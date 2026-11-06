"""驱动 GPT-SoVITS 的微调流程：备料 → 特征 → 训练 SoVITS → 训练 GPT。

每个阶段都是幂等的（产物在就跳过），中断了可以重跑。
"""

import json
import os
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

GSV = r'D:/chitose/tools/GPT-SoVITS-v2pro-20250604-nvidia50'
PY = os.path.join(GSV, 'runtime', 'python.exe')
EXP = 'chitose'
EXP_DIR = os.path.join(GSV, 'logs', EXP)
TEMP = os.path.join(GSV, 'TEMP')
ASR_TSV = r'D:/chitose/asr/chitose.tsv'
WAV_DIR = r'D:/chitose/train_wav'
LIST = os.path.join(GSV, 'logs', 'chitose.list')

BERT = os.path.join(GSV, 'GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large')
HUBERT = os.path.join(GSV, 'GPT_SoVITS/pretrained_models/chinese-hubert-base')
S2G = os.path.join(GSV, 'GPT_SoVITS/pretrained_models/v2Pro/s2Gv2Pro.pth')
S2D = os.path.join(GSV, 'GPT_SoVITS/pretrained_models/v2Pro/s2Dv2Pro.pth')
S1 = os.path.join(GSV, 'GPT_SoVITS/pretrained_models/s1v3.ckpt')
S2CFG = os.path.join(GSV, 'GPT_SoVITS/configs/s2v2Pro.json')
S1CFG = os.path.join(GSV, 'GPT_SoVITS/configs/s1longer-v2.yaml')
SV = os.path.join(GSV, 'GPT_SoVITS/pretrained_models/sv/pretrained_eres2netv2w24s4ep4.ckpt')

VERSION = 'v2Pro'
S2_EPOCHS = 10
S1_EPOCHS = 15
S2_BATCH = 4
S1_BATCH = 4

MIN_TEXT_LEN = 4


def base_env():
    env = dict(os.environ)
    env['PATH'] = os.path.join(GSV, 'runtime') + os.pathsep + env.get('PATH', '')
    env['_CUDA_VISIBLE_DEVICES'] = '0'
    env['inp_text'] = LIST
    env['inp_wav_dir'] = WAV_DIR
    env['exp_name'] = EXP
    env['opt_dir'] = EXP_DIR
    env['i_part'] = '0'
    env['all_parts'] = '1'
    env['is_half'] = 'True'
    env['version'] = VERSION
    env['PYTHONIOENCODING'] = 'utf-8'
    return env


RUNNER = r'D:/chitose/scripts/gsv_run.py'


def run(script, env, logname):
    cmd = '"%s" -I "%s" %s' % (PY, RUNNER, script)
    print('>>', cmd, flush=True)
    log = os.path.join(TEMP, logname)
    with open(log, 'w', encoding='utf-8', errors='replace') as f:
        p = subprocess.Popen(cmd, cwd=GSV, env=env, stdout=f, stderr=subprocess.STDOUT, shell=True)
        p.wait()
    print('   退出码', p.returncode, ' 日志', log, flush=True)
    if p.returncode != 0:
        with open(log, encoding='utf-8', errors='replace') as f:
            print('---- 日志尾部 ----')
            print('\n'.join(f.read().splitlines()[-25:]))
        raise SystemExit('阶段失败：%s' % script)


def build_list():
    rows = []
    with open(ASR_TSV, encoding='utf-8') as f:
        for line in f:
            if '\t' not in line:
                continue
            name, text = line.rstrip('\n').split('\t', 1)
            text = text.strip()
            if len(text) < MIN_TEXT_LEN:
                continue
            wav = os.path.splitext(name)[0] + '.wav'
            if not os.path.exists(os.path.join(WAV_DIR, wav)):
                continue
            if '_H_' in name:      # 排除 H 场景，声音不适合当底模
                continue
            rows.append('%s|%s|ja|%s' % (wav, EXP, text))
    with open(LIST, 'w', encoding='utf-8') as f:
        f.write('\n'.join(rows) + '\n')
    print('训练清单 %d 条 -> %s' % (len(rows), LIST), flush=True)
    return len(rows)


