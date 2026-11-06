"""把合成语音里过长的停顿收短。

GPT-SoVITS 会在句子交界处留下很长的静音，听起来像一直在换气。
这里按停顿长度做压制：短的原样保留，长的按比例压缩并设上限。

用法： python tighten.py <输入wav> <输出wav> [保留比例] [最长停顿时长]
"""

import sys

import numpy as np
import soundfile as sf

# 低于这个振幅就当作静音（合成器插入的是纯数字零，留一点余量给底噪）
SILENCE_THRESHOLD = 1e-4
# 短于这个长度的静音不动它，属于正常呼吸
MIN_GAP = 0.16


def tighten(x, sr, ratio=0.35, max_gap=0.30):
    mono = x.mean(axis=1) if x.ndim > 1 else x
    quiet = np.abs(mono) < SILENCE_THRESHOLD

    diff = np.diff(np.concatenate([[0], quiet.view(np.int8), [0]]))
    starts = np.where(diff == 1)[0]
    ends = np.where(diff == -1)[0]

    pieces = []
    cursor = 0
    changed = 0
    saved = 0.0
    for s, e in zip(starts, ends):
        gap = (e - s) / sr
        if gap < MIN_GAP:
            continue
        keep = min(gap * ratio, max_gap)
        keep = max(keep, MIN_GAP * 0.5)
        if keep >= gap - 1e-6:
            continue
        if s > cursor:
            pieces.append(x[cursor:s])
        n = int(round(keep * sr))
        # 用淡入淡出代替硬切，避免爆音
        fade = min(n // 2, int(0.008 * sr))
        seg = np.zeros((n, x.shape[1]), dtype=x.dtype) if x.ndim > 1 else np.zeros(n, dtype=x.dtype)
        if fade > 0:
            if x.ndim > 1:
                seg[:fade] = x[s] * np.linspace(0, 1, fade)[:, None]
                seg[-fade:] = x[e - 1] * np.linspace(1, 0, fade)[:, None]
            else:
                seg[:fade] = x[s] * np.linspace(0, 1, fade)
                seg[-fade:] = x[e - 1] * np.linspace(1, 0, fade)
        pieces.append(seg)
        cursor = e
        changed += 1
        saved += gap - keep
    if cursor < len(x):
        pieces.append(x[cursor:])

    if not pieces:
        return x, 0, 0.0
    out = np.concatenate(pieces, axis=0)
    return out, changed, saved


def process(src, dst, ratio=0.35, max_gap=0.30):
    x, sr = sf.read(src, dtype='float32', always_2d=True)
    out, n, saved = tighten(x, sr, ratio, max_gap)
    sf.write(dst, out, sr, subtype='PCM_16')
    return len(x) / sr, len(out) / sr, n, saved


if __name__ == '__main__':
    src, dst = sys.argv[1], sys.argv[2]
    ratio = float(sys.argv[3]) if len(sys.argv) > 3 else 0.35
    max_gap = float(sys.argv[4]) if len(sys.argv) > 4 else 0.30
    d0, d1, n, saved = process(src, dst, ratio, max_gap)
    print('压缩了 %d 处停顿，省下 %.2f 秒：%.1f 秒 -> %.1f 秒' % (n, saved, d0, d1))
