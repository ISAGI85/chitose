"""把千岁的 .ogg 语音转成 F5-TTS 能用的单声道 wav（24 kHz）。"""

import os
import sys

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TARGET_SR = 24000


def resample(x, sr, target=TARGET_SR):
    if sr == target:
        return x
    n = int(round(len(x) * target / sr))
    idx = np.linspace(0, len(x) - 1, n)
    lo = np.floor(idx).astype(np.int64)
    hi = np.minimum(lo + 1, len(x) - 1)
    frac = (idx - lo).astype(np.float32)
    return (x[lo] * (1 - frac) + x[hi] * frac).astype(np.float32)


def convert(src, dst, target=TARGET_SR):
    x, sr = sf.read(src, dtype='float32', always_2d=True)
    x = x.mean(axis=1)  # 单声道
    x = resample(x, sr, target)
    peak = float(np.abs(x).max())
    if peak > 0:
        x = x / peak * 0.95
    sf.write(dst, x, target, subtype='PCM_16')
    return len(x) / target


if __name__ == '__main__':
    indir = sys.argv[1] if len(sys.argv) > 1 else r'D:/chitose/ref'
    outdir = sys.argv[2] if len(sys.argv) > 2 else r'D:/chitose/ref_wav'
    os.makedirs(outdir, exist_ok=True)
    n = 0
    for f in sorted(os.listdir(indir)):
        if not f.lower().endswith('.ogg'):
            continue
        out = os.path.join(outdir, os.path.splitext(f)[0] + '.wav')
        try:
            d = convert(os.path.join(indir, f), out)
            n += 1
            if n <= 5:
                print('  %-32s %.2f 秒' % (f, d))
        except Exception as e:
            print('  失败', f, e)
    print('已转 %d 个到 %s' % (n, outdir))
