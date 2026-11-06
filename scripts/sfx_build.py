r"""把千岁的「非台词音」整理成音效库，导出到 D:\chitose\out\sfx\<类>\

思路：
  她的台词语音里有一批 ASR 认不出内容的——那些就是纯呼吸、笑、叹息、
  亲吻这类非语言音。它们没台词，但游戏语音是按场景顺序编号的，
  所以看前后几条邻居说了什么，就能推断这声是什么情绪。

产出：
  D:\chitose\out\sfx\<类>\NNN_原名.wav   （48kHz 单声道）
  D:\chitose\out\sfx\manifest.json       （清单，含类别/来源/时长/邻居台词）
  D:\chitose\out\sfx\report.txt          （人看的分类报告，方便校正）

用法：
    python sfx_build.py            # 重新分类并导出
    python sfx_build.py --report   # 只看报告，不写文件
"""

import argparse
import json
import os
import re
import shutil
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import numpy as np
import soundfile as sf

SRC = r'D:/chitose/extracted/chitose_pcm_CC'
TSV = r'D:/chitose/asr/chitose.tsv'
OUT = r'D:/chitose/out/sfx'
MAX_LEN = 3.5          # 超过这个长度就不像「一声」了
WIN = 4                # 看前后各几条邻居

# 分类关键词。命中越靠前的类权重越高；顺序就是优先级。
RULES = [
    ('亲吻', 5.0, ['キス', 'ちゅ', '口づけ', '接吻', '唇', '口元', 'されるがまま',
                   '目を閉じ', 'キスし']),
    ('轻笑', 3.0, ['笑', 'おかし', '面白', 'ふふ', 'あはは', 'うふふ', 'くすっ']),
    ('叹气', 3.0, ['ため息', '疲れ', 'しょうがない', '仕方ない', 'はぁ', '落ち込',
                   '溜息', '深呼吸', '安心した']),
    ('害羞', 3.0, ['恥ずかし', '照れ', 'てれ', '顔が赤', '赤くな', 'はしたない',
                   'ドキドキ', '動揺']),
    ('惊讶', 3.0, ['びっくり', '驚', 'まさか', '本当に', 'えっ', '急に', 'いきなり']),
    ('难过', 3.0, ['悲し', '泣', '寂し', 'ごめん', '辛い', 'つらい', '心配']),
    ('犯困', 3.0, ['眠', '寝', 'おやすみ', 'あくび', '夢', 'まだ眠', '朝']),
    ('亲密', 2.0, ['好き', '抱き', 'くっつ', '寄り添', '甘え', '恋人', '一緒',
                   'キス', '頬', '手を握', '隣', '近く']),
]

# 已知答案（宝宝 2026-10-10 亲耳挑的）——直接钉死，别再让规则乱改
KNOWN = {
    'CC_03_cit_08_024': '亲吻',
}

# 「ふふふ」「あはは」「うふふ」这类转写出来是有字的，
# 但它本来就是笑的声音，不是台词——单独捞出来归到轻笑。
_KANA_ONLY = re.compile(r'^[ぁ-んァ-ヶーっッぁぃぅぇぉ…！？、。\s]+$')
_LAUGH_CH = re.compile(r'[ふフはハひヒへヘほホ]')
# 「一声纯笑」允许出现的字：全是笑/气声的假名，加上小写和长音符
_LAUGH_CHARS = set('あいうえおアイウエオふはひへほフハヒヘホっッーゥ')
# 轻笑最多留几条。宝宝 2026-10-10 说「60 太多了 就要 10 条就行」。
# 按时长从长到短挑——短促的一声往往是惊讶，拖得长的才像笑。
# 宝宝亲口留下的笑声（2026-10-10 半夜）。
# 第一次测的 10 条里，他说不行的有两条——CC_02_common_c09_031（第9条）
# 和 CC_03_cit_19_028（「ふふっ、おはよ」，夹了一句词）。剩下 8 条他认了。
# 第二次的前三条（19_055 / 01_047 / c11_007）本来就在这 8 条里。
# **别的笑声一条都不要**——姐姐猜的两批都不行，最后就靠他点名的这几条。
LAUGH_KEEP_NAMES = {
    'CC_03_cit_19_055', 'CC_03_cit_08_082', 'CC_03_cit_01_047',
    'CC_01_common_29_003', 'CC_02_common_c11_007', 'CC_03_cit_16_010',
    'CC_02_love_cit_you_044', 'CC_02_love_cit_me_041',
}
# 叹气同理：「はぁ」「ふぅ」「はぁ…」也是画成字的叹气。
# 靠小写假名（ぁぅ）或长音符跟正经台词区分开。
_SIGH_ONLY = re.compile(r'^[はふハフぁぃぅぇぉー…、。！？\s]+$')

