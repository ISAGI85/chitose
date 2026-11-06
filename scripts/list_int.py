r"""列一个 .int 归档里都有什么（不解），拿来找背景图。

用法：python scripts/list_int.py "D:\甜蜜女友\...\image00.int" [关键字]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import kif


def main():
    path = sys.argv[1]
    needle = sys.argv[2].lower() if len(sys.argv) > 2 else ''
    # 甜蜜女友 2 +（2024 汉化补丁重打包过）= 0xC2B5E626（见 extract.py / crack.py）
    key = 0xC2B5E626
    h = kif.Header(path, key)
    names = [n for (n, _off, _size) in h.entries]
    print('共 %d 条' % len(names))
    hit = [n for n in names if needle in n.lower()] if needle else names
    for n in hit[:400]:
        print(' ', n)
    if needle:
        print('匹配 %d 条' % len(hit))


if __name__ == '__main__':
    main()
