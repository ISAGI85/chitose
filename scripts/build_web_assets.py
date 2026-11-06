r"""把界面要用的立绘素材拷进 app\web\assets\，并把坐标写成 layers.json。

坐标**不是手打的**——从每个 .hg3 的文件头里读出来（见 sprite.py 的 probe）。
坐标为「相对身体左上角」，前端直接用，不要改。

用法：
    python scripts/build_web_assets.py
"""
import json
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from PIL import Image
from scipy import ndimage

import hg3

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EX = r'D:\chitose\extracted'
SPRITES = os.path.join(EX, 'chitose_sprites')   # 身体 / 后发（大件）
PARTS = os.path.join(EX, 'chitose_parts')       # 五官
DST = os.path.join(HERE, 'app', 'web', 'assets')

BODY = ('StChit01LL_c.hg3', SPRITES)

# tag -> 源文件。tag 就是前端用的名字。
LAYERS = {
    'body': ('StChit01LL_c.hg3', SPRITES),
    # ⚠ 这一层是**整个头发**（发冠 + 刘海 + 双马尾 + 右边的辫子），不是「后发」。
    #   画在**身体上面**、五官下面。放在身体下面的话，刘海会透出来发糊
    #   （宝宝 2026-10-11 一眼看出来的：「刘海怎么是糊的」）。
    #   另外：0003 不是头发，是**兔子耳朵的连帽睡衣身体**，别拿错。
    'hair': ('Stchit01LL_0001.hg3', PARTS),
    # 第二款发型：和女仆装一起用（宝宝 2026-10-28 说的）。
    'hair.alt': ('Stchit01LL_0002.hg3', PARTS),
    # 五官：名字是姐姐逐张看过对照表定的（tmp\preview\face_pairs.jpg）
    # ⚠ 平时这张脸挑了三回，最后听宝宝的用 **00000l**（他把 27 张摊开点的 **13 号**）：
    #   · 00000c（最早）——「待机的表情感觉是担忧的表情」：上眼皮压得低、嘴是平的
    #   · 00000b（姐姐换的）——「这个太凶了」：眼睛往上斜、瞳孔偏上，像在瞪人
    #   · **00000l**（宝宝点的 13 号）—— 眼尾柔柔地垂着、瞳孔圆、嘴角带一点点笑
    #   宝宝还点了 9 号（`00000h`，嘴一直张着）和 20 号（`00000s`，一只眼闭着）——
    #   那两张当平时脸不行：**平时脸必须是「闭嘴 + 睁眼」**，
    #   不然待机时她不是张着嘴就是眨着一只眼。
    #   ⚠ l 自己的嘴比说话那张宽，一开口边上会露 42 个像素——
    #     所以下面 `_idle_face()` 把它的嘴**换成 `00000c` 的抿嘴**再上场。
    #   ⭐ **`chitose_parts` 里其实有 27 张五官层**（`000001`+`000002`+`b`~`z`），
    #     姐姐起初只挑了 15 张进界面，`l`/`o`/`x` 这几张从来没看过。
    #     **挑脸之前先把 `tmp/preview/all_faces.png` 摊开看一遍**（`tmp/all_faces.py` 生成）。
    #   **下面所有「按坐标裁一小块」的东西（眼睛层、眨眼的嘴、嘴的裁剪框）
    #   都跟着这一行走**——换平时脸只改这里。
    'face.idle':   ('Stchit01LL_00000l.hg3', PARTS),   # 睁眼 · 温柔（平时）· 宝宝点的 13 号
    # ⚠ 眨眼**不能用 000002**：那张眼睛底下挂着两颗**白色泪珠**，一眨眼就像要哭。
    #   宝宝 2026-10-11 说的「过几秒就变哭脸然后又变回了」就是这个。
    #   00000g（shut_smile）眼线几乎一样，但是干净的，**没有泪光**。
    'face.blink':  ('Stchit01LL_00000g.hg3', PARTS),   # 闭眼（真正那张图会换成「闭眼+平时的嘴」）
    'face.blink_talk': ('Stchit01LL_00000f.hg3', PARTS),  # 闭眼 · 小圆嘴：叹气 / 犯困（有心事）
    'face.talk_a': ('Stchit01LL_00000d.hg3', PARTS),   # 睁眼 · 圆张嘴：惊讶 / 意外
    'face.talk_b': ('Stchit01LL_00000h.hg3', PARTS),   # 睁眼 · 微笑开口：微笑 / 浅笑
    'face.smile':  ('Stchit01LL_00000b.hg3', PARTS),   # 和平时脸同一张（留着备用）
    'face.smile':  ('Stchit01LL_00000b.hg3', PARTS),   # 睁眼 · 抿嘴：生气 / 严肃（不是浅笑）
    'face.shut_smile': ('Stchit01LL_00000g.hg3', PARTS),  # 闭眼 · 含笑
    'face.tereb':  ('Stchit01LL_00000k.hg3', PARTS),   # 照れ：被调戏了害羞（和一般害羞不同）
    'face.shout':  ('Stchit01LL_00000u.hg3', PARTS),   # 叫ぶ：喊 / 大声
    'face.cry':    ('Stchit01LL_00000v.hg3', PARTS),   # 泣く
    'face.wow':    ('Stchit01LL_00000y.hg3', PARTS),   # 大照れ：说错话/做错事被发现时的尴尬吃惊
    'face.surprise': ('Stchit01LL_00000e.hg3', PARTS),  # きょとん：懵 / 呆住
    'face.serious': ('Stchit01LL_00000t.hg3', PARTS),  # 真剣：认真（不含叹气）
    'face.ahaa':   ('Stchit01LL_00000s.hg3', PARTS),   # あーん：张嘴 / 喂
    # 白眼 + 问号（`000001`）——漫画式的「无语」。当表情用时她的眼睛会变成
    # 两个白圈加一个问号，很可爱（宝宝 2026-10-11 要「按语境加表情」，
    # 标签那一头加在 sfx.py 的 ALIAS 里）。量过：它盖得住说话那块嘴。
    'face.question': ('Stchit01LL_000001.hg3', PARTS),  # 疑惑 / 呆萌（也当无语）
    'face.shut_open': ('Stchit01LL_00000i.hg3', PARTS),  # 闭眼 · 大张嘴：平时说话的嘴型素材
    # 脸红（差分层，可以盖在五官上）
    'blush.light': ('Stchit01LL_002.hg3', PARTS),
    'blush.heavy': ('Stchit01LL_003.hg3', PARTS),
}