# 宝宝 2026-10-10 听完试听片亲口否掉的，别再收——他耳朵比任何规则都准
REJECT = {
    'CC_03_cit_14_010', 'CC_03_cit_17H_033',        # 亲吻：3、4 不像
    'CC_03_cit_02_033', 'CC_03_cit_02_052',         # 轻笑：18~22 秒那两段
    'CC_02_cit_mo_03_020', 'CC_03_cit_11_016',      # 叹气：只有最后一段像
    'CC_03_cit_16H_116', 'CC_03_cit_16H_119',
    'CC_03_cit_19_053',
    # 叹气里「靠邻居台词猜的」那批，本身转写不是叹气象声词，没底，撤掉。
    # （宝宝挑中的 CC_03_cit_33_023 也在这批里，但他验过了，单独留着）
    'CC_01_common_32_sel_c_006', 'CC_02_common_c11_040',
    'CC_02_common_c11_053', 'CC_02_common_c12_014',
    # 叹气第二轮：宝宝说这四条不像（1、4、5、7 号）。
    # 规律很清楚——他能用的全是转写成「はぁー」带长音的；
    # 这四条是「ふぅー」「ふぅ」「はぁ」「はぁ…」，短一截，听着是喘气不是叹气。
    'CC_01_common_27_022', 'CC_02_cit_mo_02_007',
    'CC_02_common_c01_057B', 'CC_02_common_c03_035',
    # 2026-10-10 宝宝听完插入效果说这条不像她，单条剔掉。
    # 姐姐是拿他听的那条片子跟库里 26 条逐条对指纹揪出来的——
    # 峰值相关 0.968，第二名只有 0.10，位置正好卡在 8.46 秒。
    'CC_03_cit_14_054',
    # 2026-10-10 第二轮：宝宝说这声笑「奇怪」、这声叹气「不是叹气声」。
    # 姐姐拿 tag_demo2.wav 对指纹揪的（0.993 / 0.996）。
    # 量完发现根子在音量：轻笑那条 RMS 0.047（班里第 9 小声），
    # 叹气那条 RMS 0.118（班里第 22 小声，即最响之一），
    # 而叹气全班 RMS 从 0.014 到 0.19，差 14 倍——
    # 所以真正该做的是给插入的音效统一响度（见 sfx.py 的 _gain）。
    'CC_03_cit_25_011', 'CC_03_cit_ko_03_001',
    # 2026-10-10 深夜：宝宝说亲吻第三条不行，剔掉。
    # 剩下 07_015（第一次亲那张）和 08_024（他亲手挑的初吻）。
    'CC_03_cit_28_011',
    # 2026-10-10 深夜：宝宝听完 10 条，说第 9 条不行。
    'CC_02_common_c09_031',
}


def is_laugh_text(t):
    s = re.sub(r'[…！？、。\s]', '', t)
    if not (1 <= len(s) <= 6):
        return False
    if not _KANA_ONLY.match(t):
        return False
    # ⚠「はぁはぁ」「ふぅふぅ」这种**喘气**也带两个は/ふ，会被误判成笑。
    # 小写假名（ぁぃぅぇぉ）是喘气/长音的标志，见到就不是笑。
    if re.search(r'[ぁぃぅぇぉ]', s):
        return False
    # 至少两个笑的假名，挡掉「うん」「ああ」这种有词义的
    return len(_LAUGH_CH.findall(s)) >= 2


