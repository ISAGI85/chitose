"""CatSystem2 的 HG-3 (.hg3) 图片解码器。

移植自 GARbro 的 ArcFormats/CatSystem/ImageHG3.cs。
支持 img0000（自研压缩）与 img_jpg（JPEG+Alpha）两种。
"""

import struct
import zlib

import numpy as np
from PIL import Image

BASE = 0x14  # GARbro 里 Hg3Reader 的 Source 从 0x14 开始


def read_meta(data):
    if data[:4] != b'HG-3':
        raise ValueError('不是 HG-3 文件')
    if struct.unpack('<I', data[4:8])[0] != 0x0C:
        raise ValueError('HG-3 版本不支持')
    if data[0x14:0x1C] != b'stdinfo\x00':
        raise ValueError('缺少 stdinfo')
    m = {
        'header_size': struct.unpack('<I', data[0x1C:0x20])[0],
        'width': struct.unpack('<I', data[0x24:0x28])[0],
        'height': struct.unpack('<I', data[0x28:0x2C])[0],
        'bpp': struct.unpack('<i', data[0x2C:0x30])[0],
        'off_x': struct.unpack('<i', data[0x30:0x34])[0],
        'off_y': struct.unpack('<i', data[0x34:0x38])[0],
        'canvas_w': struct.unpack('<I', data[0x44:0x48])[0],
        'canvas_h': struct.unpack('<I', data[0x48:0x4C])[0],
    }
    return m


class LsbBits:
    def __init__(self, data):
        self.data = data
        self.idx = 0
        self.cur = 0
        self.left = 0

    def get(self):
        if self.left == 0:
            if self.idx >= len(self.data):
                return 0
            self.cur = self.data[self.idx]
            self.idx += 1
            self.left = 8
        b = self.cur & 1
        self.cur >>= 1
        self.left -= 1
        return b

    def count(self):
        n = 0
        while self.get() == 0:
            n += 1
            if n >= 0x20:
                raise ValueError('BitCount 溢出')
        value = 1
        for _ in range(n):
            value = (value << 1) | self.get()
        return value


def _expand_table():
    def expand(i):
        val = (i & 0xC0) << 6
        val |= i & 0x30
        val <<= 6
        val |= i & 0x0C
        val <<= 6
        val |= i & 0x03
        return val & 0xFFFFFFFF

    e = np.array([expand(i) for i in range(256)], dtype=np.uint64)
    return [np.array(e << 6, dtype=np.uint64) & 0xFFFFFFFF,
            np.array(e << 4, dtype=np.uint64) & 0xFFFFFFFF,
            np.array(e << 2, dtype=np.uint64) & 0xFFFFFFFF,
            np.array(e, dtype=np.uint64)]


_T = _expand_table()


def _convert(b):
    carry = (b & 1).astype(bool)
    r = (b >> 1).astype(np.uint32)
    return np.where(carry, r ^ np.uint32(0xFF), r).astype(np.uint8)


def _apply_delta(pixels, stride, height, pixel_size):
    """平面拆解后的增量还原。"""
    planes = pixels.reshape(4, -1)
    p0, p1, p2, p3 = planes[0], planes[1], planes[2], planes[3]
    val = (_T[0][p0] | _T[1][p1] | _T[2][p2] | _T[3][p3]).astype(np.uint64)
    b0 = _convert((val & 0xFF).astype(np.uint32))
    b1 = _convert(((val >> 8) & 0xFF).astype(np.uint32))
    b2 = _convert(((val >> 16) & 0xFF).astype(np.uint32))
    b3 = _convert(((val >> 24) & 0xFF).astype(np.uint32))
    out = np.stack([b0, b1, b2, b3], axis=1).reshape(-1)

    arr = out.reshape(height, stride).copy()
    # 只有第 0 行做横向累加（GARbro 的循环上界是 Stride，只跑一行）
    arr[0] = np.cumsum(arr[0].reshape(-1, pixel_size), axis=0, dtype=np.uint8).reshape(-1)
    # 再逐行向下累加
    arr = np.cumsum(arr, axis=0, dtype=np.uint8)
    return arr.reshape(-1)