# ---- 说话时用的那一小块嘴 ----
#
# **为什么不整张换脸**：`talk_a`（00000d）的眼睛是**睁圆的**，比平常那张
# （idle / 00000c）大一圈。宝宝 2026-10-11 的原话是「眼睛突然变大又恢复」——
# 每开一次口，眼睛就跟着放大一次。实测两张脸差 25726 个像素，**其中 20862
# 在眼睛上**（嘴只占 4864）。换回整张脸这条路是死的。
#
# **改法**：脸永远用 idle，说话时只在嘴上盖一小块。
# 量过了：idle 抿嘴那一小块**完全落在**要盖上去的那张嘴里面，
# 所以大嘴盖上去，原来的小嘴自动就看不见了——**底图一个字都不用改**。
#
# **用哪张嘴**：宝宝 2026-10-26 在 `all_faces.png` 上点了**第 10 张** ——
# `00000i`（闭眼 · 大张嘴）。他说这张张开的嘴跟平时抿着的嘴**合得来**，
# 所以待机脸不动，说话时只把这张的嘴盖上去。
# 量过：抿嘴（00000c）完全落在它里面，**盖不住 0 个像素**。
# 以前试过的：talk_a 正圆太大 · ahaa 椭圆能用 · talk_b 横向咧嘴 ·
# surprise 更扁——选嘴型要出图看，光看名字和宽高比看不出来。
MOUTH_BASE = 'face.idle'      # 平时抿着的嘴（要被盖住的那个）
# 宝宝 2026-10-26 在 all_faces.png 上点的「第 10 张」= 00000i（闭眼·大张嘴）。
# 他说这张张开的嘴跟平时抿着的嘴**合得来**，说话就用它，平时那张脸不动。
# 不再缩：它自己多大就多大，位置也是从原画里量出来的。
MOUTH_FROM = 'face.shut_open'
MOUTH_PAD = 6                 # 裁剪框往外留几像素余量

# 眨眼动画用的那一层「睁着的眼睛」（见 _eyes_crop）
EYES_PAD = 4

# 可切换的衣服（换装面板用）
#
# 宝宝 2026-10-11：「如果我想换衣服或者场景 姐姐能做到吗 就是我自由切换」。
# `StChit01LL_a` ~ `_m` 一共 **13 套**（c 是校服，现在穿的那身）。
# 姐姐以前只解了 `c` 和 `a`，剩下的在 `chitose_sprites` 里躺了很久没看。
#
# ⚠ **坐标全都读得出来，不手打**：每套的 `off_x/off_y` 都是相对身体 `c`
# 换算的——所有千岁的 .hg3 都画在**同一张大画布**上，所以换衣服时
# 五官/头发**一个坐标都不用改**，只要换身体那一层的图。
BODIES = 'abcdefghijklm'


def _lowest_ink_box(img, m):
    """一张五官层里**最下面那一坨墨**（=嘴）的方框。

    五官层没有肤色底，只有线条，所以「最下面连续的一片墨」就是嘴——
    上面是眼睛和眉毛，中间一定有空行隔着（实测 idle 在 y 288~359 是空的）。
    这样不写死 y 坐标，换素材也不会算错。

    ⚠ 回来的坐标和 `off_x/off_y` 是**同一套**（所有千岁的 .hg3 都画在同一张
    大画布上）；要给前端用还得减掉身体的位置，跟上面 LAYERS 那批一样。
    """
    a = np.asarray(img, dtype=np.float32)[:, :, 3] / 255.0
    rows = (a > 0.25).any(axis=1)
    ys = np.where(rows)[0]
    if not len(ys):
        return None
    end = int(ys[-1])
    top = end
    while top > 0 and rows[top - 1]:
        top -= 1
    band = a[top:end + 1] > 0.25
    xs = np.where(band.any(axis=0))[0]
    return (int(xs.min()) + m['off_x'], top + m['off_y'],
            int(xs.max()) + 1 + m['off_x'], end + 1 + m['off_y'])