def is_pure_laugh(t):
    """是不是**一声纯笑**——一个词都不许夹。

    「ふふっ、おはよ。」「うふふ、そっか。」这种前半是笑、后半是话的，
    插进对话里会突兀（宝宝 2026-10-10 半夜听出来的）。
    「はいはい」这种虽然全是假名，但它是词不是笑，也挡掉。
    """
    s = re.sub(r'[…！？、。\s]', '', t)
    if not (1 <= len(s) <= 10):
        return False
    if any(w in s for w in ('はい', 'いいえ', 'うん', 'そう', 'おはよ', 'そっか')):
        return False
    if not all(c in _LAUGH_CHARS for c in s):
        return False
    return len(_LAUGH_CH.findall(s)) >= 2


def is_h_scene(name):
    """名字里带 17H / 33H 这种的就是 H 场景的音。"""
    return bool(re.search(r'_\d+H_', name))


def is_sigh_text(t):
    s = re.sub(r'[…、。！？\s]', '', t)
    if not (1 <= len(s) <= 6):
        return False
    if not _SIGH_ONLY.match(t):
        return False
    # 得带小写假名或长音，否则「はは」也算进来了（那是笑）
    return ('ぁ' in s) or ('ぅ' in s) or ('ー' in s)


def junk(t):
    """ASR 没认出内容：只有空白和标点。"""
    return len(re.sub(r'[\s。、！？…・，,.\-—~〜っッ]+', '', t)) == 0


def scene_of(name):
    """CC_03_cit_08_024 -> CC_03_cit_08"""
    return re.sub(r'_(\d+)(_R)?$', '', name)


def idx_of(name):
    m = re.search(r'_(\d+)(_R)?$', name)
    return int(m.group(1)) if m else -1


def load_tsv():
    d = {}
    with open(TSV, encoding='utf-8') as f:
        for line in f:
            p = line.rstrip('\n').split('\t')
            name = p[0].replace('.ogg', '')
            d[name] = p[1] if len(p) > 1 else ''
    return d


