r"""把音效库的每一类拼成一条带编号的试听片，方便宝宝报「第几个」。

产出 D:\chitose\out\sfx_audition\
    <类>.wav   每段之间 0.6 秒静音
    <类>.txt   编号 -> 文件名 / 时长
    all.mp3    十二类各取前若干条，全拼一条（发微信方便）

用法：
    python sfx_audition.py               # 全部类别
    python sfx_audition.py 轻笑 亲吻      # 只做这两类
    python sfx_audition.py --per 5        # 每类只取前 5 条
"""

import argparse
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import numpy as np
import soundfile as sf

from sfx import SFX_DIR, _same_sr

OUT = r'D:/chitose/out/sfx_audition'
GAP = 0.6


def build(cls, per=None, gap=GAP, skip=0):
    d = os.path.join(SFX_DIR, cls)
    if not os.path.isdir(d):
        return None, None
    files = sorted(f for f in os.listdir(d) if f.lower().endswith('.wav'))
    # 编号跟着库里固定的顺序走，skip 掉前 n 条之后编号仍然对得上，
    # 方便「上次听过 1~14 了，这次只听 15 往后」
    numbered = list(enumerate(files, 1))[skip:]
    if per:
        numbered = numbered[:per]
    if not numbered:
        return None, None

    pieces, lines, sr = [], [], None
    for n, f in numbered:
        x, s = sf.read(os.path.join(d, f), dtype='float32')
        if x.ndim > 1:
            x = x.mean(axis=1)
        if sr is None:
            sr = s
        x = _same_sr(np.asarray(x, dtype=np.float32).reshape(-1), s, sr)
        x = x / max(np.abs(x).max(), 1e-6) * 0.85      # 统一响度，免得有的听不见
        pieces.append(x)
        lines.append('%2d  %-28s %4.2fs' % (n, f, len(x) / sr))
    out = []
    for i, x in enumerate(pieces):
        if i:
            out.append(np.zeros(int(sr * gap), dtype=np.float32))
        out.append(x)
    return np.concatenate(out), (sr, lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('classes', nargs='*')
    ap.add_argument('--per', type=int, default=None)
    ap.add_argument('--from', dest='skip', type=int, default=0,
                    help='跳过前 N 条（上次听过的），编号仍按库里的顺序')
    ap.add_argument('--mp3', action='store_true', help='拼完再导一条全类 mp3')
    args = ap.parse_args()

    if not os.path.isdir(SFX_DIR):
        print('音效库还没建：先跑 sfx_build.py')
        return
    classes = args.classes or sorted(
        d for d in os.listdir(SFX_DIR) if os.path.isdir(os.path.join(SFX_DIR, d)))
    os.makedirs(OUT, exist_ok=True)

    for cls in classes:
        x, meta = build(cls, args.per, skip=args.skip)
        if x is None:
            print('%s：没有素材，跳过' % cls)
            continue
        sr, lines = meta
        wav = os.path.join(OUT, cls + '.wav')
        sf.write(wav, x, sr, subtype='PCM_16')
        with open(os.path.join(OUT, cls + '.txt'), 'w', encoding='utf-8') as f:
            f.write('%s 共 %d 条\n\n' % (cls, len(lines)))
            f.write('\n'.join(lines) + '\n')
        print('%s  %d 条  %.1f 秒' % (cls, len(lines), len(x) / sr))

    if args.mp3:
        allp = []
        for cls in classes:
            x, meta = build(cls, args.per, skip=args.skip)
            if x is None:
                continue
            sr = meta[0]
            allp.append((x, sr))
        if allp:
            gapx = np.zeros(int(allp[0][1] * 1.2), dtype=np.float32)
            cat = []
            for i, (x, sr) in enumerate(allp):
                if i:
                    cat.append(gapx)
                cat.append(x)
            wav = os.path.join(OUT, 'all.wav')
            sf.write(wav, np.concatenate(cat), allp[0][1], subtype='PCM_16')
            mp3 = wav[:-4] + '.mp3'
            exe = shutil.which('ffmpeg')
            if exe:
                r = subprocess.run([exe, '-y', '-i', wav, '-b:a', '128k', mp3],
                                   capture_output=True)
                print('全拼：%s' % (mp3 if r.returncode == 0 else wav))
            else:
                print('全拼：%s（没找到 ffmpeg，只能留 wav）' % wav)


if __name__ == '__main__':
    main()
