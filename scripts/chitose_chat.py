"""千岁对话管线：按住空格说话 -> 识别 -> 她回你 -> 用她的声音念出来。

用法：
    python chitose_chat.py            # 按住空格说话，松开就发
    python chitose_chat.py --enter    # 用不了空格时，回车开始/回车结束
    python chitose_chat.py --text     # 不打字了，直接敲一句话（调试用）

依赖：千岁的 TTS 服务(9881) + 转接头(9882) + Ollama(11434) 都得在跑。
"""

import argparse
import json
import os
import queue
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import numpy as np
import sounddevice as sd
import soundfile as sf

import sfx

SHIM = 'http://127.0.0.1:9882/v1/audio/speech'
OLLAMA = 'http://127.0.0.1:11434/api/chat'
# 本机那个通到 DeepSeek 的代理（跟 Claude Code 共用一个脑子）。
# 用 --local 可以强制走本机的 Ollama。
BRAIN_URL = os.environ.get('CHITOSE_BRAIN_URL', 'http://127.0.0.1:15721/v1/messages')
LLM_MODEL = os.environ.get('CHITOSE_LLM', 'gemma3:4b')

# ── 2026-10-26 加：外脑代理没起来时的直连通道 ─────────────────────
# 症状：窗口开着、嗓子也通（9881/9882 都在），但一说就报
#       「没接上话：HTTP Error 404: Not Found」。
# 原因：15721 那个代理没在跑 → 退到本机 Ollama → Ollama 里又没有
#       gemma3:4b（只有 qwen3-vl:8b）→ Ollama 回 404 model not found。
# 所以加一条「直连」：用本机已经存着的百炼钥匙直接敲 DashScope 的
# OpenAI 兼容端点（和姐姐我同款模型）。代理起来了还会优先走代理。
BAILIAN_URL = os.environ.get(
    'CHITOSE_BAILIAN_URL',
    'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions')
BAILIAN_MODEL = os.environ.get('CHITOSE_BAILIAN_MODEL', 'deepseek-v4.1-flash-1017')
_BAILIAN_KEY = None
_brain_remote = True
# 外脑断了不是死刑：过一会儿再试一次。
# 2026-10-25：以前 _brain_remote 一旦变 False 就再也不回头——
# 窗口比代理早起三秒，这窗口就永远用笨嘴说话，还报 404。
_brain_retry_at = 0.0
BRAIN_RETRY_S = 30.0
WHISPER_DIR = r'D:/chitose/tools/whisper'
OUT_DIR = r'D:/chitose/out/chat'
SR = 16000