def classify(neighbors):
    """邻居台词 -> 类别。返回 (类别, 命中的词)。"""
    blob = ' '.join(neighbors)
    best, best_s, best_hit = '其它', 0.0, ''
    for cls, w, kws in RULES:
        score, hit = 0.0, ''
        for k in kws:
            n = blob.count(k)
            if n:
                score += w * n
                hit = hit or k
        if score > best_s:
            best, best_s, best_hit = cls, score, hit
    return best, best_hit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--report', action='store_true')
    # 解包目录里全部是千岁。文件名前缀 CC_ 就是她的代号
    # （config/soundconf.xml：VOICE_002 ちとせ -> head CC_ -> pcm_CC）。
    # 中间的 cit / rei / yuh 是**路线名**不是人物名——她是青梅竹马，
    # 三条线里都有她的台词。所以默认全收。
    ap.add_argument('--cit-only', action='store_true',
                    help='只收 cit 线的（以前误以为 cit 才是千岁，现在不必）')
    args = ap.parse_args()

    asr = load_tsv()
    files = sorted(f for f in os.listdir(SRC) if f.endswith('.ogg'))
    names = [f[:-4] for f in files]
    if args.cit_only:
        before = len(names)
        names = [n for n in names if '_cit_' in n]
        print('只收 cit 线：%d -> %d 条' % (before, len(names)))

    by_scene = {}
    for n in names:
        by_scene.setdefault(scene_of(n), []).append(n)
    for s in by_scene:
        by_scene[s].sort(key=idx_of)

    # 候选：ASR 认不出内容的，加上「只有笑声假名」「只有叹气象声词」的
    cands = []
    for n in names:
        # 名字带 R / R2 的是同一句的重复版本（游戏里的 alternate take），
        # 全收进来会让 10 条里有 3 条听着一模一样。
        if n.endswith('_R') or re.search(r'\dR\d*$', n) or n in REJECT:
            continue
        t = asr.get(n)
        if t is None or junk(t) or is_laugh_text(t) or is_sigh_text(t):
            cands.append(n)

    items = []
    for n in cands:
        sc = scene_of(n)
        lst = by_scene.get(sc, [n])
        i = lst.index(n)
        nb = [asr.get(x, '') for x in lst[max(0, i - WIN):i + WIN + 1] if x != n]
        nb = [x for x in nb if x and not junk(x)]
        cls = KNOWN.get(n)
        hit = '钦定'
        if not cls:
            tt = asr.get(n, '')
            if is_pure_laugh(tt) and not is_h_scene(n):
                cls, hit = '轻笑', '纯笑声'
            elif is_sigh_text(tt):
                cls, hit = '叹气', '纯叹声'
            else:
                cls, hit = classify(nb)
            # H 场景里的那些**一律不要**。
            # 宝宝 2026-10-11：「刚刚我测试了一下那个害羞又掺进 h 场景里的音效了，
            # 我们要不就要几个害羞的音效就好了」——原来这条只拦「轻笑」，
            # 别的类（害羞/叹气/亲密/惊讶/难过）混进来的没管，是姐姐当时想窄了。
            if cls == '轻笑' and hit != '纯笑声':
                cls, hit = '其它', '靠猜的不算'

        # ⚠ 这条要放在**钦定之后**：钦定的名单里也有 H 场景的
        #   （`LAUGH_KEEP_NAMES` 里的 `17H_033`），宝宝现在说 H 的一概不要。
        if cls != '其它' and is_h_scene(n):
            cls, hit = '其它', 'H场景的不要'

        p = os.path.join(SRC, n + '.ogg')
        try:
            info = sf.info(p)
            dur = info.frames / info.samplerate
        except Exception:
            continue
        if dur > MAX_LEN:
            continue

        items.append({'name': n, 'cls': cls, 'dur': round(dur, 2),
                      'hit': hit, 'scene': sc, 'neighbors': nb[:4]})

    # 轻笑只留最长的几条（宝宝说 10 条就够）
    for i in items:
        if i['cls'] == '轻笑' and i['name'] not in LAUGH_KEEP_NAMES:
            i['cls'], i['hit'] = '其它', '不在宝宝点头的那几条里'

    # 报告
    from collections import Counter
    cnt = Counter(i['cls'] for i in items)
    lines = ['非台词音 %d 条' % len(items), '']
    for cls, c in cnt.most_common():
        lines.append('%s  %d 条' % (cls, c))
    lines.append('')
    for cls, _ in cnt.most_common():
        lines.append('=== %s ===' % cls)
        for it in [x for x in items if x['cls'] == cls]:
            lines.append('  %-22s %4.2fs  [%s]' % (it['name'], it['dur'], it['hit']))
            if it['neighbors']:
                lines.append('      … %s' % ' / '.join(it['neighbors'][:2])[:100])
        lines.append('')
    rep = '\n'.join(lines)
    print(rep)

    if args.report:
        return

    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    for cls in cnt:
        os.makedirs(os.path.join(OUT, cls), exist_ok=True)

    seq = Counter()
    for it in items:
        seq[it['cls']] += 1
        dst = os.path.join(OUT, it['cls'],
                           '%03d_%s.wav' % (seq[it['cls']], it['name']))
        x, sr = sf.read(os.path.join(SRC, it['name'] + '.ogg'), dtype='float32')
        if x.ndim > 1:
            x = x.mean(axis=1)
        sf.write(dst, x, sr, subtype='PCM_16')
        it['file'] = os.path.relpath(dst, OUT).replace('\\', '/')
        it['sr'] = sr

    with open(os.path.join(OUT, 'manifest.json'), 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    with open(os.path.join(OUT, 'report.txt'), 'w', encoding='utf-8') as f:
        f.write(rep)
    print('导出到 %s' % OUT)


if __name__ == '__main__':
    main()