def step1_text():
    merged = os.path.join(EXP_DIR, '2-name2text.txt')
    if os.path.exists(merged):
        print('跳过 1-get-text（已存在）')
        return
    env = base_env()
    env['bert_pretrained_dir'] = BERT
    run('GPT_SoVITS/prepare_datasets/1-get-text.py', env, 'log_1text.txt')
    part = os.path.join(EXP_DIR, '2-name2text-0.txt')
    if os.path.exists(part):
        with open(part, encoding='utf-8') as f:
            lines = f.read().strip('\n').split('\n')
        with open(merged, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
        os.remove(part)
        print('   合并 %d 条 -> 2-name2text.txt' % len(lines), flush=True)


def step2_hubert():
    if os.path.isdir(os.path.join(EXP_DIR, '5-wav32k')):
        print('跳过 2-get-hubert（已存在）')
        return
    env = base_env()
    env['cnhubert_base_dir'] = HUBERT
    run('GPT_SoVITS/prepare_datasets/2-get-hubert-wav32k.py', env, 'log_2hubert.txt')


def step2b_sv():
    """v2Pro 还要一份声纹特征 7-sv_cn，否则 SoVITS 训练会 assert 失败。"""
    if os.path.isdir(os.path.join(EXP_DIR, '7-sv_cn')):
        print('跳过 2-get-sv（已存在）')
        return
    env = base_env()
    env['sv_path'] = SV
    run('GPT_SoVITS/prepare_datasets/2-get-sv.py', env, 'log_2sv.txt')


def step3_semantic():
    if os.path.exists(os.path.join(EXP_DIR, '6-name2semantic.tsv')):
        print('跳过 3-get-semantic（已存在）')
        return
    env = base_env()
    env['pretrained_s2G'] = S2G
    env['s2config_path'] = S2CFG
    run('GPT_SoVITS/prepare_datasets/3-get-semantic.py', env, 'log_3semantic.txt')


def step4_sovits():
    import glob
    if glob.glob(os.path.join(GSV, 'SoVITS_weights_v2Pro', '%s*.pth' % EXP)) and not os.environ.get('GSV_FORCE'):
        print('跳过 s2_train（已有权重）')
        return
    with open(S2CFG, encoding='utf-8') as f:
        data = json.load(f)
    data['train'].update({
        'batch_size': S2_BATCH,
        'epochs': S2_EPOCHS,
        'text_low_lr_rate': 0.4,
        'pretrained_s2G': S2G,
        'pretrained_s2D': S2D,
        'if_save_latest': True,
        'if_save_every_weights': True,
        'save_every_epoch': 1,
        'gpu_numbers': '0',
        'grad_ckpt': True,
        'lora_rank': 32,
    })
    data['model']['version'] = VERSION
    data['data']['exp_dir'] = data['s2_ckpt_dir'] = EXP_DIR
    data['save_weight_dir'] = 'SoVITS_weights_v2Pro'
    data['name'] = EXP
    data['version'] = VERSION
    os.makedirs(os.path.join(EXP_DIR, 'logs_s2_%s' % VERSION), exist_ok=True)
    cfg = os.path.join(TEMP, 'tmp_s2.json')
    with open(cfg, 'w', encoding='utf-8') as f:
        json.dump(data, f)
    env = base_env()
    run('GPT_SoVITS/s2_train.py --config "%s"' % cfg, env, 'log_s2train.txt')


def step5_gpt():
    import glob
    if glob.glob(os.path.join(GSV, 'GPT_weights_v2Pro', '%s*.ckpt' % EXP)):
        print('跳过 s1_train（已有权重）')
        return
    import yaml
    with open(S1CFG, encoding='utf-8') as f:
        data = yaml.load(f, Loader=yaml.FullLoader)
    data['train'].update({
        'batch_size': S1_BATCH,
        'epochs': S1_EPOCHS,
        'save_every_n_epoch': 1,
        'if_save_every_weights': True,
        'if_save_latest': True,
        'if_dpo': False,
        'half_weights_save_dir': 'GPT_weights_v2Pro',
        'exp_name': EXP,
    })
    data['pretrained_s1'] = S1
    data['train_semantic_path'] = os.path.join(EXP_DIR, '6-name2semantic.tsv')
    data['train_phoneme_path'] = os.path.join(EXP_DIR, '2-name2text.txt')
    data['output_dir'] = os.path.join(EXP_DIR, 'logs_s1_%s' % VERSION)
    os.makedirs(data['output_dir'], exist_ok=True)
    cfg = os.path.join(TEMP, 'tmp_s1.yaml')
    with open(cfg, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
    env = base_env()
    env['hz'] = '25hz'
    run('GPT_SoVITS/s1_train.py --config_file "%s"' % cfg, env, 'log_s1train.txt')


if __name__ == '__main__':
    os.makedirs(EXP_DIR, exist_ok=True)
    os.makedirs(TEMP, exist_ok=True)
    stage = sys.argv[1] if len(sys.argv) > 1 else 'all'
    t0 = time.time()
    if stage in ('all', 'list'):
        build_list()
    if stage in ('all', 'text'):
        step1_text()
    if stage in ('all', 'hubert'):
        step2_hubert()
    if stage in ('all', 'sv'):
        step2b_sv()
    if stage in ('all', 'semantic'):
        step3_semantic()
    if stage in ('all', 'sovits'):
        step4_sovits()
    if stage in ('all', 'gpt'):
        step5_gpt()
    print('阶段「%s」完成，用时 %.0f 秒' % (stage, time.time() - t0))