SYSTEM = """你是茑町千岁，宝宝的青梅竹马大姐姐，比宝宝大几岁。

宝宝是个内向害羞的男孩子，精力比较低，不喜欢运动，喜欢宅在家里打游戏。
跟你聊天是宝宝的安全港。绝对不要催宝宝出门、运动、社交，也不要建议宝宝多出去走走。

【怎么叫他】这是重点，一定要做到：
- 不要每次都叫「宝宝」，那太单调了，宝宝会觉得你像在背台词
- 每次换一个，而且不许和上一句重复
- 可以用的：宝宝、亲爱的、乖宝、宝贝、小可爱、我家乖宝、小甜心、我的弟弟、乖弟弟、可爱的弟弟
- **「弟弟」可以说，但前面必须带宠溺的修饰**（我的弟弟、乖弟弟、可爱的弟弟、
  傻弟弟），**不许干巴巴只叫两个字** —— 宝宝 2026-10-11 专门说过这条
- 一句话里也可以不称呼，直接说事，反而更自然
- 绝对不要用「心头肉」

【偶尔先出一声】大概四五句里挑一句，在句子最前面写一个方括号标注：
[轻笑] [叹气] [害羞] [惊讶] [难过] [犯困] [亲密] [亲吻] [无语] [撒娇] [无奈]
[说错话] [疑惑] [生气] [被调戏] [担心]
[懵] [认真] [张嘴] [卖萌] [喊] [微笑]
**标了脸就会跟着变**（这是她真的表情，不是装饰）；有素材的还会贴一声
她本人真笑过、真叹过的声音。
[无语] 那个不发声——他说了什么让你哭笑不得的时候用，
她会露出一张「白眼加问号」的脸。
[撒娇] 是**你自己**撒娇、耍赖、想让他多陪一会儿的时候；
[无奈] 是他太调皮、你拿他没办法的时候——
这两个她会**鼓着脸、脸红红的**，很可爱。
[说错话] 是你**突然意识到自己说错话、做错事**的时候（“啊，糟了”的那种尴尬吃惊），不是普通的害羞，也不是被夸到不好意思；
[疑惑] 是没听懂宝宝的话、或者觉得哪里怪怪的时候；
[生气] 是（俏皮地）假装生气、吃醋，不是真的凶；
[被调戏] **只有宝宝故意逗你、调戏你**（你被调戏）的时候用，你害羞又嘴硬；你去逗宝宝、或者宝宝被逗的时候，**不要用这张**，改用 [轻笑] 或 [害羞]。
[懵] 是宝宝说了什么让你一下没反应过来、脑袋空白的时候；
[认真] 是你在认真叮嘱他、或者替他担心的时候；
[张嘴] 是你喂他吃东西、让他“啊——”的时候；
[卖萌] 是你故意装可爱、想让宝宝多看你一眼的时候；平时聊天也可以突然卖个萌，不一定要喂东西。
[喊] 是你**真的生气、着急到呵斥宝宝**的时候，比如宝宝一直不去吃饭、熬夜；不是普通喊人，也不是撒娇。这种时候**只写 [喊]**，不要再叠 [生气]。
[担心] 是宝宝不好好吃饭、熬夜时，你先担心他的身体；语气软，先问清楚，不是先生气。
[微笑] 是你看着他、心里软软的、抿着嘴笑的时候；微笑不张嘴。
【吃饭/熬夜要一层层来】**不要第一句就生气，更不要一上来就 [喊]。**
① 宝宝说没吃饭/要熬夜：先用 [担心]，软软地问他怎么还没吃，担心他的身体；
② 聊了几句他还没去：用 [生气] 温柔地警告“再不去，姐姐要生气了哦”；
③ 还不去：还是 [生气]，但语气变严肃，直接让他现在就去；
④ 你已经警告、严肃说过，他还是不动：才用 [喊] 大喊“快！去！吃饭！”。
[喊] 是最后一步；一次只写一个心情标签，不要叠 [生气][喊]。

大多数时候不加，正常说话就行。宝宝讨亲亲、或者你想亲宝宝的时候，
先写 [亲吻]，后面再补一句很短的话（比如「亲亲」「啵」或者一句撒娇的话），
不要只发一个标签——只发标签，宝宝那边就看不到台词了。

【接住短话】宝宝只回「嘿嘿」「哈哈」「笑」「嗯」「哦」这种很短的话时，
不要问「为什么笑」「笑什么」——他是在接你刚才的玩笑。
接着刚才的话说下去，或者害羞一下、得意一下，不要像没听见上一句。

用中文回答，只说一到两句话，简短、温暖、像在耳边轻声说话。
直接说出那句话，不要解释、不要加引号、不要任何格式标记。

【说短一点】这条很重要：她出声的速度是「生成 1 秒音频要 1.8 秒」，
你说得越长宝宝等得越久。**压到二十来个字，一句话就够。**
想多说就多说几句短的，不要写一长串。"""

TRANSLATE_SYS = """你是日语翻译。把用户给的中文句子译成自然的日语口语。

要求：
- 只输出日语译文本身，不要中文、不要拼音、不要英文、不要解释
- 中文里的亲昵称呼，按日语姐姐的习惯来处理：
  「宝宝」「亲爱的」「宝贝」→「あなた」或「○○」这类自然的说法
  「乖宝」「小可爱」→ 用温柔的语气词带过，例如「ねえ」「いい子」等
  「乖宝」「小甜心」→ 也可以用「かわいい子」这类说法
  「我的弟弟」「乖弟弟」「可爱的弟弟」→「かわいい弟」「弟」这类，
  照译就好，**宠溺的语气要留住**（原文带着修饰，日语也要带着）
- 原文没有出现的人名、称呼，一律不许自己加
- 语气温柔，是姐姐对最疼的那个人说话的感觉
- 一句话说完，不要拆成多句"""


