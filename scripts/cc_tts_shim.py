"""把 GPT-SoVITS 伪装成 OpenAI 的 /v1/audio/speech 接口。

cc-connect 的 [tts] 支持自定义 base_url，配上这个转接头，
微信里收到的语音条就是千岁本人的声音。

启动：
    python cc_tts_shim.py            # 默认 127.0.0.1:9882

依赖：同机跑着 GPT-SoVITS 的 api.py（默认 127.0.0.1:9881）
"""

import io
import json
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import numpy as np
import soundfile as sf

from tighten import tighten
import sfx

GSV_API = os.environ.get('GSV_API', 'http://127.0.0.1:9881/')
PORT = int(os.environ.get('SHIM_PORT', '9882'))
HOST = os.environ.get('SHIM_HOST', '127.0.0.1')

# 参考音频。用她轻声安慰的那句当默认，出来最沉稳。
#
# 为什么要有好几条：GPT-SoVITS 的语气是**从参考音频带过来的**。
# 拿平静的参考去合成，出来一律平静——标了 [轻笑] 声音是笑过了，
# 后面那句话还是平的，宝宝一听就说「语气没跟上」。
# 所以按心情换参考：开心的事用她念「やった！」那条，语气自然就亮。
# 2026-10-10 宝宝在四条候选里挑的第 1（平静）和第 3（轻快）。
REFS = {
    '平静': (os.environ.get('GSV_REF',
                          r'D:/chitose/ref_wav/calm/CC_02_cit_mo_05_003.wav'),
             os.environ.get('GSV_REF_TEXT', 'うん、大丈夫、難しいことじゃないから。'),
             'ja'),
    '开心': (r'D:/chitose/ref_wav/cheer/cheer_01.wav',
             'やった!それじゃあ早速するね', 'ja'),
}
# 心情标注 -> 用哪条参考。没列到的（叹气/难过…）先用平静的，
# 等宝宝听过别的候选再往上挂。
TAG_MOOD = {
    '轻笑': '开心',
    '惊讶': '开心',
}
DEFAULT_MOOD = '平静'

REF_WAV, REF_TEXT, REF_LANG = REFS[DEFAULT_MOOD]
TEXT_LANG = os.environ.get('GSV_TEXT_LANG', 'ja')
TEMPERATURE = float(os.environ.get('GSV_TEMPERATURE', '0.7'))
TOP_K = int(os.environ.get('GSV_TOP_K', '15'))
TOP_P = float(os.environ.get('GSV_TOP_P', '0.9'))


def merge_short(text, min_len=9):
    """按标点断开后，把太短的片段和后面的拼起来。

    切太碎的话，GPT-SoVITS 会把只有两三个字的段直接忽略
    （数数时「1、」「2、」就是这么掉的）；全不切又会在长串里漏字。
    所以：切，但保证每段够长。
    """
    import re
    parts = re.split(r'(?<=[。？！、])', text)
    out = []
    buf = ''
    for p in parts:
        if not p:
            continue
        buf += p
        if len(buf) >= min_len:
            out.append(buf)
            buf = ''
    if buf:
        if out:
            out[-1] += buf
        else:
            out.append(buf)
    return '\n'.join(out)


def _gsv(text, speed=1.0, mood=DEFAULT_MOOD):
    """光把字念出来，返回 (波形, 采样率)。标签已经在外面剥掉了。"""
    ref_wav, ref_text, ref_lang = REFS.get(mood, REFS[DEFAULT_MOOD])
    payload = {
        'refer_wav_path': ref_wav,
        'prompt_text': ref_text,
        'prompt_language': ref_lang,
        'text': merge_short(text),
        'text_language': TEXT_LANG,
        # 这里不切，交给 merge_short 分好行，api 只会按换行分段
        'cut_punc': '',
        'top_k': TOP_K,
        'top_p': TOP_P,
        'temperature': TEMPERATURE,
        'speed': speed,
        'sample_steps': 32,
        'if_sr': False,
    }
    req = urllib.request.Request(
        GSV_API,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
    )
    with urllib.request.urlopen(req, timeout=900) as r:
        raw = r.read()
    # 切得碎，段间会插静音，这里再收回来一点，免得听着喘
    x, sr = sf.read(io.BytesIO(raw), dtype='float32', always_2d=True)
    x, n, saved = tighten(x, sr, ratio=0.4, max_gap=0.22)
    return x, sr


def synth(text, speed=1.0):
    # [轻笑] 这类标注剥出来，换成她本人那一声
    tags, body = (sfx.parse_tags(text) if sfx.has_library() else ([], text))
    # 语气也跟着走：标了 [轻笑] 就用开心的参考音频合成正文，
    # 不然声音笑过了、后面那句还是平的。
    mood = DEFAULT_MOOD
    for t in tags:
        if t in TAG_MOOD:
            mood = TAG_MOOD[t]
            break
    if tags:
        print('[shim] 心情「%s」-> 参考 %s'
              % (mood, os.path.basename(REFS[mood][0])), flush=True)

    speech = None
    if body.strip():
        try:
            speech = _gsv(body, speed, mood)
        except Exception as e:
            if not tags:
                raise
            print('[shim] 合成失败，只出声音：%s' % e, flush=True)

    if tags:
        x, sr = sfx.splice(tags, speech[0] if speech else None,
                           speech[1] if speech else None)
        if x is None:
            return b''
    elif speech:
        x, sr = speech
    else:
        return b''

    buf = io.BytesIO()
    sf.write(buf, x, sr, format='WAV', subtype='PCM_16')
    return buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):
        print('[shim] ' + (fmt % args), flush=True)

    def _send(self, code, body, ctype='application/json'):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip('/') in ('', '/health'):
            self._send(200, json.dumps({'ok': True, 'voice': 'chitose'}).encode())
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
        speed = float(req.get('speed') or 1.0)
        if speed <= 0:
            speed = 1.0
        print('[shim] 合成 %d 字，语速 %.2f：%s' % (len(text), speed, text[:40]), flush=True)
        try:
            audio = synth(text, speed)
        except urllib.error.URLError as e:
            self._send(503, json.dumps({'error': 'GPT-SoVITS unreachable: %s' % e}).encode())
            return
        except Exception as e:
            self._send(500, json.dumps({'error': str(e)}).encode())
            return
        print('[shim] -> %d 字节' % len(audio), flush=True)
        self._send(200, audio, 'audio/wav')


if __name__ == '__main__':
    print('转接头启动：%s:%d  ->  %s' % (HOST, PORT, GSV_API), flush=True)
    print('参考音频：%s' % REF_WAV, flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
