"""用 faster-whisper 把千岁的参考音频转写成日文文本。"""

import os
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

MODEL_DIR = r'D:/chitose/tools/whisper'


def _add_cuda_dlls():
    """ctranslate2 要靠 torch 自带的 CUDA 库，得手动加进 DLL 搜索路径。"""
    import os
    try:
        import torch
        lib = os.path.join(os.path.dirname(torch.__file__), 'lib')
        if os.path.isdir(lib):
            os.add_dll_directory(lib)
    except Exception:
        pass


_add_cuda_dlls()


def load16k(path):
    """读成 16 kHz 单声道 float32，绕开 faster-whisper 的 PyAV 解码。"""
    import numpy as np
    import soundfile as sf
    x, sr = sf.read(path, dtype='float32', always_2d=True)
    x = x.mean(axis=1)
    if sr != 16000:
        n = int(round(len(x) * 16000 / sr))
        idx = np.linspace(0, len(x) - 1, n)
        lo = np.floor(idx).astype(np.int64)
        hi = np.minimum(lo + 1, len(x) - 1)
        frac = (idx - lo).astype(np.float32)
        x = (x[lo] * (1 - frac) + x[hi] * frac).astype(np.float32)
    return x


def main(indir, out_txt, limit=None):
    from faster_whisper import WhisperModel
    model = WhisperModel(MODEL_DIR, device='cpu', compute_type='int8', cpu_threads=8)
    files = sorted(f for f in os.listdir(indir) if f.lower().endswith('.wav'))
    if limit:
        files = files[:limit]
    rows = []
    for i, f in enumerate(files, 1):
        p = os.path.join(indir, f)
        segs, info = model.transcribe(load16k(p), language='ja', beam_size=5, vad_filter=False)
        text = ''.join(s.text for s in segs).strip()
        rows.append((f, text))
        print('%2d/%d  %-32s %s' % (i, len(files), f, text))
    with open(out_txt, 'w', encoding='utf-8') as o:
        for f, t in rows:
            o.write('%s\t%s\n' % (f, t))
    print('已写', out_txt)


if __name__ == '__main__':
    indir = sys.argv[1] if len(sys.argv) > 1 else r'D:/chitose/ref_wav'
    out = sys.argv[2] if len(sys.argv) > 2 else r'D:/chitose/ref/transcript.tsv'
    lim = int(sys.argv[3]) if len(sys.argv) > 3 else None
    main(indir, out, lim)