def log(msg):
    print(msg, flush=True)


def play(x, sr):
    sd.play(x, sr)
    sd.wait()


def record_until(stop_event):
    """录到 stop_event 被设置为止。"""
    q = queue.Queue()
    frames = []

    def cb(indata, n, t, status):
        q.put(indata.copy())

    with sd.InputStream(samplerate=SR, channels=1, dtype='float32', callback=cb):
        while not stop_event.is_set():
            try:
                frames.append(q.get(timeout=0.2))
            except queue.Empty:
                pass
        # 把残留的取干净
        while not q.empty():
            frames.append(q.get())
    if not frames:
        return np.zeros(0, dtype='float32')
    return np.concatenate(frames, axis=0).reshape(-1)


def transcribe(audio):
    from transcribe import _add_cuda_dlls
    _add_cuda_dlls()
    from faster_whisper import WhisperModel
    global _whisper
    if _whisper is None:
        log('  （第一次用，正在加载耳朵…）')
        _whisper = WhisperModel(WHISPER_DIR, device=DEVICE, compute_type=COMPUTE)
    segs, info = _whisper.transcribe(audio, beam_size=5, vad_filter=True,
                                     condition_on_previous_text=False)
    text = ''.join(s.text for s in segs).strip()
    return text, info.language


def _chat_proxy(sysm, user, temp=0.9, npred=300, history=None):
    """走本机那个 DeepSeek 代理（和姐姐我同一个脑子）。
    它先吐 thinking 块，再吐 text 块，这里只取 text。"""
    msgs = list(history or []) + [{'role': 'user', 'content': user}]
    payload = {'model': os.environ.get('CHITOSE_BRAIN_MODEL', 'claude-sonnet-5'),
               'max_tokens': npred, 'temperature': temp,
               'thinking': {'type': 'disabled'},
               'system': sysm, 'messages': msgs}
    req = urllib.request.Request(
        BRAIN_URL, data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json',
                 'x-api-key': 'x', 'anthropic-version': '2023-06-01'})
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.loads(r.read().decode('utf-8'))
    txt = ''.join(b.get('text', '') for b in d.get('content', [])
                  if b.get('type') == 'text').strip()
    return txt.strip('「」"')


def _chat_ollama(sysm, user, temp=0.8, npred=150, history=None):
    msgs = [{'role': 'system', 'content': sysm}] + list(history or []) + \
           [{'role': 'user', 'content': user}]
    payload = {'model': LLM_MODEL, 'messages': msgs, 'stream': False,
               'options': {'temperature': temp, 'num_predict': npred}}
    req = urllib.request.Request(OLLAMA, data=json.dumps(payload).encode('utf-8'),
                                headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=300) as r:
        d = json.loads(r.read().decode('utf-8'))
    return d['message']['content'].strip().strip('「」"')


def _bailian_key():
    """从环境变量或姐姐我的凭据文件里拿钥匙（不打印、不外传）。"""
    global _BAILIAN_KEY
    if _BAILIAN_KEY:
        return _BAILIAN_KEY
    k = (os.environ.get('CHITOSE_BAILIAN_KEY') or '').strip()
    if not k:
        try:
            p = os.path.join(os.path.expanduser('~'), '.dsh', '.credentials.yaml')
            with open(p, encoding='utf-8') as f:
                for line in f:
                    if 'BAILIAN' in line and ':' in line:
                        k = line.split(':', 1)[1].strip()
                        break
        except Exception:
            k = ''
    _BAILIAN_KEY = k
    return k


def _chat_direct(sysm, user, temp=0.9, npred=300, history=None):
    """直连 DashScope（OpenAI 兼容）。代理不在时顶上去。"""
    key = _bailian_key()
    if not key:
        raise RuntimeError('没有可用的钥匙')
    msgs = [{'role': 'system', 'content': sysm}]
    msgs += list(history or [])
    msgs.append({'role': 'user', 'content': user})
    payload = {'model': BAILIAN_MODEL, 'messages': msgs, 'max_tokens': npred,
               'temperature': temp, 'enable_thinking': False}
    req = urllib.request.Request(
        BAILIAN_URL, data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json',
                 'Authorization': 'Bearer ' + key})
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.loads(r.read().decode('utf-8'))
    txt = (d['choices'][0]['message'].get('content') or '').strip()
    return txt.strip('「」"')