# 平时那张脸的嘴从哪来（见 _idle_face）
IDLE_MOUTH_FROM = 'Stchit01LL_00000c.hg3'

_IDLE = {}


def _idle_face():
    """平时那张脸（拼好的）：宝宝点的 `00000l` 的眼睛 + `00000c` 的抿嘴。

    **为什么要把嘴换掉**：l 自己的嘴比说话那张（ahaa）**宽**，一开口
    边上会露出 42 个像素的「另一个嘴」（`tmp/cover_candidates.py` 量的）。
    c 的抿嘴小、平，说话时被盖得严严实实（盖不住 0 个）。

    换法和 `_blink_face` 一个套路：把 l 在嘴那一块**整个换成** c 的像素
    （`paste` 是覆盖不是叠加）。裁的框取「**l 的嘴 ∪ c 的嘴**」，
    这样 l 那张宽嘴的两端也被盖掉。
    """
    if _IDLE:
        return _IDLE['img'], _IDLE['meta']
    lim, lm = hg3.decode(os.path.join(PARTS, LAYERS['face.idle'][0]))
    cim, cm = hg3.decode(os.path.join(PARTS, IDLE_MOUTH_FROM))
    lb = _lowest_ink_box(lim, lm)
    cb = _lowest_ink_box(cim, cm)
    x0 = min(lb[0], cb[0]) - MOUTH_PAD
    y0 = min(lb[1], cb[1]) - MOUTH_PAD
    x1 = max(lb[2], cb[2]) + MOUTH_PAD
    y1 = max(lb[3], cb[3]) + MOUTH_PAD
    patch = cim.crop((x0 - cm['off_x'], y0 - cm['off_y'],
                      x1 - cm['off_x'], y1 - cm['off_y']))
    out = lim.copy()
    out = lim.copy()
    out.paste(patch, (x0 - lm['off_x'], y0 - lm['off_y']))
    _IDLE['img'], _IDLE['meta'] = _feather(out), lm
    return out, lm


# 害羞 / 撒娇 / 无奈那张脸（见 _shy_face）
SHY_SRC = 'Stchit01LL_00000z.hg3'

_SHY = {}


def _shy_face():
    """害羞 / 撒娇 / 无奈 = **`00000z` 原样**：眯眼 + 脸红 + 爱心 + 它自己那个
    微微翘着的小嘴。

    宝宝 2026-10-11 为它说了三回：
      ① 「千岁有个脸全红的表情 但是聊天聊到一半脸全红了但眼睛还是睁开的
         是不是有点突兀了 我记得游戏里有对应的」——**就是这张**。
      ② 「这个表情应该是用于那种撒娇或者有点拿调皮的弟弟没办法的表情」
         → 它管**撒娇 / 无奈**，「亲密」回到 `shut_smile`。
      ③ 姐姐问「哪张的嘴是你要的横线」，他在那排对比图上点了名：
         「**是倒数第二张哦**」——**就是 `00000z` 自己的嘴**。
         姐姐先前拿 `00000t` 的横线嘴去换，是换错了方向。

    ⭐ **嘴不用动**。它那张嘴「盖不住」（说话时会被叠嘴层戳穿，漏 792 像素）
    只在**开口说话**时才成问题——而这个表情说话时**根本不叠嘴**
    （见 `app.js` 的 `syncMouth()`：`baseFace !== 'shy'` 才叠）。
    所以这里唯一要做的是**羽化边缘**，免得那块小图在深色头发上盖出一个淡框。
    """
    if _SHY:
        return _SHY['img'], _SHY['meta']
    zim, zm = hg3.decode(os.path.join(PARTS, SHY_SRC))
    _SHY['img'], _SHY['meta'] = _feather(zim), zm
    return _SHY['img'], _SHY['meta']


