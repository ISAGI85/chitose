r"""按游戏自己的坐标把立绘拼起来 —— 不再猜位置。

每个 .hg3 里都写着这张图在公共画布上的 (off_x, off_y)，
所以「五官贴哪儿」是有答案的，不用对齐、不用微调。

用法：
    python scripts/sprite.py            # 出一张验证图给姐姐看
"""
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hg3

EX = r'D:\chitose\extracted'
SPRITES = os.path.join(EX, 'chitose_sprites')   # 身体（大写 C）
PARTS = os.path.join(EX, 'chitose_parts')       # 五官（小写 c）


def probe(path):
    """只读头，拿到尺寸和在公共画布上的位置。"""
    with open(path, 'rb') as f:
        m = hg3.read_meta(f.read())
    return {'w': m['width'], 'h': m['height'], 'x': m['off_x'], 'y': m['off_y']}


def load(path):
    img, _ = hg3.decode(path)
    return img


def compose(layers, box=None):
    """layers: [(路径, ...)] 按给的顺序叠。返回 (图, 左上角画布坐标)。"""
    metas = [(p, probe(p)) for p in layers]
    x0 = min(m['x'] for _, m in metas)
    y0 = min(m['y'] for _, m in metas)
    x1 = max(m['x'] + m['w'] for _, m in metas)
    y1 = max(m['y'] + m['h'] for _, m in metas)
    if box:
        x0, y0, x1, y1 = box
    canvas = Image.new('RGBA', (x1 - x0, y1 - y0), (0, 0, 0, 0))
    for p, m in metas:
        img = load(p)
        canvas.alpha_composite(img, (m['x'] - x0, m['y'] - y0))
    return canvas, (x0, y0)


if __name__ == '__main__':
    OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       'tmp', 'preview')
    os.makedirs(OUT, exist_ok=True)
    body = os.path.join(SPRITES, 'StChit01LL_c.hg3')
    bm = probe(body)
    print('身体 _c：', bm)

    faces = {
        'c_睁眼抿嘴': 'Stchit01LL_00000c.hg3',
        'd_睁眼张嘴': 'Stchit01LL_00000d.hg3',
        '002_闭眼笑': 'Stchit01LL_000002.hg3',
        'y_大照れ': 'Stchit01LL_00000y.hg3',
    }
    for name, fn in faces.items():
        p = os.path.join(PARTS, fn)
        m = probe(p)
        print('%-12s %s  %dx%d  画布(%d,%d)  相对身体左上 (%d,%d)'
              % (name, fn, m['w'], m['h'], m['x'], m['y'],
                 m['x'] - bm['x'], m['y'] - bm['y']))
        img, _ = compose([body, p])
        img2, _ = compose([body, p], box=(bm['x'], bm['y'], bm['x'] + bm['w'], bm['y'] + bm['h']))
        f = os.path.join(OUT, 'det_%s.jpg' % name)
        img2.convert('RGB').save(f, quality=92)
        print('    ->', f, img2.size)

    # 头部特写（用游戏坐标裁，跟之前那张同区域：身体内 x330..900 y0..560）
    img, _ = compose([body, os.path.join(PARTS, 'Stchit01LL_00000c.hg3')])
    crop = img.crop((bm['x'] - 298 + 330, bm['y'] - 444, bm['x'] - 298 + 900, bm['y'] - 444 + 560))
    crop.convert('RGB').save(os.path.join(OUT, 'det_head.jpg'), quality=92)
    print('->', os.path.join(OUT, 'det_head.jpg'))