def _unpack_img0000(data, meta):
    hs = meta['header_size']
    base = BASE + hs
    packed_data_size, data_size, packed_ctl_size, ctl_size = struct.unpack('<4i', data[base + 0x18:base + 0x28])
    data_off = base + 0x28
    ctl_off = data_off + packed_data_size

    raw = zlib.decompress(data[data_off:data_off + packed_data_size])

    ctl = zlib.decompress(data[ctl_off:ctl_off + packed_ctl_size])
    bits = LsbBits(ctl)
    copy_flag = bits.get() != 0
    out_size = bits.count()
    output = bytearray(out_size)
    src = 0
    dst = 0
    while dst < out_size:
        n = bits.count()
        if copy_flag:
            output[dst:dst + n] = raw[src:src + n]
            src += n
        dst += n
        copy_flag = not copy_flag

    pixel_size = meta['bpp'] // 8
    stride = meta['width'] * pixel_size
    return _apply_delta(np.frombuffer(bytes(output), dtype=np.uint8), stride, meta['height'], pixel_size)


def _read_sections(data, meta):
    nxt = BASE + meta['header_size']
    toc = {}
    while True:
        name = data[nxt:nxt + 8].split(b'\x00')[0].decode('ascii', 'replace')
        size = struct.unpack('<I', data[nxt + 8:nxt + 12])[0]
        toc[name] = nxt
        nxt += size
        if size == 0:
            break
    return toc


def _unpack_jpg(data, meta):
    toc = _read_sections(data, meta)
    p = toc['img_jpg'] + 12
    jpeg_size = struct.unpack('<i', data[p:p + 4])[0]
    p += 4
    img = Image.open(__import__('io').BytesIO(data[p:p + jpeg_size])).convert('RGB')
    rgb = np.array(img, dtype=np.uint8)
    h, w = rgb.shape[:2]

    total = w * h
    if 'img_al' in toc:
        ap = toc['img_al'] + 0x10
        packed_size, alpha_size = struct.unpack('<2i', data[ap:ap + 8])
        alpha = np.frombuffer(zlib.decompress(data[ap + 8:ap + 8 + packed_size]), dtype=np.uint8)[:alpha_size]
    else:
        alpha = np.full(total, 0xFF, dtype=np.uint8)

    swap = 'imgmode' in toc
    r = rgb[:, :, 0]
    g = rgb[:, :, 1]
    b = rgb[:, :, 2]
    if swap:
        r, b = b, r
    out = np.stack([b, g, r, alpha.reshape(h, w)], axis=2).reshape(-1)
    return out


def decode(path):
    with open(path, 'rb') as f:
        data = f.read()
    meta = read_meta(data)
    hs = meta['header_size']
    kind = data[BASE + hs:BASE + hs + 8]
    if kind[:7] == b'img0000':
        pixels = _unpack_img0000(data, meta)
        flipped = True
    elif kind[:7] == b'img_jpg':
        pixels = _unpack_jpg(data, meta)
        flipped = False
    else:
        raise ValueError('不支持的 HG-3 图像类型: %r' % kind)

    h, w = meta['height'], meta['width']
    arr = pixels.reshape(h, w, 4)
    if flipped:
        arr = arr[::-1]
    rgba = arr[:, :, [2, 1, 0, 3]]  # BGRA -> RGBA
    return Image.fromarray(np.ascontiguousarray(rgba), 'RGBA'), meta


if __name__ == '__main__':
    import sys
    import os
    src = sys.argv[1]
    dst = sys.argv[2]
    if os.path.isdir(src):
        os.makedirs(dst, exist_ok=True)
        ok = 0
        for f in sorted(os.listdir(src)):
            if not f.lower().endswith('.hg3'):
                continue
            try:
                img, meta = decode(os.path.join(src, f))
                img.save(os.path.join(dst, os.path.splitext(f)[0] + '.png'))
                ok += 1
            except Exception as e:
                print('失败 %s: %s' % (f, e))
        print('完成 %d 个' % ok)
    else:
        img, meta = decode(src)
        img.save(dst)
        print('已保存', dst, img.size, meta)
