r"""验证哪些语音真的是千岁本人。

那个解包目录里其实混着三个人的声音：
  CC_*_cit_*  千岁      CC_*_rei_*  玲      CC_*_yuh_*  結灯
还有一大堆 CC_*_common_*，名字上看不出是谁的。

用 GPT-SoVITS 自带的话者验证模型 ERes2Net 提声纹，拿 cit 当基准看每条跟谁最像。

**关键**：原始声纹向量里有一个很强的「公共方向」，所有人的余弦都接近 1，
分不开人。必须先减掉全体均值（中心化）再做余弦，自检才有意义。

用法（要用 GPT-SoVITS 自带的 runtime python，我们的 venv 没有 funasr）：
    cd D:\chitose\tools\GPT-SoVITS-v2pro-20250604-nvidia50
    .\runtime\python.exe D:\chitose\scripts\verify_speaker.py
    .\runtime\python.exe D:\chitose\scripts\verify_speaker.py --per 60
"""

import argparse
import glob
import os
import random
import sys

GSV = r'D:/chitose/tools/GPT-SoVITS-v2pro-20250604-nvidia50'
CLIPS = r'D:/chitose/extracted/chitose_pcm_CC'
MIN_LEN, MAX_LEN = 2.0, 6.0

os.chdir(GSV)
sys.path.insert(0, GSV)
sys.path.insert(0, os.path.join(GSV, 'GPT_SoVITS'))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import numpy as np
import soundfile as sf
import torch

KNOWN = [('cit', 'CC_03_cit_*.ogg'), ('rei', 'CC_03_rei_*.ogg'),
         ('yuh', 'CC_03_yuh_*.ogg')]
UNKNOWN = [('CC_01_common', 'CC_01_common_*.ogg'),
           ('CC_02_common', 'CC_02_common_*.ogg'),
           ('CC_02_love', 'CC_02_love_*.ogg'),
           ('CC_amakano2_system', 'CC_amakano2_system_*.ogg'),
           ('CC_MOVIE', 'CC_MOVIE_*.ogg')]


def load16k(path):
    x, sr = sf.read(path, dtype='float32', always_2d=True)
    x = x.mean(axis=1)
    if sr != 16000:
        n = int(round(len(x) * 16000 / sr))
        idx = np.linspace(0, len(x) - 1, n)
        lo = np.floor(idx).astype(np.int64)
        hi = np.minimum(lo + 1, len(x) - 1)
        f = (idx - lo).astype(np.float32)
        x = (x[lo] * (1 - f) + x[hi] * f).astype(np.float32)
    return x


def pick(pat, n, seed=0):
    fs = sorted(glob.glob(os.path.join(CLIPS, pat)))
    random.Random(seed).shuffle(fs)
    out = []
    for f in fs:
        if len(out) >= n:
            break
        try:
            i = sf.info(f)
        except Exception:
            continue
        if MIN_LEN <= i.frames / i.samplerate <= MAX_LEN:
            out.append(f)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--per', type=int, default=40)
    args = ap.parse_args()

    from sv import SV
    # 全程 CPU：sv.py 里 is_half 会把波形转 half 而 kaldi.fbank 不收 half；
    # float32 上 GPU 又会出现 fbank 在 CPU、模型在 GPU 的设备不一致。
    # 模型很小，CPU 跑几百条几十秒的事。
    sv = SV('cpu', False)

    def emb(path):
        x = torch.from_numpy(load16k(path)).unsqueeze(0)
        with torch.no_grad():
            e = sv.compute_embedding3(x)
        return e.squeeze(0).float().cpu().numpy()

    print('提取声纹…')
    data = {}
    for name, pat in KNOWN + UNKNOWN:
        fs = pick(pat, args.per, seed=7)
        if fs:
            data[name] = [(f, emb(f)) for f in fs]
            print('  %-18s %d 条' % (name, len(fs)))

    # 中心化：减掉全体均值，去掉那个公共方向
    allv = np.stack([v for vs in data.values() for _, v in vs])
    mu = allv.mean(0)

    def unit(v):
        v = v - mu
        return v / (np.linalg.norm(v) + 1e-9)

    def centroid(vecs):
        c = np.stack([unit(v) for v in vecs]).mean(0)
        return c / (np.linalg.norm(c) + 1e-9)

    # 自检：一半建基准，另一半认人
    print()
    print('=== 自检（一半建基准，一半认人）===')
    refs, tests = {}, {}
    for k, _ in KNOWN:
        vs = [v for _, v in data[k]]
        h = len(vs) // 2
        refs[k] = centroid(vs[:h])
        tests[k] = vs[h:]
    ok = 0
    tot = 0
    for k, _ in KNOWN:
        hit = 0
        for v in tests[k]:
            got = max(refs, key=lambda r: float(unit(v) @ refs[r]))
            hit += got == k
        ok += hit
        tot += len(tests[k])
        print('  %-4s 认回 %2d/%2d' % (k, hit, len(tests[k])))
    print('  合计 %.1f%%' % (100 * ok / max(tot, 1)))

    print()
    print('=== 待验的组（跟谁最像）===')
    for name, _ in UNKNOWN:
        if name not in data:
            print('  %-18s 没素材' % name)
            continue
        votes, marg = {}, []
        for _, v in data[name]:
            s = {k: float(unit(v) @ refs[k]) for k in refs}
            got = max(s, key=s.get)
            votes[got] = votes.get(got, 0) + 1
            marg.append(s['cit'] - max(s[k] for k in s if k != 'cit'))
        n = len(data[name])
        top = sorted(votes.items(), key=lambda kv: -kv[1])
        print('  %-18s %s' % (name, '  '.join('%s %d/%d' % (k, c, n)
                                              for k, c in top)))
        m = np.array(marg)
        print('  %-18s 跟 cit 的余量 中位 %+.3f  ＞0.05 的占 %.0f%%'
              % ('', np.median(m), 100 * (m > 0.05).mean()))


if __name__ == '__main__':
    main()
