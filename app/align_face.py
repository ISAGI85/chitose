r"""摆脸工具 —— 把五官贴到她脸上的正确位置。

姐姐看不见屏幕，只能靠读图猜；这个工具是让宝宝用眼睛一分钟摆正。

用法：
    python align_face.py
操作：
    方向键      挪 1 像素（按住 Shift 挪 10 像素）
    滚轮 / +-   缩放
    数字键 1-9  切换五官层（看别的表情对不对得上）
    S           保存到 face_calib.json
    R           复位
"""

import json
import os
import sys
import threading
import time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, 'web', 'assets')
CALIB = os.path.join(HERE, 'face_calib.json')
PORT = 9891

# 身体原图尺寸（跟 assets 里那张一致）
BODY_W, BODY_H = 1343, 3723
# 五官层的基准尺寸（各层略有出入，统一按这个缩放，差值靠中心对齐吸收）
FACE_W, FACE_H = 336, 262

app = FastAPI()
app.mount('/assets', StaticFiles(directory=ASSETS), name='assets')


class Calib(BaseModel):
    x: float
    y: float
    scale: float = 1.0


@app.get('/')
def index():
    # 带 no-store：WebView2 会缓存页面，改了 html 不重启进程也看不到效果
    return FileResponse(os.path.join(HERE, 'align.html'),
                        headers={'Cache-Control': 'no-store, must-revalidate'})


@app.post('/save')
def save(c: Calib):
    with open(CALIB, 'w', encoding='utf-8') as f:
        json.dump(c.model_dump(), f, ensure_ascii=False, indent=1)
    print('已保存：x=%.0f y=%.0f scale=%.3f  ->  %s'
          % (c.x, c.y, c.scale, CALIB), flush=True)
    return {'ok': True, 'path': CALIB}


@app.get('/load')
def load():
    """返回五官层的**中心**该落在身体的哪个点（身体像素坐标）。

    默认 (580, 300) 是姐姐量她脸的范围（x 420~740、y 155~445）取的中点。
    各层尺寸不一样（高 257~331），所以按中心对齐，不按左上角。
    """
    if os.path.exists(CALIB):
        v = json.load(open(CALIB, encoding='utf-8'))
        if 'cx' in v:
            return v
    return {'cx': 580.0, 'cy': 300.0, 'scale': 1.0}


@app.get('/api/size')
def size():
    return {'body': [BODY_W, BODY_H], 'face': [FACE_W, FACE_H]}


def main():
    import webview
    cfg = uvicorn.Config(app, host='127.0.0.1', port=PORT, log_level='warning')
    srv = uvicorn.Server(cfg)
    threading.Thread(target=srv.run, daemon=True).start()
    for _ in range(100):
        import socket
        with socket.socket() as s:
            s.settimeout(0.2)
            if s.connect_ex(('127.0.0.1', PORT)) == 0:
                break
        time.sleep(0.05)
    webview.create_window(
        '摆脸 —— 把她的五官挪正',
        'http://127.0.0.1:%d/?v=%d' % (PORT, int(time.time())),   # 防缓存
        width=820, height=1000, background_color='#241C1E')
    webview.start()


if __name__ == '__main__':
    main()
