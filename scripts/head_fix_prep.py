r"""准备「补头顶」的输入图和蒙版。

她的头顶原画只画了几根尖的头发，尖和尖之间的空没画，
所以看着像被抹了一块。这个脚本：
  1. 裁出头部区域
  2. 把透明的地方用最近的头发颜色填满（不然模型会去画背景）
  3. 算蒙版 = 「头部的凸包」减去「已经画了的部分」——就是那些凹口

产出（给 ComfyUI 用）：
    D:/chitose/out/headfix/input.png   填好底色的图
    D:/chitose/out/headfix/mask.png    白=要补的地方
    D:/chitose/out/headfix/orig.png    原图（后面对齐用）
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from scipy.spatial import ConvexHull

import hg3

SRC = r'D:/chitose/extracted/chitose_sprites/StChit01LL_c.hg3'
OUT = r'D:/chitose/out/headfix'
# 头部区域（身体图坐标）
X0, X1, Y0, Y1 = 380, 1120, 0, 470
PAD_TOP = 70          # 上面留出来的空，让模型有地方长
BAND = 0.62           # 只对头部上面这段做凸包，免得把肩膀也圈进去
# 只对这段 x 做凸包——双马尾在两边，圈进来会变成一个大拱
HULL_X0, HULL_X1 = 150, 620   # 相对 X0
FACE_TOP = 150        # 脸上沿（身体坐标），蒙版不许越过这里


def main():
    os.makedirs(OUT, exist_ok=True)
    im, _ = hg3.decode(SRC)
    a = np.array(im)
    head = a[Y0:Y1, X0:X1].copy()
    h, w = head.shape[:2]
    print('头部区域 %dx%d' % (w, h))

    # 1) 上面留空
    canvas = np.zeros((h + PAD_TOP, w, 4), dtype=np.uint8)
    canvas[PAD_TOP:] = head
    rgb = canvas[:, :, :3].astype(np.float32)
    al = canvas[:, :, 3] > 30
    ch, cw = al.shape
    print('留空后 %dx%d，不透明占 %.1f%%' % (cw, ch, 100 * al.mean()))

    # 2) 透明处填成她头发的颜色。
    #    不能用整体的中位色——那跟她的皮肤太像，模型会顺着画成发光的头发。
    #    取「最上面那段里偏暗的那些像素」当发色（发丝比受光的皮肤暗）。
    zone = al[:int(PAD_TOP + 120)]
    px = rgb[:int(PAD_TOP + 120)][zone]
    if len(px):
        lum = px @ np.array([0.299, 0.587, 0.114], np.float32)
        dark = px[lum <= np.percentile(lum, 35)]
        fill_rgb = np.median(dark if len(dark) > 50 else px, axis=0)
    else:
        fill_rgb = np.array([200, 150, 130], np.float32)
    filled = np.where(al[:, :, None], rgb, fill_rgb[None, None, :]).astype(np.float32)
    print('填的底色 %s' % fill_rgb.astype(int))

    # 3) 蒙版：头顶那段的凸包 减去 已经画了的
    top = al[:int(ch * BAND)]
    ys, xs = np.where(top)
    keep = (xs >= HULL_X0) & (xs <= HULL_X1)
    ys, xs = ys[keep], xs[keep]
    pts = np.column_stack([xs, ys]).astype(np.float64)
    hull = pts[ConvexHull(pts).vertices]
    # 把凸包画成实心多边形（用 PIL，免得依赖 matplotlib）
    hullim = Image.new('L', (cw, ch), 0)
    ImageDraw.Draw(hullim).polygon([tuple(p) for p in hull], fill=255)
    inside = np.array(hullim) > 128

    want = inside & (~al)
    # ⚠ 关键：她的脸在身体图上是**空的**（透明），所以「凸包减已画」会把整张脸
    # 也算成要补的地方，模型就会把额头往上顶一大块。
    # 蒙版只保留「脸的上沿以上」那一段。
    want[int(FACE_TOP + PAD_TOP):] = False
    # 往已经画了的头发里啃进去几像素，让它自然接上
    want = ndimage.binary_dilation(want, iterations=6) | (inside & ~al)
    want[int(FACE_TOP + PAD_TOP):] = False
    print('要补的面积：%.1f%%（%d 像素）'
          % (100 * want.mean(), want.sum()))

    Image.fromarray(np.dstack([filled.astype(np.uint8),
                               np.full((ch, cw), 255, np.uint8)]),
                    'RGBA').convert('RGB').save(os.path.join(OUT, 'input.png'))
    Image.fromarray((want * 255).astype(np.uint8)).save(os.path.join(OUT, 'mask.png'))
    Image.fromarray(canvas[PAD_TOP:], 'RGBA').save(os.path.join(OUT, 'orig.png'))

    # 一张对照图：原图 | 填色 | 蒙版
    vis = np.concatenate([
        canvas[:, :, :3],
        filled.astype(np.uint8),
        np.dstack([(want * 255).astype(np.uint8)] * 3),
    ], axis=1)
    Image.fromarray(vis).resize((vis.shape[1] // 2, vis.shape[0] // 2)).save(
        os.path.join(OUT, 'preview.png'))
    print('->', OUT)


if __name__ == '__main__':
    main()
