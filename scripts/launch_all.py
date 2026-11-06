r"""一键把千岁叫起来。

以前要开三个东西：嗓子(GPT-SoVITS, 9881)、转接头(9882)、对话。
这个脚本把它们串起来，已经开着的就跳过。

用法：
    python launch_all.py            # 按住空格说话
    python launch_all.py --text     # 打字
    python launch_all.py --enter    # 回车模式
    python launch_all.py --stop     # 把嗓子和转接头关掉
    python launch_all.py --check    # 只把服务拉起来，再合成一句试试
"""

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# 谁在跑这个脚本就用谁的 python——宝宝用的是 venv，别人也一样。
VENV_PY = sys.executable


def _find_gsv():
    """找 GPT-SoVITS 整合包。

    顺序：环境变量 CHITOSE_GSV_DIR > tools/ 下以 GPT-SoVITS 开头的目录。
    这样整合包叫 `GPT-SoVITS-v2pro` 还是宝宝这个长名字都能认出来。
    """
    p = (os.environ.get('CHITOSE_GSV_DIR') or '').strip()
    if p and os.path.isdir(p):
        return p
    tools = os.path.join(ROOT, 'tools')
    if os.path.isdir(tools):
        for n in sorted(os.listdir(tools)):
            d = os.path.join(tools, n)
            if n.lower().startswith('gpt-sovits') and os.path.isdir(d):
                return d
    return os.path.join(tools, 'GPT-SoVITS-v2pro')


def _find_weight(subdir, pattern, default):
    """权重文件可以改名，按通配找；找不到再退回原来的文件名。"""
    import glob
    hits = sorted(glob.glob(os.path.join(GSV, subdir, pattern)))
    if hits:
        return os.path.relpath(hits[0], GSV)
    return os.path.join(subdir, default)


def _voice_enabled():
    """这台机器要不要出声（和 chitose_chat.voice_enabled 同一套规则）。"""
    env = (os.environ.get('CHITOSE_VOICE') or '').strip().lower()
    if env in ('off', '0', 'false', 'no'):
        return False
    if env in ('on', '1', 'true', 'yes'):
        return True
    try:
        import json
        with open(os.path.join(ROOT, 'config.json'), encoding='utf-8') as f:
            v = (json.load(f) or {}).get('voice') or {}
        return v.get('enabled') is not False
    except Exception:
        return True


GSV = _find_gsv()
GSV_PY = os.path.join(GSV, 'runtime', 'python.exe')
SOVITS = _find_weight('SoVITS_weights_v2Pro', 'chitose*.pth', 'chitose_e10_s6600.pth')
GPT = _find_weight('GPT_weights_v2Pro', 'chitose*.ckpt', 'chitose-e9.ckpt')
GSV_PORT, SHIM_PORT = 9881, 9882
NEW_CONSOLE = 0x00000010        # 让服务各自开一个窗口，出错能看见


def port_open(p):
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(('127.0.0.1', p)) == 0


def wait_port(p, timeout, label):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if port_open(p):
            print('  %s 起来了（%.0f 秒）' % (label, time.time() - t0))
            return True
        time.sleep(1)
    return False


def pid_on(p):
    out = subprocess.run(['netstat', '-ano'], capture_output=True, text=True,
                         errors='replace').stdout
    for line in out.splitlines():
        f = line.split()
        if len(f) >= 5 and f[0].upper() == 'TCP' and f[3] == 'LISTENING' \
                and f[1].endswith(':%d' % p):
            return int(f[-1])
    return None


_CMD_CACHE = {}


def proc_cmdline(pid):
    """拿一个进程的完整命令行。拿不到（权限不够/进程没了）就返回 None。

    先用 psutil（venv 里就有，快、不用起 shell）；没有再退回 powershell CIM。
    2026-10-25：在这台机器上 powershell 那条路是被挡住的，所以 psutil 必须排第一。
    """
    if not pid:
        return None
    if pid in _CMD_CACHE:
        return _CMD_CACHE[pid]

    line = None
    try:
        import psutil
        try:
            line = ' '.join(psutil.Process(pid).cmdline()) or None
        except Exception:
            line = None
    except ImportError:
        pass

    if not line:
        script = ('(Get-CimInstance Win32_Process -Filter "ProcessId=%d").CommandLine' % pid)
        for exe in ('powershell', 'pwsh'):
            try:
                r = subprocess.run(
                    [exe, '-NoProfile', '-NonInteractive', '-Command', script],
                    capture_output=True, text=True, errors='replace', timeout=20)
            except Exception:
                continue
            out = (r.stdout or '').strip()
            if r.returncode == 0 and out:
                line = out.splitlines()[0].strip()
                break

    _CMD_CACHE[pid] = line
    return line


