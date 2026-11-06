r"""把游戏里的背景抓出来，装进 `app\web\assets\bg\` —— 「换景」面板用。

宝宝 2026-10-11：「如果我想换衣服或者场景 姐姐能做到吗 就是我自由切换」。

游戏本体 `image00.int` 里躺着 **303 张背景**（1920×1080），画风和千岁本来就是
一套的。这里挑一批有代表性的：她家、神社、学校、街上、雪夜、还有几张天空。
每张配一个中文名，前端面板上显示的就是这个。

**命名规律**（以后想加图照这个找）：
  `bg01`~`bg48`、`bg99` = 场景编号
  后缀字母 = 光线/时段：`a` 白天 · `v` 傍晚 · `w` 夜 · `x` 另一种
  另有 `bgwipe*`（转场）、`bgeffect*`（特效）、`bg99a/b/c/e` = 天空（晴/晚霞/星空/雨）

用法：python scripts/build_rooms.py
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from PIL import Image

import hg3
import kif

GAME = r'D:\甜蜜女友\甜蜜女友 2 +.part1\甜蜜女友 2 +'
ARCHIVE = os.path.join(GAME, 'image00.int')
KEY = 0xC2B5E626
CACHE = r'D:\chitose\tmp\bg_cache'
DST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'app', 'web', 'assets', 'bg')

# 抓哪些、叫什么。第一个是默认那间和室。
ROOMS = [
    ('bg05vb', '和室 · 黄昏'),
    ('bg05aa', '和室 · 白天'),
    ('bg05xa', '和室 · 夜里'),
    ('bg16xb', '她的房间'),
    ('bg03v', '咖啡店'),
    ('bg11w', '教室'),
    ('bg10a', '上学路上'),
    ('bg06a', '神社街口 · 晴'),
    ('bg06v', '神社街口 · 黄昏'),
    ('bg06w', '神社街口 · 暮色'),
    ('bg01a', '神社参道 · 晴'),
    ('bg01v', '神社参道 · 黄昏'),
    ('bg01w', '神社参道 · 夜'),
    ('bg25x', '夜里的参道'),
    ('bg17w', '神社 · 夜灯'),
    ('bg09a', '神社 · 秋'),
    ('bg09v', '神社 · 雪'),
    ('bg08a', '秋日的公园'),
    ('bg18a', '春天的小路'),
    ('bg07v', '商店街'),
    ('bg26a', '商店街 · 白天'),
    ('bg26b', '商店街 · 晌午'),
    ('bg19w', '雪里的温泉街'),
    ('bg02v', '雪夜的小巷'),
    ('bg02w', '雪夜 · 暖灯'),
    ('bg99a', '晴空'),
    ('bg99b', '晚霞'),
    ('bg99c', '星空'),
    ('bg99e', '雨'),
]


def main():
    os.makedirs(DST, exist_ok=True)
    os.makedirs(CACHE, exist_ok=True)

    h = kif.Header(ARCHIVE, KEY)
    fast = kif.make_fast_decipher(h.blowfish)
    have = {n: (o, s) for (n, o, s) in h.entries}

    out = []
    for stem, cn in ROOMS:
        name = stem + '.hg3'
        if name not in have:
            print('  ★ 归档里没有 %s，跳过' % name)
            continue
        off, size = have[name]
        with open(ARCHIVE, 'rb') as f:
            f.seek(off)
            data = fast(f.read(size))
        tmp = os.path.join(CACHE, name)
        with open(tmp, 'wb') as o:
            o.write(data)
        img, meta = hg3.decode(tmp)
        jpg = stem + '.jpg'
        bg = Image.new('RGB', img.size, (20, 16, 17))
        bg.paste(img, (0, 0), img)
        bg.save(os.path.join(DST, jpg), quality=88)
        # ⚠ 面板上的小图**另存一份缩到 180 宽**。不缩的话，一打开换装面板
        #   就要下 29 张 1920×1080 的原图（12M），页面直接卡住——
        #   姐姐 2026-10-11 把自己坑过一次（连同 13 张立绘一共 50 多兆）。
        th = stem + '_s.jpg'
        bg.resize((180, 101), Image.LANCZOS).save(os.path.join(DST, th), quality=82)
        out.append({'file': jpg, 'thumb': th, 'name': cn,
                    'w': img.width, 'h': img.height})
        print('  %-10s %-16s %dx%d  %.0f KB'
              % (stem, cn, img.width, img.height,
                 os.path.getsize(os.path.join(DST, jpg)) / 1024))

    # 顺手把清单写下来，前端读它做面板
    import json
    p = os.path.join(DST, 'rooms.json')
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print()
    print('-> %s（%d 张）' % (p, len(out)))
    print('-> 图都存在 %s' % DST)


if __name__ == '__main__':
    main()
