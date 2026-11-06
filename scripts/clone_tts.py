"""用 F5-TTS 零样本克隆千岁的声线。

用法：
    python clone_tts.py <参考音频> <参考文本> <要说的中文> <输出wav>
"""

import os
import sys

os.environ.setdefault('HF_ENDPOINT', 'https://hf-mirror.com')

CKPT = r'D:/chitose/tools/f5tts/model_1250000.safetensors'
VOCAB = r'D:/chitose/tools/f5tts/vocab.txt'


def _patch_torchaudio():
    """新版 torchaudio.load 依赖 torchcodec（要 FFmpeg DLL），
    这里换成用 soundfile 解码，效果一样。"""
    import numpy as np
    import soundfile as sf
    import torch
    import torchaudio

    def load(uri, frame_offset=0, num_frames=-1, normalize=True,
             channels_first=True, **kwargs):
        data, sr = sf.read(str(uri), dtype='float32', always_2d=True)
        wav = torch.from_numpy(data.T.copy())
        if frame_offset:
            wav = wav[:, frame_offset:]
        if num_frames and num_frames > 0:
            wav = wav[:, :num_frames]
        return wav, sr

    torchaudio.load = load
    torchaudio.load_with_torchcodec = load


_patch_torchaudio()


def load(device=None):
    from f5_tts.api import F5TTS
    return F5TTS(ckpt_file=CKPT, vocab_file=VOCAB, device=device)


def say(f5, ref_wav, ref_text, gen_text, out_wav, seed=42):
    wav, sr, _ = f5.infer(
        ref_file=ref_wav,
        ref_text=ref_text,
        gen_text=gen_text,
        file_wave=out_wav,
        seed=seed,
    )
    return out_wav, sr


if __name__ == '__main__':
    ref_wav, ref_text, gen_text, out_wav = sys.argv[1:5]
    dev = sys.argv[5] if len(sys.argv) > 5 else None
    f5 = load(dev)
    p, sr = say(f5, ref_wav, ref_text, gen_text, out_wav)
    print('已生成', p, sr)
