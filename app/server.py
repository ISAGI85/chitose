r"""千岁的窗口。

一个真的桌面窗口，里面是网页。她站在中间，底下是字幕和两个按钮。

启动：
    python server.py            # 或者双击 D:\chitose\开千岁.bat
说明：
    脑子（DeepSeek 代理）、嗓子（转接头 9882）、耳朵（faster-whisper）都复用
    chitose_chat.py 里那几样，不重复造。
"""

import base64
import io
import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import numpy as np
import soundfile as sf
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import chitose_chat as cc

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, 'web')
PORT = int(os.environ.get('CHITOSE_UI_PORT', '9890'))
SR = 16000

app = FastAPI()
app.mount('/assets', StaticFiles(directory=os.path.join(WEB, 'assets')), name='assets')


@app.middleware('http')
async def _no_store(request, call_next):
    """网页那一层（html/js/css）一律不许缓存。

    **但 /assets 下面放行**——立绘、背景、问候的 wav 一共 6.3M，文件名固定、
    内容不变，让它们缓存着才对；每次都重下会把开窗拖慢。
    """
    r = await call_next(request)
    if not request.url.path.startswith('/assets/'):
        r.headers['Cache-Control'] = 'no-store, must-revalidate'
    return r

HISTORY = []
STATE = {'rec': None, 'stop': None, 'frames': None}
LOCK = threading.Lock()


def _wav_b64(x, sr):
    buf = io.BytesIO()
    sf.write(buf, np.asarray(x, dtype=np.float32).reshape(-1), sr,
             format='WAV', subtype='PCM_16')
    return base64.b64encode(buf.getvalue()).decode('ascii')


def answer(user_text):
    """走一遍：想好 -> （有声时）翻成日语 -> 用她的声音念出来。

    静音版（config.json 里 voice.enabled=false）只走到「想好」，
    audio 给 null，网页照样打字、换表情，不会去等一个不存在的嗓子。
    """
    voice = cc.voice_enabled()
    if voice:
        ensure_voice()                  # 哑了就先把嗓子叫起来（最多等 45 秒）
    cn, jp, mood = cc.ask_llm(HISTORY, user_text)
    audio = None
    if voice and jp:
        try:
            wav = cc.synth(jp)
            x, sr = sf.read(io.BytesIO(wav), dtype='float32')
            if x.ndim > 1:
                x = x.mean(axis=1)
            audio = _wav_b64(x, sr)
        except Exception as e:
            print('  [voice] 这句没合成出来，只打字：%s' % str(e)[:80], flush=True)
    HISTORY.append({'role': 'user', 'content': user_text})
    HISTORY.append({'role': 'assistant', 'content': cn})
    del HISTORY[:-24]   # 保留 12 轮，别让刚才的玩笑太快掉出上下文
    # mood = 这句话的心情（'轻笑'、'害羞' 这些，本来只给嗓子加音效用）。
    # 网页拿它来**换脸**——她说话的时候表情跟着情绪走（宝宝 2026-10-11 定的）。
    return {'cn': cn, 'jp': jp, 'audio': audio, 'mood': mood}


class Say(BaseModel):
    text: str


_LAUNCH = None


