"""反推 CatSystem2 的 name 主密钥。

原理：GARbro 的 SRand 之后第一次 Rand() 取的是 mt[0]，
而 mt[0] = (seed & 0xffff0000) | ((69069*seed+1) & 0xffff0000) >> 16，
只和 seed 有关，可以 O(1) 算出来，于是 2^32 全空间可搜。
"""

import struct
import sys
import numpy as np

sys.path.insert(0, r'D:\chitose\scripts')
import kif

MASK64 = 0xFFFFFFFF

np.seterr(over='ignore')


def _lcg_consts():
    """s_n = (A_n*s0 + B_n) mod 2^32，其中 s_{n+1} = 69069*s_n + 1。"""
    A = {}
    B = {}
    a, b = 1, 0
    for n in range(0, 800):
        A[n] = a
        B[n] = b
        a = (69069 * a) & MASK64
        b = (69069 * b + 1) & MASK64
    return A, B


_A, _B = _lcg_consts()


def k0_array(seeds):
    """seeds: uint32 ndarray -> k0 = bytesum(temper(扭转后的 mt[0])) & 0xFF

    SRand 之后第一次 Rand() 会先做一轮扭转，新 mt[0] 只依赖
    SRand 阶段的 mt[0]、mt[1]、mt[397]，三者都能由 seed 直接算出。
    """
    s0 = seeds.astype(np.uint32)
    u32 = np.uint32

    def sn(A, B):
        return (u32(A) * s0 + u32(B)).astype(np.uint32)

    m794 = sn(_A[794], _B[794])
    m795 = sn(_A[795], _B[795])
    mt0 = (s0 & u32(0xFFFF0000)) | ((sn(_A[1], _B[1]) & u32(0xFFFF0000)) >> u32(16))
    s2 = sn(_A[2], _B[2])
    s3 = sn(_A[3], _B[3])
    mt1 = (s2 & u32(0xFFFF0000)) | ((s3 & u32(0xFFFF0000)) >> u32(16))
    mt397 = (m794 & u32(0xFFFF0000)) | ((m795 & u32(0xFFFF0000)) >> u32(16))

    y = (mt0 & u32(0x80000000)) | (mt1 & u32(0x7FFFFFFF))
    z = mt397 ^ (y >> u32(1)) ^ np.where((y & u32(1)) == u32(1), u32(0x9908B0DF), u32(0)).astype(np.uint32)

    z = z ^ (z >> u32(11))
    z = z ^ ((z << u32(7)) & u32(0x9D2C5680))
    z = z ^ ((z << u32(15)) & u32(0xEFC60000))
    z = z ^ (z >> u32(18))

    b = z.astype(np.uint32)
    return ((b >> u32(24)) + (b >> u32(16)) + (b >> u32(8)) + b).astype(np.uint32) & u32(0xFF)


def required_k0_sets(path, max_entries=64):
    """对每条名字，求出能让它以 .hg3 结尾的 k0%52 集合。"""
    with open(path, 'rb') as f:
        d = f.read(8 + (max_entries + 2) * 0x48)
    count = struct.unpack('<I', d[4:8])[0]
    out = []
    for i in range(1, min(count, max_entries + 1)):
        base = 8 + i * 0x48
        raw = d[base:base + 0x40].split(b'\x00')[0]
        if len(raw) < 5:
            out.append(None)
            continue
        ok = []
        for k0 in range(52):
            k = k0
            buf = bytearray(raw)
            for idx, ch in enumerate(buf):
                j = kif.ALPHABET.find(bytes([ch]))
                if j != -1:
                    j -= k % 0x34
                    if j < 0:
                        j += 0x34
                    buf[idx] = kif.ALPHABET[0x33 - j]
                k += 1
            if bytes(buf).split(b'\x00')[0].lower().endswith(b'.hg3'):
                ok.append(k0)
        out.append(ok if ok else None)
    return out


def search(path, max_constraints=10, chunk=1 << 22, verbose=True):
    import time
    req = required_k0_sets(path, max_constraints + 2)
    usable = [(i + 1, sorted(set(s))) for i, s in enumerate(req) if s]
    if verbose:
        print('可用约束条目数:', len(usable))
        for i, s in usable[:10]:
            print('   条目%d 允许 k0%%52 ∈ %s' % (i, s))
    if not usable:
        return []
    usable = usable[:max_constraints]
    base_i, base_set = usable[0]
    rest_eff = usable[1:]

    total = 1 << 32
    found = []
    t0 = time.time()
    for start in range(0, total, chunk):
        seeds = np.arange(start, min(start + chunk, total), dtype=np.uint64)
        k = k0_array(seeds + base_i) % 52
        m = np.zeros(k.size, dtype=bool)
        for b in base_set:
            m |= (k == b)
        cand = seeds[m]
        for ci, cset in rest_eff:
            if cand.size == 0:
                break
            kk = k0_array(cand + ci) % 52
            ok = np.zeros(kk.size, dtype=bool)
            for b in cset:
                ok |= (kk == b)
            cand = cand[ok]
        if cand.size:
            found.extend(int(x) for x in cand)
            if verbose:
                print('  命中 %d 个: %s' % (cand.size, [hex(int(x)) for x in cand[:8]]))
        if verbose and (start // chunk) % 128 == 0:
            print('  进度 %.1f%%  已用 %.0f 秒' % (100.0 * start / total, time.time() - t0))
        if found and len(rest_eff) >= 4:
            break
    return found


if __name__ == '__main__':
    p = sys.argv[1]
    print('目标:', p)
    res = search(p)
    print('总共找到:', len(res) if res else 0)
    if res:
        for mk in res[:10]:
            print('  main_key = 0x%08X' % mk)
