"""调用 GPT-SoVITS 的 API 合成语音。

用法：
    python gsv_say.py <参考wav> <参考文本> <参考语种> <要说的文本> <目标语种> <输出wav>
"""

import json
import os
import sys
import urllib.request

API = 'http://127.0.0.1:%s/' % os.environ.get('GSV_PORT', '9880')


def tts(text, out, ref_wav, ref_text, ref_lang='ja', text_lang='zh',
        top_k=15, top_p=0.9, temperature=0.7, speed=1.0):
    payload = {
        'refer_wav_path': ref_wav,
        'prompt_text': ref_text,
        'prompt_language': ref_lang,
        'text': text,
        'text_language': text_lang,
        'top_k': top_k,
        'top_p': top_p,
        'temperature': temperature,
        'speed': speed,
        'cut_punc': '，。！？；',
        'sample_steps': 32,
        'if_sr': False,
    }
    req = urllib.request.Request(
        API,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
    )
    with urllib.request.urlopen(req, timeout=900) as r:
        data = r.read()
    with open(out, 'wb') as f:
        f.write(data)
    return len(data)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    ref_wav, ref_text, ref_lang, text, text_lang, out = sys.argv[1:7]
    n = tts(text, out, ref_wav, ref_text, ref_lang, text_lang)
    print('已生成 %s (%d 字节)' % (out, n))