def _mouth_crop(bx, by):
    """量出嘴的裁剪框，并把那一块剪成一张小图。返回 (给前端的项, 检查报告)。"""
    bimg, bm = _idle_face()          # 用拼好的那张（见 _idle_face）
    timg, tm = hg3.decode(os.path.join(PARTS, LAYERS[MOUTH_FROM][0]))
    b_base = _lowest_ink_box(bimg, bm)
    b_talk = _lowest_ink_box(timg, tm)

    x0 = min(b_base[0], b_talk[0]) - MOUTH_PAD
    y0 = min(b_base[1], b_talk[1]) - MOUTH_PAD
    x1 = max(b_base[2], b_talk[2]) + MOUTH_PAD
    y1 = max(b_base[3], b_talk[3]) + MOUTH_PAD
    W, H = x1 - x0, y1 - y0

    def ink_in_box(img, m):
        """这张图的墨，落在裁剪框里的是哪几格（布尔图，框的大小）。"""
        a = np.asarray(img, dtype=np.float32)[:, :, 3] / 255.0 > 0.25
        out = np.zeros((H, W), dtype=bool)
        ox, oy = m['off_x'] - x0, m['off_y'] - y0        # 图左上角在框里的位置
        sx, sy = max(0, -ox), max(0, -oy)                 # 图内起点
        dx, dy = max(0, ox), max(0, oy)                   # 框内起点
        w = min(W - dx, a.shape[1] - sx)
        h = min(H - dy, a.shape[0] - sy)
        if w > 0 and h > 0:
            out[dy:dy + h, dx:dx + w] = a[sy:sy + h, sx:sx + w]
        return out

    big = ink_in_box(timg, tm)          # 张嘴那一块（要拿来盖的）
    small = ink_in_box(bimg, bm)        # 平时那半张脸在框里的墨
    naked = int((small & ~big).sum())   # 盖不住的像素数——必须是 0

    x = x0 - tm['off_x']
    y = y0 - tm['off_y']
    crop = _feather(timg.crop((x, y, x + W, y + H)))
    name = MOUTH_FROM.replace('.', '_') + '_mouth.png'
    crop.save(os.path.join(DST, name))

    rep = ('  抿嘴 %d×%d ／ 张嘴 %d×%d → 裁剪框 %d×%d'
           % (b_base[2] - b_base[0], b_base[3] - b_base[1],
              b_talk[2] - b_talk[0], b_talk[3] - b_talk[1], W, H))
    rep += '\n  张嘴盖不住的像素：%d  %s' % (
        naked, '✅ 一个都不漏' if naked == 0 else '★会露出两个嘴，得改底图')

    item = {'file': name, 'w': W, 'h': H, 'x': x0 - bx, 'y': y0 - by}
    return item, rep


def _face_mouth_set(face_tag, bx, by, bimg_body):
    """某张表情**自己的嘴**，单独做一套「遮片 + 可开合的嘴」。

    只给「它自己的嘴就是说话时的嘴型」的表情用。
    惊讶（`face.surprise` / 00000e）自己的是一张小圆嘴；
    拿平嘴那张大张嘴（00000i）盖上去，圆嘴会被整个吃掉——
    宝宝 2026-10-26：「她惊讶是嘴巴应该是圆嘴」。

    裁法和平嘴那套不同：这里**只围它自己的嘴**，不跟 idle 的嘴取并集。
    因为这张嘴只盖在它自己脸上，按它自己的中心缩放才对；
    跟 idle 并集的话，缩放中心会落在两张嘴中间，圆嘴会一边缩一边跑。
    """
    img, m = hg3.decode(os.path.join(PARTS, LAYERS[face_tag][0]))
    b = _lowest_ink_box(img, m)
    x0 = b[0] - MOUTH_PAD
    y0 = b[1] - MOUTH_PAD
    x1 = b[2] + MOUTH_PAD
    y1 = b[3] + MOUTH_PAD
    crop = _feather(img.crop((x0 - m['off_x'], y0 - m['off_y'],
                              x1 - m['off_x'], y1 - m['off_y'])))
    stem = face_tag.replace('.', '_')
    name = 'mouth_%s.png' % stem
    crop.save(os.path.join(DST, name))
    item = {'file': name, 'w': crop.width, 'h': crop.height,
            'x': x0 - bx, 'y': y0 - by}

    cover = _feather(bimg_body.crop((x0 - bx, y0 - by, x1 - bx, y1 - by)), 4)
    cname = 'mouth_cover_%s.png' % stem
    cover.save(os.path.join(DST, cname))
    cover_item = {'file': cname, 'w': cover.width, 'h': cover.height,
                  'x': x0 - bx, 'y': y0 - by}
    return item, cover_item