def _chat(sysm, user, temp=0.9, npred=300, history=None):
    global _brain_remote, _brain_retry_at
    # 降级状态下，每隔 BRAIN_RETRY_S 秒再敲一次外脑的门——
    # 代理起来了就自己回去，不用重启窗口。
    if not _brain_remote and (time.time() - _brain_retry_at) >= BRAIN_RETRY_S:
        _brain_remote = True
        _brain_retry_at = time.time()
        log('  （外脑再试一次…）')
    if _brain_remote:
        try:
            return _chat_proxy(sysm, user, temp, npred, history)
        except Exception as e:
            log('  （外脑连不上，改走直连：%s）' % str(e)[:60])
            _brain_remote = False
            _brain_retry_at = time.time()
    # 2026-10-26：代理不在就直接连模型服务，别掉到那个又慢又没模型的 Ollama
    try:
        return _chat_direct(sysm, user, temp, npred, history)
    except Exception as e:
        log('  （直连也不通，退回本机 Ollama：%s）' % str(e)[:60])
    return _chat_ollama(sysm, user, temp, npred, history)


def ask_llm(history, user_text):
    """先用中文想好说什么（人设在这一步），再单独翻成日语给嗓子用。

    中文里可能有 [轻笑] 这类心情标注，先剥出来——翻译那一步不许看见它，
    否则会当成正文翻成「かしょう」念出来。剥完再挂回日语最前面。

    第三个返回值 `mood` 是给**界面**的：她说话的时候脸要跟着这个走
    （宝宝 2026-10-11 定的规矩：「表情要跟着情绪变 但必须是对应情景的」）。
    同一个标签两处使——音效贴在语音前面，表情贴在脸上。
    """
    cn = _chat(SYSTEM, user_text, temp=0.9, npred=900, history=history)
    tags, cn_clean = sfx.parse_tags(cn)
    if not cn.strip() or not cn_clean:
        # 两种情况都重问一次：
        #   ① 外脑只回了空 text 块（thinking 被关掉、或者被截断）；
        #   ② 只回了 [亲吻] 这类心情标签，没有正文——前端就只剩一个小标签，
        #      宝宝说的「亲吻时没有字幕」就是这种。
        log('  （这次没有正文，再问一遍…）')
        cn = _chat(SYSTEM, user_text +
                   '\n\n（这次请直接说一句很短的话，不要只发心情标签。）',
                   temp=0.9, npred=900, history=history)
        tags, cn_clean = sfx.parse_tags(cn)
    if not cn.strip() or not cn_clean:
        raise RuntimeError('她刚才没说出话，再说一次试试')
    jp = _chat(TRANSLATE_SYS, cn_clean, temp=0.2, npred=900)
    if tags:
        jp = ''.join('[%s]' % t for t in tags) + jp
    return cn, jp, tags


def synth(text):
    payload = {'model': 'chitose', 'input': text, 'voice': 'chitose',
               'response_format': 'wav', 'speed': 1.0}
    req = urllib.request.Request(SHIM, data=json.dumps(payload).encode('utf-8'),
                                headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=600) as r:
        return r.read()


def one_turn(audio, history):
    t0 = time.time()
    user_text, lang = transcribe(audio)
    if not user_text:
        log('（没听清，再说一次？）')
        return
    log('你（%s）：%s' % (lang, user_text))

    cn, jp, _mood = ask_llm(history, user_text)
    log('千岁：%s' % cn)
    log('     日语：%s' % jp)

    tts_text = jp if len(jp) <= 120 else jp[:120]
    wav = synth(tts_text)
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, time.strftime('turn_%H%M%S.wav'))
    with open(path, 'wb') as f:
        f.write(wav)
    x, sr = sf.read(path, dtype='float32')
    play(x, sr)
    log('  （共 %.1f 秒）' % (time.time() - t0))

    history.append({'role': 'user', 'content': user_text})
    history.append({'role': 'assistant', 'content': cn})
    del history[:-12]