def looks_like(port, tokens, label):
    """端口开着时，确认里面蹲的确实是我们的东西。

    True  = 认出来了，是自己
    None  = 看不清（那就当它是，别拦人）
    False = 明确是别人

    只在「明确认错人」时拦下来——宁可放过，也不误杀本来就好的环境。
    """
    pid = pid_on(port)
    line = proc_cmdline(pid)
    if not line:
        return None
    low = line.lower()
    if any(t.lower() in low for t in tokens):
        return True
    print('  ⚠ 端口 %d 上蹲着的不是%s（PID %s）' % (port, label, pid))
    print('     它跑的是：%s' % line[:180])
    print('     接着用它会说错声音。要接管，先双击「关千岁.bat」，再重新开。')
    return False


def weights_ok():
    return (os.path.exists(os.path.join(GSV, SOVITS))
            and os.path.exists(os.path.join(GSV, GPT)))


def diagnose(label, port):
    """启动失败时，把最常见的原因一条条念出来，别让人去猜黑窗口。"""
    print()
    print('=== 有东西没起来，我看看是哪一环 ===')
    print('  卡在：%s（端口 %d）' % (label, port))

    pid = pid_on(port)
    print('  · 端口上有人吗：%s' % ('有，PID %s' % pid if pid else '没人，说明它压根没起来'))

    smi = shutil.which('nvidia-smi')
    if not smi:
        print('  · 显卡：找不到 nvidia-smi。驱动没装好，GPT-SoVITS 起不来很正常')
    else:
        try:
            r = subprocess.run(
                [smi, '--query-gpu=name,memory.used,memory.total', '--format=csv,noheader'],
                capture_output=True, text=True, errors='replace', timeout=20)
            out = (r.stdout or '').strip()
            print('  · 显卡：%s' % (out.replace('\n', ' / ') if out else 'nvidia-smi 没报出卡来'))
        except Exception as e:
            print('  · 显卡：查不动（%s）' % str(e)[:80])

    for p, what in ((GSV_PY, '嗓子的 python'), (VENV_PY, 'venv 的 python')):
        print('  · %s：%s' % (what, '在' if os.path.exists(p) else '不见了！'))
    print('  · 模型权重：%s' % ('在' if weights_ok() else '不见了！'))

    print()
    print('下一步：')
    print('  1) 去看那个自己弹出来的黑窗口，最后几行就是真原因')
    print('  2) 想确认服务和模型通不通：python scripts\\launch_all.py --check')
    print('  3) 想全关干净重来：双击「关千岁.bat」')


def kill_port(p, label):
    pid = pid_on(p)
    if not pid:
        print('  %s 本来就没开' % label)
        return
    subprocess.run(['taskkill', '/PID', str(pid), '/F'],
                   capture_output=True)
    print('  关掉 %s（PID %d）' % (label, pid))


def start_voice():
    if port_open(GSV_PORT):
        seen = looks_like(GSV_PORT, ('api.py',), '嗓子')
        if seen is False:
            return False
        if seen is None:
            print('  嗓子开着，但没看清是谁（权限不够？）。先当它是——声音不对就关干净再开。')
        else:
            print('  嗓子已经开着了，跳过')
        return True
    print('  正在叫嗓子…（模型大，要等一会儿）')
    env = dict(os.environ)
    env['PATH'] = os.path.join(GSV, 'runtime') + os.pathsep + env.get('PATH', '')
    subprocess.Popen(
        [GSV_PY, '-I', 'api.py',
         '-s', SOVITS, '-g', GPT,
         '-a', '127.0.0.1', '-p', str(GSV_PORT), '-d', 'cuda'],
        cwd=GSV, env=env, creationflags=NEW_CONSOLE)
    return wait_port(GSV_PORT, 420, '嗓子')


def start_shim(mouth='qwen'):
    script = 'qwen_tts_shim.py' if mouth == 'qwen' else 'cc_tts_shim.py'
    label = 'Qwen3-TTS' if mouth == 'qwen' else 'GPT-SoVITS'
    if port_open(SHIM_PORT):
        line = proc_cmdline(pid_on(SHIM_PORT))
        if not line:
            print('  转接头开着，没看清是哪一个。先当它是——声音不对就关干净再开。')
            return True
        if script.lower() not in line.lower():
            print('  ⚠ 端口 %d 上跑的是另一个转接头（%s）' % (SHIM_PORT, line[:160]))
            print('     这次要的是 %s。先双击「关千岁.bat」，再重新开。' % script)
            return False
        print('  转接头已经开着了，跳过')
        return True
    print('  正在接转接头（%s）…' % label)
    subprocess.Popen([VENV_PY, '-X', 'utf8', os.path.join(HERE, script)],
                     cwd=HERE, creationflags=NEW_CONSOLE)
    # Qwen 要现载模型，给它多点时间
    return wait_port(SHIM_PORT, 300 if mouth == 'qwen' else 60, '转接头')