def _mouth_on_face(src_tag, target_tag, scale, bx, by, bimg_body, stem):
    """把一张脸的嘴（src）缩到 scale，贴到另一张脸的嘴中心（target）。

    惊讶用这个：`talk_a`（00000d）是**正圆**的嘴，宝宝要的「圆嘴」就是它。
    惊讶自己的小嘴太小、而且本来就是张着的，开合时几乎看不出来；
    所以把它自己的小嘴用遮片盖掉，再把正圆嘴放到同一个中心。
    """
    simg, sm = hg3.decode(os.path.join(PARTS, LAYERS[src_tag][0]))
    sb = _lowest_ink_box(simg, sm)
    timg, tm = hg3.decode(os.path.join(PARTS, LAYERS[target_tag][0]))
    tb = _lowest_ink_box(timg, tm)

    pad = 10
    x0, y0, x1, y1 = sb[0] - pad, sb[1] - pad, sb[2] + pad, sb[3] + pad
    crop = simg.crop((x0 - sm['off_x'], y0 - sm['off_y'],
                      x1 - sm['off_x'], y1 - sm['off_y']))
    w = max(1, round(crop.width * scale))
    h = max(1, round(crop.height * scale))
    crop = crop.resize((w, h), Image.LANCZOS)

    # 目标嘴的中心（画布坐标）→ 这张嘴在身体里的左上角
    tx = (tb[0] + tb[2]) / 2
    ty = (tb[1] + tb[3]) / 2
    left = round(tx - w / 2) - bx
    top = round(ty - h / 2) - by

    name = 'mouth_%s.png' % stem
    crop.save(os.path.join(DST, name))
    item = {'file': name, 'w': w, 'h': h, 'x': left, 'y': top}

    # 遮片要同时盖住「目标脸原来的嘴」和「贴上来的圆嘴」
    ux0 = min(tb[0] - bx, left) - 10
    uy0 = min(tb[1] - by, top) - 10
    ux1 = max(tb[2] - bx, left + w) + 10
    uy1 = max(tb[3] - by, top + h) + 10
    cover = _feather(bimg_body.crop((ux0, uy0, ux1, uy1)), 4)
    cname = 'mouth_cover_%s.png' % stem
    cover.save(os.path.join(DST, cname))
    cover_item = {'file': cname, 'w': cover.width, 'h': cover.height,
                  'x': ux0, 'y': uy0}
    return item, cover_item