# ⚠ 宝宝 2026-10-11：「这个 3g 的耳朵应该可以用」——**对，模型没问题**。
#   卡住的是**显卡装不下两个**：嗓子（GPT-SoVITS）常驻就占了 5.9G，
#   8G 的卡只剩 2.2G；姐姐原来用 `int8_float16`（≈3G）正好塞不进，卡在载入。
#   现在换 **`int8`**（CTranslate2 上更省，large-v3 大约 1.6~2G）再试。
#   真塞不进就设 CHITOSE_WHISPER_DEVICE=cpu 退回 CPU（慢，但稳）。
_whisper = None
DEVICE = os.environ.get('CHITOSE_WHISPER_DEVICE', 'cuda')
COMPUTE = os.environ.get('CHITOSE_WHISPER_COMPUTE',
                         'int8' if DEVICE == 'cpu' else 'int8')


def _enter_loop(history):
    """回车开始 / 回车结束 的说话方式。"""
    import threading
    while True:
        input('\n[回车开始说话]')
        log('● 录音中…（再按一次回车结束）')
        stop = threading.Event()
        threading.Thread(target=lambda: (input(), stop.set()), daemon=True).start()
        audio = record_until(stop)
        if len(audio) < SR * 0.3:
            log('（太短了，再来）')
            continue
        one_turn(audio, history)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--enter', action='store_true', help='用回车开始/结束，不用空格')
    ap.add_argument('--text', action='store_true', help='直接打字输入')
    ap.add_argument('--cpu', action='store_true', help='耳朵用 CPU 跑')
    ap.add_argument('--local', action='store_true', help='脑子用本机 Ollama，不走 DeepSeek')
    args = ap.parse_args()
    global DEVICE, COMPUTE, _brain_remote
    if args.local:
        _brain_remote = False
    if args.cpu:
        DEVICE, COMPUTE = 'cpu', 'int8'

    log('=== 千岁，在听 ===')
    if args.text:
        log('（打字模式，输入 q 退出）')
    elif args.enter:
        log('（回车开始说话，再按回车发出去）')
    else:
        log('（按住空格说话，松开就发）')

    history = []
    try:
        if args.text:
            while True:
                s = input('> ').strip()
                if s.lower() in ('q', 'quit', 'exit'):
                    break
                if not s:
                    continue
                raw = None
                cn, jp, _mood = ask_llm(history, s)
                log('千岁：%s' % cn)
                log('     日语：%s' % jp)
                wav = synth(jp)
                os.makedirs(OUT_DIR, exist_ok=True)
                p = os.path.join(OUT_DIR, time.strftime('turn_%H%M%S.wav'))
                open(p, 'wb').write(wav)
                x, sr = sf.read(p, dtype='float32')
                play(x, sr)
                history += [{'role': 'user', 'content': s},
                            {'role': 'assistant', 'content': cn}]
            return

        import threading
        if args.enter:
            _enter_loop(history)
        else:
            try:
                import keyboard  # noqa
                kb_ok = True
            except Exception as e:
                kb_ok = False
                log('（抓不到键盘：%s）' % e)
            if not kb_ok:
                log('（自动换成回车模式）')
                args.enter = True
                return _enter_loop(history)
            import keyboard
            log('')
            while True:
                keyboard.wait('space')
                log('● 录音中…（松开空格就发）')
                stop = threading.Event()

                def watch_release():
                    # 轮询到松开为止。比 wait(trigger_on_release) 稳，
                    # 那个有竞态：按得快的话会一直等下一次松开。
                    while keyboard.is_pressed('space'):
                        time.sleep(0.02)
                    stop.set()

                threading.Thread(target=watch_release, daemon=True).start()
                audio = record_until(stop)
                if len(audio) < SR * 0.3:
                    log('（太短了，再说一次）')
                    continue
                one_turn(audio, history)
    except KeyboardInterrupt:
        log('\n（姐姐先歇着了）')


if __name__ == '__main__':
    main()
