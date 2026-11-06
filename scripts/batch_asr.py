"""批量把千岁的语音转写成日文文本（微调要用）。

结果增量写到 tsv，中断了也能接着跑。
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import numpy as np
import soundfile as sf

from transcribe import MODEL_DIR, _add_cuda_dlls

_add_cuda_dlls()


def load16k(path):
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


def main(indir, out_tsv, contains=None):
    from faster_whisper import WhisperModel
    done = set()
    if os.path.exists(out_tsv):
        with open(out_tsv, encoding='utf-8') as f:
            for line in f:
                if '\t' in line:
                    done.add(line.split('\t', 1)[0])
    files = sorted(f for f in os.listdir(indir) if f.lower().endswith('.ogg'))
    if contains:
        files = [f for f in files if contains in f]
    todo = [f for f in files if f not in done]
    print('总 %d 条，已完成 %d，待处理 %d（名字过滤：%s）'
          % (len(files), len(done), len(todo), contains or '无'))

    model = WhisperModel(MODEL_DIR, device='cuda', compute_type='float16')
    t0 = time.time()
    with open(out_tsv, 'a', encoding='utf-8') as out:
        for i, f in enumerate(todo, 1):
            try:
                segs, _ = model.transcribe(load16k(os.path.join(indir, f)),
                                           language='ja', beam_size=1,
                                           condition_on_previous_text=False,
                                           # 非台词音（呻吟、尖叫、笑）会让 Whisper
                                           # 认不出词、一路重复到 448 上限，慢十倍。
                                           # 压到 128 就够装下最长的台词了。
                                           max_new_tokens=128)
                text = ''.join(s.text for s in segs).strip()
            except Exception as e:
                text = ''
                print('  失败 %s: %s' % (f, e))
            out.write('%s\t%s\n' % (f, text))
            out.flush()
            if i % 100 == 0:
                el = time.time() - t0
                print('  %d/%d  已用 %.0f 秒  预计还要 %.0f 分钟'
                      % (i, len(todo), el, el / i * (len(todo) - i) / 60))
    print('全部完成')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else r'D:/chitose/extracted/chitose_pcm_CC',
         sys.argv[2] if len(sys.argv) > 2 else r'D:/chitose/asr/chitose.tsv',
         sys.argv[3] if len(sys.argv) > 3 else '_cit_')