def _feather(img, px=3):
    """把图片最外圈几像素的 alpha 平滑地吃掉（羽化）。

    ⚠ 这些裁出来的小方块是要盖到**深色**（她的头发、和室的阴影）上的。
    原图里眼睛边上本来就有一圈**极淡的像素**（alpha 只有 7/255 上下），
    裁进来以后，盖到深色背景上就显出**一个淡白色的方框**——
    宝宝 2026-10-11 说的「她脸周围出现一个框 能不能去掉」就是它
    （姐姐一开始还当成无头截图的噪声，是错的：他在真窗口里也看见了）。
    最外圈几像素渐变到 0 就干净了。
    """
    a = np.asarray(img, dtype=np.float32).copy()
    h, w = a.shape[:2]
    for i in range(min(px, h // 2, w // 2)):
        # 最外圈**直接归零**（i=0 → k=0），往里再平滑回升。
        # 只乘个 0.25 的话，alpha 255 还剩 63，盖在深色头发上照样看得见那个框。
        k = i / float(px)
        a[i, :, 3] *= k
        a[h - 1 - i, :, 3] *= k
        a[:, i, 3] *= k
        a[:, w - 1 - i, 3] *= k
    return Image.fromarray(a.astype(np.uint8))


def _eyes_crop(bx, by):
    """剪出「她睁着的那双眼睛」——单独一层，眨眼动画要用（见 app.js）。

    宝宝 2026-10-11：「眨眼应该有其他正确的素材吧，或者你可以把眨眼的时长
    变久一点 直接当一个表情 但要有动画一样的转变过程 不要两张图切」。

    做法：把 idle 的**眼睛那一块**剪下来单独盖在脸上；眨眼时让这一层
    **慢慢淡掉**，淡没的瞬间底下就是闭着眼的那张——看着就是眼睑落下来。
    所以要裁得**只有眼睛，连眉毛都不能带上**（一起淡会成鬼影）。
    """
    iim, im = _idle_face()           # 拼好的那张（见 _idle_face）
    a = np.asarray(iim, dtype=np.float32)[:, :, 3] / 255.0 > 0.25
    lab, n = ndimage.label(a, structure=np.ones((3, 3)))
    blobs = []
    for i in range(1, n + 1):
        yy, xx = np.where(lab == i)
        blobs.append((len(yy), xx.min(), yy.min(), xx.max(), yy.max()))
    # ⚠ 眼睛是**最大的两块**（各四千多像素）；最上面那两条细长的是**眉毛**
    #   （几百像素）。姐姐第一次就挑成眉毛了，全在 tmp/measure_eyes.py 里对过。
    top = sorted(blobs, key=lambda b: -b[0])[:2]
    # int() 别省：numpy 的整数 json 存不了
    x0 = int(min(b[1] for b in top) + im['off_x'] - EYES_PAD)
    y0 = int(min(b[2] for b in top) + im['off_y'] - EYES_PAD)
    x1 = int(max(b[3] for b in top) + 1 + im['off_x'] + EYES_PAD)
    y1 = int(max(b[4] for b in top) + 1 + im['off_y'] + EYES_PAD)

    crop = _feather(iim.crop((x0 - im['off_x'], y0 - im['off_y'],
                              x1 - im['off_x'], y1 - im['off_y'])))
    name = 'eyes_idle.png'
    crop.save(os.path.join(DST, name))
    rep = ('  眼睛那一块 %d×%d（画布 %d,%d）—— 只有眼睛，眉毛没带上'
           % (crop.width, crop.height, x0, y0))
    return {'file': name, 'w': crop.width, 'h': crop.height,
            'x': x0 - bx, 'y': y0 - by}, rep


def _blink_face(bx, by, box):
    """眨眼那张 = 闭眼的她 + **平时的嘴**。

    宝宝 2026-10-11 连着挑出两个毛病，姐姐绕了两圈才想明白：

      ① 最初用 `000002` → 「过几秒就变哭脸」。
         那张**不是「闭眼抿嘴」，是「哭着闭眼」**——眼睛底下挂着泪痕，
         脸颊两边还有两道泪溜下来。放大一看就明白
         （`tmp/preview/orig_000002_zoom.png`）。姐姐以前记的
         「有一小点泪光，缩到窗口看不出来」是**错**的。
      ② 换成 `00000g`（闭眼含笑）→「过几秒又突然出现一个笑脸」。
         那张嘴角是翘的，眨一下就像笑了一下。

    **眨眼就该是「闭眼，别的什么都不变」。** 所以：拿 `00000g` 的闭眼，
    把它嘴那一块**整个换成 idle 的嘴**（`paste` 是覆盖不是叠加，
    眨眼的嘴就此消失），成图就是「平时的她闭上了眼睛」。
    """
    bim, bm = hg3.decode(os.path.join(PARTS, LAYERS['face.blink'][0]))
    iim, im = _idle_face()           # 拼好的那张（见 _idle_face）
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0

    patch = iim.crop((x0 - im['off_x'], y0 - im['off_y'],
                      x0 - im['off_x'] + w, y0 - im['off_y'] + h))
    out = bim.copy()
    # 00000g 自己那张嘴和 idle 的嘴不在一个位置；直接贴 idle 的嘴，
    # 下面会残留 00000g 的一小截唇线，变成「两张嘴」。
    # 先把眼睛以下的整条嘴部带子清空，再贴 idle 的嘴——保证只有一张嘴。
    a = np.asarray(out).copy()
    a[190:, :, 3] = 0
    out = Image.fromarray(a)
    out.paste(patch, (x0 - bm['off_x'], y0 - bm['off_y']))
    out = _feather(out)          # 边缘那圈淡像素盖在头发上会显出一个框
    name = 'blink_idle_mouth.png'
    out.save(os.path.join(DST, name))
    return {'file': name, 'w': out.width, 'h': out.height,
            'x': bm['off_x'] - bx, 'y': bm['off_y'] - by}


def main():
    global MOUTH_FROM
    os.makedirs(DST, exist_ok=True)
    body_path = os.path.join(SPRITES, BODY[0])
    bimg_body, bm = hg3.decode(body_path)
    bx, by = bm['off_x'], bm['off_y']

    # 先把嘴那一块量出来——眨眼那张要用这个框来换嘴
    mouth_item, mouth_rep = _mouth_crop(bx, by)
    # 第 10 张（00000i）的嘴原样用，不缩：宝宝说它跟待机的嘴合得来
    mbox = (mouth_item['x'] + bx, mouth_item['y'] + by,
            mouth_item['x'] + bx + mouth_item['w'],
            mouth_item['y'] + by + mouth_item['h'])

    # 闭眼笑那张单独用「小圆嘴」，平嘴用 talk_a
    _keep_from = MOUTH_FROM
    MOUTH_FROM = 'face.blink_talk'
    smile_mouth_item, smile_mouth_rep = _mouth_crop(bx, by)
    MOUTH_FROM = _keep_from


    out = {'version': int(time.time()), 'body': {'w': bm['width'], 'h': bm['height']}, 'layers': {}}

    # 说话时先盖一块**不透明的皮肤**在待机嘴上，再让张开的嘴在上面淡入淡出。
    # 不然 opacity 降到 .14 的时候，底下抿着的嘴会透出来，看着像两张嘴。
    cover = bimg_body.crop((mouth_item['x'], mouth_item['y'],
                            mouth_item['x'] + mouth_item['w'],
                            mouth_item['y'] + mouth_item['h']))
    cover = _feather(cover, 4)
    cover.save(os.path.join(DST, 'mouth_cover.png'))
    out['layers']['mouth.cover'] = {
        'file': 'mouth_cover.png', 'w': cover.width, 'h': cover.height,
        'x': mouth_item['x'], 'y': mouth_item['y'],
    }

    # 惊讶（00000e）用 talk_a（00000d）的**正圆嘴**，缩到 0.8 后对准
    # 惊讶自己的嘴中心。宝宝 2026-10-26 要的「圆嘴」就是这张；
    # 惊讶自己的小嘴太小，开合时几乎看不出来。
    surprise_open, surprise_cover = _mouth_on_face(
        'face.talk_a', 'face.surprise', 0.8, bx, by, bimg_body, 'surprise')
    out['layers']['mouth.open_surprise'] = surprise_open
    out['layers']['mouth.cover_surprise'] = surprise_cover

    # 这几张脸说话时也用**自己的嘴**做开合素材，别拿平时那张去盖：
    #   talk_a（惊讶/意外）· tereb（被调戏害羞）· wow（尴尬）· blink_talk（叹气/犯困）
    # 宝宝 2026-10-28 在 17 张总览上逐张点了名。
    for _tag in ('face.talk_a', 'face.tereb', 'face.wow', 'face.blink_talk',
                 'face.shout', 'face.talk_b'):
        _stem = _tag.split('.')[1]
        _item, _cover = _face_mouth_set(_tag, bx, by, bimg_body)
        out['layers']['mouth.open_' + _stem] = _item
        out['layers']['mouth.cover_' + _stem] = _cover
        print('mouth.open_%-10s %-28s %4dx%-4d 相对身体 (%4d,%4d)'
              % (_stem, _item['file'], _item['w'], _item['h'],
                 _item['x'], _item['y']))

    # 闭眼含笑（shut_smile / 00000g）自己的嘴在另一个位置：
    # 单独做一套「遮住笑嘴的皮肤 + 对齐到笑嘴位置的圆嘴」。
    simg, sm = hg3.decode(os.path.join(PARTS, LAYERS['face.shut_smile'][0]))
    sb = _lowest_ink_box(simg, sm)
    sx, sy = sb[0] - bx, sb[1] - by
    sw, sh = sb[2] - sb[0], sb[3] - sb[1]
    ow, oh = smile_mouth_item['w'], smile_mouth_item['h']
    ox = round(sx + sw / 2 - ow / 2)
    oy = round(sy + sh / 2 - oh / 2)
    cx0, cy0 = min(sx, ox) - 7, min(sy, oy) - 7
    cx1, cy1 = max(sx + sw, ox + ow) + 7, max(sy + sh, oy + oh) + 7
    scover = _feather(bimg_body.crop((cx0, cy0, cx1, cy1)), 4)
    scover.save(os.path.join(DST, 'mouth_cover_smile.png'))
    out['layers']['mouth.cover_smile'] = {
        'file': 'mouth_cover_smile.png', 'w': scover.width, 'h': scover.height,
        'x': cx0, 'y': cy0,
    }
    out['layers']['mouth.open_smile'] = {
        'file': smile_mouth_item['file'], 'w': ow, 'h': oh, 'x': ox, 'y': oy,
    }

    for tag, (fn, src) in LAYERS.items():
        if tag in ('face.blink', 'face.idle'):
            continue          # 这两张要拼过才上场，单独处理（见 _blink_face / _idle_face）
        p = os.path.join(src, fn)
        img, m = hg3.decode(p)
        name = fn[:-4] + '.png'
        img.save(os.path.join(DST, name))
        out['layers'][tag] = {
            'file': name, 'w': img.width, 'h': img.height,
            'x': m['off_x'] - bx, 'y': m['off_y'] - by,
        }
        print('%-16s %-28s %4dx%-4d 相对身体 (%4d,%4d)'
              % (tag, name, img.width, img.height,
                 m['off_x'] - bx, m['off_y'] - by))

    # 平时那张脸：宝宝点的眼睛 + 一张「说话时盖得住」的嘴（见 _idle_face）
    iimg, imeta = _idle_face()
    iimg.save(os.path.join(DST, 'idle_face.png'))
    iitem = {'file': 'idle_face.png', 'w': iimg.width, 'h': iimg.height,
             'x': imeta['off_x'] - bx, 'y': imeta['off_y'] - by}
    out['layers']['face.idle'] = iitem
    print('%-16s %-28s %4dx%-4d 相对身体 (%4d,%4d)  ← 宝宝挑的眼睛 + 抿嘴'
          % ('face.idle', iitem['file'], iitem['w'], iitem['h'],
             iitem['x'], iitem['y']))

    # 眨眼那张：闭眼 + **平时的嘴**（不然要么哭要么笑，见 _blink_face）
    bitem = _blink_face(bx, by, mbox)
    out['layers']['face.blink'] = bitem
    print('%-16s %-28s %4dx%-4d 相对身体 (%4d,%4d)  ← 闭眼 + 平时的嘴'
          % ('face.blink', bitem['file'], bitem['w'], bitem['h'],
             bitem['x'], bitem['y']))

    # 害羞 / 亲密 / 亲吻那张：眯眼 + 脸红（见 _shy_face）
    simg, smeta = _shy_face()
    simg.save(os.path.join(DST, 'shy_face.png'))
    sitem = {'file': 'shy_face.png', 'w': simg.width, 'h': simg.height,
             'x': smeta['off_x'] - bx, 'y': smeta['off_y'] - by}
    out['layers']['face.shy'] = sitem
    print('%-16s %-28s %4dx%-4d 相对身体 (%4d,%4d)  ← 眯眼 + 脸红（害羞用）'
          % ('face.shy', sitem['file'], sitem['w'], sitem['h'],
             sitem['x'], sitem['y']))

    # 说话时盖上去的那一小块嘴（见文件上方 MOUTH_FROM 的说明）
    out['layers']['mouth.open'] = mouth_item
    print()
    print('mouth.open       %-28s %4dx%-4d 相对身体 (%4d,%4d)'
          % (mouth_item['file'], mouth_item['w'], mouth_item['h'],
             mouth_item['x'], mouth_item['y']))
    print(mouth_rep)
    print('mouth.open_surprise %-23s %4dx%-4d 相对身体 (%4d,%4d)  ← 惊讶的正圆嘴（talk_a 0.8）'
          % (surprise_open['file'], surprise_open['w'], surprise_open['h'],
             surprise_open['x'], surprise_open['y']))

    # 眨眼动画用的那一层「睁着的眼睛」（见 _eyes_crop）
    eitem, erep = _eyes_crop(bx, by)
    out['layers']['eyes.idle'] = eitem
    print('eyes.idle        %-28s %4dx%-4d 相对身体 (%4d,%4d)'
          % (eitem['file'], eitem['w'], eitem['h'], eitem['x'], eitem['y']))
    print(erep)

    # ---- 十三套衣服（换装面板用，见上面 BODIES 的说明）----
    print()
    print('---- 衣服 %d 套（坐标同样是读出来的）----' % len(BODIES))
    out['bodies'] = {}
    for letter in BODIES:
        img, m = hg3.decode(os.path.join(SPRITES, 'StChit01LL_%s.hg3' % letter))
        name = 'body_%s.png' % letter
        img.save(os.path.join(DST, name))
        # ⚠ 面板上的小图**另存一份缩到 180 宽**。
        #   不这么做的话，打开面板会把 13 张 3M 的立绘全下一遍
        #   （加上 29 张背景一共 50 多兆），页面直接卡住——
        #   姐姐 2026-10-11 就是这么把自己坑了，测试页的探针都跑不动。
        thumb = 'body_%s_s.png' % letter
        img.resize((180, int(img.height * 180 / img.width)),
                   Image.LANCZOS).save(os.path.join(DST, thumb))
        out['bodies'][letter] = {
            'file': name, 'thumb': thumb, 'w': img.width, 'h': img.height,
            'x': m['off_x'] - bx, 'y': m['off_y'] - by,
        }
        print('  %s  %-14s %4dx%-5d 相对身体 (%4d,%4d)'
              % (letter, name, img.width, img.height,
                 m['off_x'] - bx, m['off_y'] - by))
    # 兔子耳朵连帽睡衣：0003 不是头发，是一件罩在裸体上的睡衣。
    # 底用 m（没穿·远）垫皮肤，把 0003 罩上去，合成一套完整的立绘。
    mb, mm = hg3.decode(os.path.join(SPRITES, 'StChit01LL_a.hg3'))
    hb, hm = hg3.decode(os.path.join(PARTS, 'Stchit01LL_0003.hg3'))
    hx = hm['off_x'] - mm['off_x']       # 睡衣相对底身体
    hy = hm['off_y'] - mm['off_y']
    # 睡衣比底图高（帽子伸到身体上方），所以画布取两者的并集，
    # 不能直接拿底图 copy，不然帽子会被裁掉。
    x0, y0 = min(0, hx), min(0, hy)
    x1 = max(mb.width, hx + hb.width)
    y1 = max(mb.height, hy + hb.height)
    hood = Image.new('RGBA', (x1 - x0, y1 - y0), (0, 0, 0, 0))
    # 只取身体中央的皮肤（脸/脖子/手），不要两侧的后发——
    # 兔子睡衣帽子里不该有后发（宝宝 2026-10-28 指出）。
    patch = (500, 80, 900, 1300)
    hood.alpha_composite(mb.crop(patch), (patch[0] - x0, patch[1] - y0))
    hood.alpha_composite(hb, (hx - x0, hy - y0))
    hood.save(os.path.join(DST, 'body_hood.png'))
    hood_thumb = 'body_hood_s.png'
    hood.resize((180, int(hood.height * 180 / hood.width)), Image.LANCZOS).save(
        os.path.join(DST, hood_thumb))
    out['bodies']['hood'] = {
        'file': 'body_hood.png', 'thumb': hood_thumb,
        'w': hood.width, 'h': hood.height, 'x': x0, 'y': y0,
        'noHair': True,
    }
    print('  hood   body_hood.png   %4dx%-5d  ← 兔子耳朵连帽睡衣（不叠头发）'
          % (hood.width, hood.height))

    # body 那一层就用 c（校服）这套，省一份 3M 的副本
    out['layers']['body'] = dict(out['bodies']['c'])

    with open(os.path.join(DST, 'layers.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print('\n-> %s' % os.path.join(DST, 'layers.json'))

    # 清掉没坐标、也没在用的旧图，免得前端认错
    keep = {v['file'] for v in out['layers'].values()}
    for v in out['bodies'].values():
        keep.add(v['file'])
        keep.add(v['thumb'])          # 面板上的小图也要留住
    for f in os.listdir(DST):
        if f.endswith('.png') and f not in keep:
            os.remove(os.path.join(DST, f))
            print('清掉旧图', f)


if __name__ == '__main__':
    main()