def check():
    """拉起来之后合成一句带 [轻笑] 的，验证整条链。"""
    import io
    import json
    print()
    print('试合成一句：「[轻笑] おかえりなさい、待ってたよ。」')
    body = json.dumps({'model': 'chitose', 'voice': 'chitose',
                       'input': '[轻笑] おかえりなさい、待ってたよ。',
                       'response_format': 'wav'}).encode('utf-8')
    req = urllib.request.Request('http://127.0.0.1:%d/v1/audio/speech' % SHIM_PORT,
                                 data=body,
                                 headers={'Content-Type': 'application/json'})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            raw = r.read()
    except Exception as e:
        print('  失败了：%s' % str(e)[:120])
        return False
    import soundfile as sf
    x, sr = sf.read(io.BytesIO(raw), dtype='float32')
    out = os.path.join(ROOT, 'out', 'launch_check.wav')
    with open(out, 'wb') as f:
        f.write(raw)
    print('  成功：%.1f 秒 / %d Hz / %.0f 秒合成完' % (len(x) / sr, sr, time.time() - t0))
    print('  存到 %s' % out)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--text', action='store_true')
    ap.add_argument('--enter', action='store_true')
    ap.add_argument('--cpu', action='store_true')
    ap.add_argument('--stop', action='store_true')
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--ui', action='store_true',
                    help='开千岁的窗口（app/server.py），不是控制台')
    ap.add_argument('--skip-services', action='store_true')
    ap.add_argument('--no-voice', action='store_true',
                    help='静音版：不叫嗓子和转接头，直接开界面')
    # 宝宝 2026-10-10 晚试完新嘴，说「新的不行」，换回老的 GPT-SoVITS。
    # 所以默认改回 gsv；想再试新的就 --mouth qwen。
    ap.add_argument('--mouth', choices=['qwen', 'gsv'], default='gsv',
                    help='gsv=老的 GPT-SoVITS（默认，宝宝挑的）'
                         ' / qwen=Qwen3-TTS 那套')
    args = ap.parse_args()

    # 哪些情况算「静音版」：命令行喊了 --no-voice，或者 config.json 写着 voice.enabled=false。
    silent = args.no_voice or not _voice_enabled()

    if args.stop:
        print('=== 关千岁 ===')
        kill_port(SHIM_PORT, '转接头')
        kill_port(GSV_PORT, '老嗓子')
        return

    if args.skip_services:
        ok = True
    elif silent:
        ok = True
        print('=== 静音版：只开界面，不叫嗓子 ===')
    else:
        print('=== 叫千岁起床 ===')
        ok = True
        failed = ('转接头', SHIM_PORT)
        if args.mouth == 'gsv':
            # Qwen3-TTS 自己带模型，不需要单独起 GPT-SoVITS
            ok = start_voice()
            failed = ('嗓子', GSV_PORT)
        if ok:
            if not start_shim(args.mouth):
                ok = False
                failed = ('转接头', SHIM_PORT)
        if not ok:
            diagnose(*failed)
            print()
            print('（第一次要载模型，可能等一两分钟，别急着关窗口。）')
            return

    print()
    if args.check:
        if silent:
            print('静音版没有嗓子可查。想验证声音，先把 config.json 的 voice.enabled 改成 true。')
            return
        check()
        print()
        print('服务留着没关。要关就 python launch_all.py --stop')
        return

    if args.ui:
        # 千岁的窗口：她站在中间，底下是字幕板，最底两个按钮
        print('=== 千岁，开窗 ===')
        print('（她会先按现在的钟点跟你打个招呼。窗口关掉就是退出。）')
        print()
        ui = os.path.join(ROOT, 'app', 'server.py')
        try:
            subprocess.call([VENV_PY, '-X', 'utf8', ui], cwd=ROOT)
        except KeyboardInterrupt:
            pass
        print()
        print('窗口关了。嗓子和转接头还开着——下次双击秒开。')
        print('想全关：python launch_all.py --stop')
        return

    print('=== 千岁，在听 ===')
    if args.text:
        print('（打字模式，输入一句话按回车发出，输入 q 退出）')
    else:
        print('（按住空格说话，松开就发）')
    print()
    cmd = [VENV_PY, '-X', 'utf8', os.path.join(HERE, 'chitose_chat.py')]
    for name in ('text', 'enter', 'cpu'):
        if getattr(args, name):
            cmd.append('--' + name)
    try:
        subprocess.call(cmd, cwd=ROOT)
    except KeyboardInterrupt:
        pass
    print()
    print('千岁先歇着了。')
    print('嗓子和转接头还开着——下次双击秒开。')
    print('想全关：python launch_all.py --stop')


if __name__ == '__main__':
    main()
