"""把 KIF(.int) 归档解包到指定目录。

用法:
    python extract.py <xxx.int> <输出目录> [main_key十六进制] [名字包含的子串]

main_key 不给的话会尝试 GARbro 已知的几个 CatSystem2 口令。
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kif

KNOWN = {
    'NXT-126VPCMQ': kif.encode_passphrase('NXT-126VPCMQ'),
    'NXT-6XKQJF5B': kif.encode_passphrase('NXT-6XKQJF5B'),
    'NXT-N0VZCG13': kif.encode_passphrase('NXT-N0VZCG13'),
    'NXT-M81ERGNE': kif.encode_passphrase('NXT-M81ERGNE'),
}


def safe_name(name):
    name = name.replace('\\', '/').split('/')[-1]
    bad = '<>:"|?*'
    for c in bad:
        name = name.replace(c, '_')
    return name or 'unnamed'


def extract(path, outdir, main_key=None, contains=None):
    if main_key is None:
        head = kif.Header(path, 0)
        main_key = kif.crack_main_key(path)
    h = kif.Header(path, main_key)
    fast = kif.make_fast_decipher(h.blowfish)
    os.makedirs(outdir, exist_ok=True)

    total = len(h.entries)
    written = 0
    skipped = 0
    done_bytes = 0
    t0 = time.time()
    seen = {}
    with open(path, 'rb') as f:
        for idx, (name, off, size) in enumerate(h.entries):
            if contains and contains not in name:
                continue
            if size <= 0 or off + size > os.path.getsize(path):
                skipped += 1
                continue
            f.seek(off)
            blob = f.read(size)
            data = fast(blob)
            fn = safe_name(name)
            if fn in seen:
                seen[fn] += 1
                base, ext = os.path.splitext(fn)
                fn = '%s_%d%s' % (base, seen[fn], ext)
            else:
                seen[fn] = 0
            with open(os.path.join(outdir, fn), 'wb') as o:
                o.write(data)
            written += 1
            done_bytes += size
            if written % 200 == 0:
                print('  已解 %d/%d  %.1f MB  %.0f 秒' % (written, total, done_bytes / 1048576, time.time() - t0))
    print('完成: 写出 %d 个文件, 跳过 %d, 共 %.1f MB, 用时 %.0f 秒'
          % (written, skipped, done_bytes / 1048576, time.time() - t0))
    return written


if __name__ == '__main__':
    src = sys.argv[1]
    dst = sys.argv[2]
    mk = int(sys.argv[3], 16) if len(sys.argv) > 3 else None
    contains = sys.argv[4] if len(sys.argv) > 4 else None
    extract(src, dst, mk, contains)