def _launch():
    """把 launch_all.py 当模块用——起服务那段逻辑它已经写好了，不再抄一遍。"""
    global _LAUNCH
    if _LAUNCH is None:
        import importlib.util
        p = os.path.join(os.path.dirname(HERE), 'scripts', 'launch_all.py')
        spec = importlib.util.spec_from_file_location('chitose_launch', p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _LAUNCH = mod
    return _LAUNCH


def _start_missing(L):
    try:
        if not L.port_open(L.GSV_PORT):
            print('  [voice] 嗓子不在，拉起来…', flush=True)
            L.start_voice()
        if not L.port_open(L.SHIM_PORT):
            print('  [voice] 转接头不在，拉起来…', flush=True)
            L.start_shim('gsv')
    except Exception as e:
        print('  [voice] 拉不起来：%s' % e, flush=True)


def ensure_voice(wait_s=45):
    """说之前先看嗓子和转接头在不在，不在就拉起来。

    2026-10-25：以前窗口开着、服务被关掉（比如跑过 关千岁.bat）只会报
    「没接上话」。现在第一句会慢一点，但会回。
    只在后台等 wait_s 秒——真起不来的话不把整个窗口吊死，照样让它报错。
    """
    try:
        L = _launch()
    except Exception as e:
        print('  [voice] 找不到 launch_all：%s' % e, flush=True)
        return
    if L.port_open(L.GSV_PORT) and L.port_open(L.SHIM_PORT):
        return
    th = threading.Thread(target=_start_missing, args=(L,), daemon=True)
    th.start()
    th.join(wait_s)



@app.get('/')
def index():
    """把 index.html 读出来，**顺手给 style.css / app.js 挂上版本号**。

    ⚠ 不挂会出事：WebView2 把 `/app.js` 当缓存，姐姐改完前端宝宝看到的还是
    老的那一版——2026-10-11 他就这么撞了一回，明明改好的嘴，他看到的还是
    「表情一直在变、从微笑到哭泣」（那是旧代码在跑）。
    版本号取这两个文件的修改时间，**改一下就自动换一个 URL**，
    浏览器不得不重新下载。以后改前端不用手动升版本号。
    """
    html = io.open(os.path.join(WEB, 'index.html'), encoding='utf-8').read()
    # gaze.js（视线跟随）也是自己写的，一样要挂版本号，不然改了不生效。
    # assets/layers.json 也参加版本计算：素材重建后它会变，app.js 的 URL
    # 跟着变，页面才会重新取 layers.json，再拿到新的素材 version。
    names = [n for n in ('app.js', 'style.css', 'gaze.js')
             if os.path.exists(os.path.join(WEB, n))]
    stamp = names + (['assets/layers.json']
                     if os.path.exists(os.path.join(WEB, 'assets', 'layers.json')) else [])
    try:
        v = int(max(os.path.getmtime(os.path.join(WEB, n)) for n in stamp)) if stamp else 0
    except OSError:
        v = 0
    for n in names:
        html = html.replace('src="%s"' % n, 'src="%s?v=%d"' % (n, v))
        html = html.replace('href="%s"' % n, 'href="%s?v=%d"' % (n, v))
    return HTMLResponse(html, headers={'Cache-Control': 'no-store, must-revalidate'})


@app.post('/api/say')
def api_say(body: Say):
    t = (body.text or '').strip()
    if not t:
        return JSONResponse({'error': '空的'}, status_code=400)
    try:
        return answer(t)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({'error': str(e)}, status_code=500)


# ---- 录音：按住说话 ----


def _record_loop(stop_evt):
    import queue as _q
    import sounddevice as sd
    q = _q.Queue()
    frames = []

    def cb(indata, n, t, status):
        q.put(indata.copy())

    with sd.InputStream(samplerate=SR, channels=1, dtype='float32', callback=cb):
        while not stop_evt.is_set():
            try:
                frames.append(q.get(timeout=0.2))
            except _q.Empty:
                pass
        while not q.empty():
            frames.append(q.get())
    if not frames:
        return np.zeros(0, dtype='float32')
    return np.concatenate(frames, axis=0).reshape(-1)


@app.post('/api/rec/start')
def api_rec_start():
    if not cc.ears_available():
        return JSONResponse(
            {'error': '耳朵没装，先打字聊吧——想装耳朵看 README 的「可选：按住说话」。'},
            status_code=400)
    if STATE['rec'] is not None:
        return {'ok': True, 'already': True}
    stop = threading.Event()
    box = {}

    def run():
        box['audio'] = _record_loop(stop)

    th = threading.Thread(target=run, daemon=True)
    STATE['rec'], STATE['stop'], STATE['frames'] = th, stop, box
    th.start()
    return {'ok': True}


@app.post('/api/rec/stop')
def api_rec_stop():
    if not cc.ears_available():
        return JSONResponse({'error': '耳朵没装，先打字聊吧。'}, status_code=400)
    th = STATE.get('rec')
    if th is None:
        return JSONResponse({'error': '没在录'}, status_code=400)
    STATE['stop'].set()
    th.join(timeout=15)
    audio = STATE['frames'].get('audio', np.zeros(0, dtype='float32'))
    STATE['rec'] = STATE['stop'] = STATE['frames'] = None
    if len(audio) < SR * 0.3:
        return {'heard': '', 'note': '太短了'}
    try:
        text, lang = cc.transcribe(audio)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({'error': str(e)}, status_code=500)
    if not text:
        return {'heard': '', 'note': '没听清'}
    out = answer(text)
    out['heard'] = text
    out['lang'] = lang
    return out


@app.get('/api/status')
def api_status():
    """网页开窗时先看一眼：脑子填了没、耳朵装没装、嗓子开没开。"""
    return {
        'brain': cc.brain_configured(),
        'voice': cc.voice_enabled(),
        'ears': cc.ears_available(),
        'config_path': os.path.join(os.path.dirname(HERE), 'config.json'),
    }


@app.get('/api/ping')
def api_ping():
    return {'ok': True, 'shim': _port(9882)}


# ---- 开场那句问候 ----
#
# **声音是这边放的，不是网页放的。** 网页一打开还没被点过，
# 浏览器不让出声（实测 AudioContext 一建出来就是 suspended），
# 所以问候走 Python 的扬声器；网页拿到一份真实音量曲线，嘴照样跟着动。
#
# 五句问候是**提前合成**好的（scripts/make_greetings.py），点开即响，不等嗓子。

VOICE = os.path.join(WEB, 'assets', 'voice')


def _greet_key():
    """按钟点挑一句问候。

    ⚠ 中午只到 **13 点**为止（原来划到 14 点）。宝宝 2026-10-11：
    「现在是下午了 开机她还是按中午的话来说」——当时 13:45，
    姐姐这边还在说「到中午了哦」。**过了下午一点就该叫下午。**
    """
    h = time.localtime().tm_hour
    if 5 <= h < 11:
        return 'morning'
    if 11 <= h < 13:
        return 'noon'
    if 13 <= h < 18:
        return 'afternoon'
    if 18 <= h < 22:
        return 'evening'
    return 'night'


def _envelope(x, sr, hop_ms=30.0):
    """每 30 毫秒一个音量值（RMS，不归一化，跟前端的阈值对得上）。"""
    hop = max(1, int(sr * hop_ms / 1000.0))
    n = len(x) // hop
    if n <= 0:
        return []
    v = np.abs(np.asarray(x, dtype=np.float32)[:n * hop]).reshape(n, hop)
    rms = np.sqrt((v ** 2).mean(axis=1))
    return [round(float(r), 4) for r in rms]


_HELLO = {}


# 静音版没有预合成的问候声，但话还是要说——用文字打招呼。
GREET_TEXT = {
    'morning': '早上好呀，宝宝睡得好吗？',
    'noon': '到中午啦，宝宝吃饭了没有？',
    'afternoon': '下午啦，宝宝在忙什么呢？',
    'evening': '晚上好呀，宝宝今天过得怎么样？',
    'night': '这么晚还没睡呀，宝宝。',
}


@app.get('/api/hello')
def api_hello():
    """只报「该说哪句」和它的音量曲线，不播放。播放等网页准备好再喊 /api/hello/play。"""
    key = _greet_key()
    if not cc.voice_enabled():
        cn = GREET_TEXT.get(key, '')
        if cn and not HISTORY:
            HISTORY.append({'role': 'assistant', 'content': cn})
        return {'key': key, 'cn': cn, 'jp': '', 'dur': 0.0, 'env': []}
    try:
        g = json.load(open(os.path.join(VOICE, 'greetings.json'), encoding='utf-8'))[key]
    except Exception:
        return {'key': key, 'cn': '', 'jp': '', 'dur': 0.0, 'env': []}
    x, sr = sf.read(os.path.join(VOICE, g['file']), dtype='float32')
    if x.ndim > 1:
        x = x.mean(axis=1)
    _HELLO['a'] = (x, sr)
    # 开场问候也是她说的话：进上下文，宝宝回「嘿嘿」时才知道在接哪句
    if not HISTORY and g.get('cn'):
        HISTORY.append({'role': 'assistant', 'content': g['cn']})
    return {'key': key, 'cn': g['cn'], 'jp': g['jp'],
            'dur': float(len(x)) / sr, 'env': _envelope(x, sr)}


@app.post('/api/hello/play')
def api_hello_play():
    """网页准备好了——现在放。这边一喊就响，所以嘴和声能对上。"""
    a = _HELLO.get('a')
    if not a:
        return {'ok': False}
    x, sr = a
    threading.Thread(target=cc.play, args=(x, sr), daemon=True).start()
    return {'ok': True}


def _port(p):
    import socket
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(('127.0.0.1', p)) == 0


# 网页那一层（style.css / app.js / index.html）。
# 必须注册在**所有路由之后**：/api/* 和上面的 / 先匹配，剩下的才落到这里。
app.mount('/', StaticFiles(directory=WEB, html=True), name='web')


def _warm_ears():
    """窗口一开就把耳朵捂热。

    **不预热的话，宝宝第一次「按住说话」松手要干等十几秒**——实测第一次
    17.9 秒（载 2.9G 模型），热了之后 **0.65 秒**。他自己试的时候会以为卡死了。
    拿半秒静音过一遍就行，识别结果扔掉，只为把模型读进显存。
    """
    try:
        cc.transcribe(np.zeros(int(SR * 0.5), dtype='float32'))
        print('  （耳朵热好了）')
    except Exception:
        import traceback
        traceback.print_exc()


def main():
    # ⚠ 已经开着一个就别再开第二个。第二个会卡在「端口被占」上，
    #   宝宝看到的只是「双击了没反应 / 打不开」（他 2026-10-11 撞过一回）。
    #   自己先说清楚，比让他对着一个闪一下就没的黑窗口猜强。
    if _port(PORT):
        print()
        print('  她已经在开着啦——屏幕上那个窗口就是。')
        print('  要重开的话：先把那个窗口关掉，再双击一次。')
        print()
        return

    import webview
    cfg = uvicorn.Config(app, host='127.0.0.1', port=PORT, log_level='warning')
    srv = uvicorn.Server(cfg)
    threading.Thread(target=srv.run, daemon=True).start()
    # 跟开窗并行地捂耳朵，不挡窗口弹出来。
    # ⚠ 这儿换过好几轮，最后是这样才成的：**GPU + int8**（见 chitose_chat.py 顶上那段）。
    #   宝宝 2026-10-11 说「这个 3g 的耳朵应该可以用」——对的，模型没问题，
    #   是 `int8_float16`（≈3G）塞不进剩下那 2.2G 显存，**卡在载入**，
    #   连累整个界面（背景黑、探针一行都跑不出来，姐姐查了半天）。
    #   改 `int8` 之后：载入 6 秒、识别 0.6 秒、显存 3.8G，全好了。
    # 耳朵没装就不预热——省得黑窗口里刷一堆 import 失败。
    if cc.ears_available():
        threading.Thread(target=_warm_ears, daemon=True).start()
    for _ in range(100):
        if _port(PORT):
            break
        time.sleep(0.05)
    webview.create_window(
        '千岁', 'http://127.0.0.1:%d/' % PORT,
        width=760, height=880, min_size=(560, 640),
        background_color='#241C1E')
    webview.start()


if __name__ == '__main__':
    main()
