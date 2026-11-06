r"""用 Qwen3-TTS 当嘴。对外提供跟 cc_tts_shim.py 一模一样的 OpenAI 接口，
所以 chitose_chat.py 一个字都不用改。

跟老那套（GPT-SoVITS）的区别：
  老：拿她 2632 条语音微调过，音色是「长在」模型里的
  新：通用模型，拿她 3 秒音频现场克隆。宝宝 2026-10-10 听完 A/B 说
      新的「平静」那条更像她，所以换过来了。

启动：
    python qwen_tts_shim.py            # 默认 127.0.0.1:9882
依赖：
    本地模型 D:/chitose/tools/Qwen3-TTS-12Hz-1.7B-Base（4.23 G）
"""

import io
import json
import os
import sys
import threading
import time
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
os.environ.setdefault('HF_ENDPOINT', 'https://hf-mirror.com')

import numpy as np
import soundfile as sf
import torch

import sfx

MODEL_DIR = os.environ.get('QWEN_TTS_DIR',
                           r'D:/chitose/tools/Qwen3-TTS-12Hz-1.7B-Base')
# 参考音频。宝宝挑的就是这条（平静），别乱换。
REF_WAV = os.environ.get('QWEN_REF',
                         r'D:/chitose/ref_wav/calm/CC_02_cit_mo_05_003.wav')
REF_TEXT = os.environ.get('QWEN_REF_TEXT', 'うん、大丈夫、難しいことじゃないから。')
LANG = os.environ.get('QWEN_LANG', 'Japanese')
PORT = int(os.environ.get('SHIM_PORT', '9882'))
HOST = os.environ.get('SHIM_HOST', '127.0.0.1')

_model = None
_prompt = None
_lock = threading.Lock()


def _load_ref():
    x, sr = sf.read(REF_WAV, dtype='float32')
    if x.ndim > 1:
        x = x.mean(axis=1)
    # 游戏的 ogg 峰值会超过 1.0，喂进去会报警，先压一下
    pk = float(np.abs(x).max())
    if pk > 0.99:
        x = x * (0.99 / pk)
    return np.asarray(x, dtype=np.float32), sr


def load():
    global _model, _prompt
    from qwen_tts import Qwen3TTSModel
    print('[qwen] 载入模型…', flush=True)
    t0 = time.time()
    _model = Qwen3TTSModel.from_pretrained(
        MODEL_DIR, device_map='cuda:0', dtype=torch.bfloat16,
        # 默认那个注意力实现很慢（日志里一直喊 flash-attn 没装）。
        # sdpa 是 PyTorch 自带的快速注意力，不用额外装东西。
        attn_implementation=os.environ.get('QWEN_ATTN', 'sdpa'))
    print('[qwen] 载入用了 %.0f 秒' % (time.time() - t0), flush=True)
    x, sr = _load_ref()
    _prompt = _model.create_voice_clone_prompt(ref_audio=(x, sr), ref_text=REF_TEXT)
    print('[qwen] 声纹建好了（参考 %.2f 秒）' % (len(x) / sr), flush=True)


def say(text):
    """出声。返回 (波形, 采样率)。"""
    with _lock:
        wavs, sr = _model.generate_voice_clone(
            text=text, language=LANG, voice_clone_prompt=_prompt)
    return np.asarray(wavs[0], dtype=np.float32).reshape(-1), sr


def synth(text):
    tags, body = (sfx.parse_tags(text) if sfx.has_library() else ([], text))
    if not body.strip() and not tags:
        return b''
    speech = say(body) if body.strip() else None
    if tags:
        x, sr = sfx.splice(tags, speech[0] if speech else None,
                           speech[1] if speech else None)
        if x is None:
            return b''
    else:
        x, sr = speech
    buf = io.BytesIO()
    sf.write(buf, x, sr, format='WAV', subtype='PCM_16')
    return buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *a):
        print('[qwen] ' + (fmt % a), flush=True)

    def _send(self, code, body, ctype='application/json'):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip('/') in ('', '/health'):
            self._send(200, json.dumps({'ok': True, 'voice': 'chitose',
                                        'engine': 'qwen3-tts'}).encode())
        else:
            self._send(404, b'{"error":"not found"}')

    def do_POST(self):
        path = self.path.split('?')[0].rstrip('/')
        if path not in ('/v1/audio/speech', '/audio/speech'):
            self._send(404, b'{"error":"not found"}')
            return
        try:
            n = int(self.headers.get('Content-Length', '0'))
            req = json.loads(self.rfile.read(n).decode('utf-8'))
        except Exception as e:
            self._send(400, json.dumps({'error': 'bad request: %s' % e}).encode())
            return
        text = (req.get('input') or '').strip()
        if not text:
            self._send(400, b'{"error":"empty input"}')
            return
        print('[qwen] 合成 %d 字：%s' % (len(text), text[:40]), flush=True)
        t0 = time.time()
        try:
            audio = synth(text)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._send(500, json.dumps({'error': str(e)}).encode())
            return
        if not audio:
            self._send(500, b'{"error":"empty audio"}')
            return
        print('[qwen] -> %d 字节（%.1f 秒）' % (len(audio), time.time() - t0),
              flush=True)
        self._send(200, audio, 'audio/wav')


if __name__ == '__main__':
    load()
    print('Qwen3-TTS 转接头启动：%s:%d' % (HOST, PORT), flush=True)
    print('参考音频：%s' % REF_WAV, flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
