r"""拿千岁的声音试 Qwen3-TTS 的三秒克隆，跟 GPT-SoVITS 比一比。

用法：
    python qwen_tts_test.py
产出：
    D:/chitose/out/qwen_test/*.wav
"""

import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
os.environ.setdefault('HF_ENDPOINT', 'https://hf-mirror.com')

import numpy as np
import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel

MODEL = r'D:/chitose/tools/Qwen3-TTS-12Hz-1.7B-Base'
SRC = r'D:/chitose/extracted/chitose_pcm_CC'
OUT = r'D:/chitose/out/qwen_test'
os.makedirs(OUT, exist_ok=True)

LINES = [
    'おかえりなさい、待ってたよ。',
    '今日はちょっと疲れたでしょ。ちゃんとご飯食べた?',
]

REFS = [
    ('平静', 'CC_02_cit_mo_05_003', 'うん、大丈夫、難しいことじゃないから。'),
    ('明亮', 'CC_03_cit_35_001', 'うん!特別なものを作るから楽しみにしてね!'),
]


def load_ref(name):
    p = os.path.join(SRC, name + '.ogg')
    x, sr = sf.read(p, dtype='float32')
    if x.ndim > 1:
        x = x.mean(axis=1)
    return x, sr


def main():
    print('载入 Qwen3-TTS…')
    t0 = time.time()
    model = Qwen3TTSModel.from_pretrained(
        MODEL, device_map='cuda:0', dtype=torch.bfloat16)
    print('载入用了 %.0f 秒' % (time.time() - t0))
    if torch.cuda.is_available():
        print('显存占用 %.1f G'
              % (torch.cuda.memory_allocated() / 1024 ** 3))

    for tag, name, text in REFS:
        x, sr = load_ref(name)
        print()
        print('=== 参考「%s」%s（%.2f 秒）===' % (tag, name, len(x) / sr))
        t0 = time.time()
        prompt = model.create_voice_clone_prompt(ref_audio=(x, sr), ref_text=text)
        print('  建声纹用了 %.1f 秒' % (time.time() - t0))
        for i, line in enumerate(LINES, 1):
            t0 = time.time()
            wavs, osr = model.generate_voice_clone(
                text=line, language='Japanese', voice_clone_prompt=prompt)
            w = np.asarray(wavs[0], dtype=np.float32).reshape(-1)
            p = os.path.join(OUT, '%s_%d.wav' % (tag, i))
            sf.write(p, w, osr, subtype='PCM_16')
            print('  %d: %.2f 秒 / 合成 %.1f 秒 / %d Hz  -> %s'
                  % (i, len(w) / osr, time.time() - t0, osr, os.path.basename(p)))
    print()
    print('都在 %s' % OUT)


if __name__ == '__main__':
    main()
