r"""把千岁本人的「非语言音」接进合成语音里。

TTS 只会念字——你让它说「ふふっ」，它读出的是字母；
真正的那一声笑，她自己在游戏里笑过。
这个模块负责：认出脑子标出来的心情标签，把她本人那一声贴到语音前面。

标签形态：[轻笑] 嗯，宝宝回来啦
导出目录：D:\chitose\out\sfx\<类>\   （由 sfx_build.py 生成）
"""

import os
import random
import re
import sys

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SFX_DIR = os.environ.get('GSV_SFX', os.path.join(ROOT, 'out', 'sfx'))

# 把音效的响度拉到跟她的合成语音齐平。
# 素材是从游戏里直接扒的，音量参差不齐——叹气那批只有语音的一半，
# 贴在前面就像从很远的地方飘过来，听着不像她。
# 她的 TTS 输出 RMS 大约 0.12，这里取 0.11 当目标。
TARGET_RMS = float(os.environ.get('GSV_SFX_RMS', '0.11'))
PEAK_LIMIT = 0.99     # 兜底，别真削
SOFT_KNEE = 0.70      # 软压缩的膝盖：超过这里就开始压尖峰
SOFT_RATIO = 2.5      # 膝盖以上压多少（越大压得越狠）

# 脑子写的中文标注（以及日语同义词）-> 音效文件夹名
ALIAS = {
    '轻笑': ['轻笑', '笑', '笑声', '笑意', '轻笑声', 'ふふ', 'うふふ', '微笑'],
    '亲吻': ['亲吻', '亲', '亲亲', 'キス', 'kiss', 'chu', '啵', '口づけ'],
    '叹气': ['叹气', '叹息', '叹气声', '放心', 'ため息', '呼'],
    '害羞': ['害羞', '羞', '脸红', '不好意思', '照れ', '害羞声'],
    '惊讶': ['惊讶', '吃惊', '意外', '惊讶声', '欸'],
    '难过': ['难过', '伤心', '低落', '委屈', '寂寞'],
    '犯困': ['犯困', '困', '打哈欠', '想睡', '睡意'],
    '亲密': ['亲密', '亲昵', '蹭', '腻'],
    # 「撒娇」从「亲密」里分出来（宝宝 2026-10-11：「那个亲密应该没有鼓脸那个表情
    # 这个表情应该是用于那种撒娇或者有点拿调皮的弟弟没办法的表情」）——
    # 撒娇和「拿你没办法」共用那张**鼓着脸、红扑扑**的（`00000z`）。
    # 这两类也可能没有音效素材，`splice()` 会照样跳过，脸是照换的。
    '撒娇': ['撒娇', '任性', '耍赖', '哼哼'],
    '无奈': ['无奈', '拿你没办法', '真拿你没办法', '没办法', '服了', '被打败'],
    # ⚠「无语」这类**没有音效素材**——`splice()` 会打一行「没有这类音，跳过」。
    #   没关系，它主要是给**界面换脸**用的：她有一张「白眼 + 问号」（`000001`），
    #   漫画式的无语，很可爱。宝宝 2026-10-11：
    #   「还有其他的表情可以根据说话的语境加上去」。
    # ⚠ 「无奈」**不能**留在这张的别名里：它有自己的脸（鼓着脸那张 `00000z`）。
    #   姐姐一开始两边都写了，结果嘴上标着 `[无奈]`、解析出来却是「无语」——
    #   因为 `_LOOKUP` 是按 ALIAS 顺序建的字典，后写的会把先写的盖掉。
    '无语': ['无语', '汗', '吐槽', '扶额', '沉默'],
    # 2026-10-28 宝宝在 17 张总览上逐张正名后加的心情。
    # 这几类没有音效素材，`splice()` 会跳过声音，但**脸照样换**。
    '说错话': ['说错话', '尴尬', '做错事', '说漏嘴', '搞砸', '糟了', '糟糕', '失误'],
    '疑惑': ['疑惑', '困惑', '不解', '纳闷'],
    '生气': ['生气', '不高兴', '恼', '吃醋'],
    '被调戏': ['被调戏', '调戏', '逗你', '逗我', '捉弄'],
    # 2026-10-28 宝宝说备用图也用上：懵 / 认真 / 张嘴 / 喊 / 微笑
    '懵': ['懵', '呆住', '愣住', '傻眼', '发呆'],
    '认真': ['认真', '正经', '严肃'],
    '张嘴': ['张嘴', '喂', '啊呜'],
    '卖萌': ['卖萌', '装可爱', '卖乖', '可爱'],
    '喊': ['喊', '呵斥', '吼', '凶'],
    '担心': ['担心', '担忧', '挂心', '不放心'],
    '微笑': ['微笑', '浅笑'],
}
_LOOKUP = {a: c for c, al in ALIAS.items() for a in al}

TAG_RE = re.compile(r'[\[【［（(]\s*([^\[\]【】［］（）()\s]{1,6})\s*[\]】］）)]')

_cache = {}
_recent = {}


def parse_tags(text):
    """把 [轻笑] 这类标注挑出来。返回 (标签列表, 剩下的正文)。"""
    tags = []

    def take(m):
        # 模型有时候会在标签里带标点，比如「[惊讶！]」；先把尾巴上的标点去掉。
        name = m.group(1).strip()
        name = re.sub(r'[！!。.，,、～~…・]+$', '', name).strip()
        cls = _LOOKUP.get(name)
        if cls:
            tags.append(cls)
            return ''
        return m.group(0)   # 认不出的方括号原样留着，别吃正文

    body = TAG_RE.sub(take, text)
    # 一次顶多两声，多了像抽风
    return tags[:2], body.strip()


def has_library():
    return os.path.isdir(SFX_DIR)


def _load(cls):
    """从某一类里随机挑一条，尽量不连着重复。"""
    if cls in _cache and _cache[cls]:
        pool = _cache[cls]
    else:
        d = os.path.join(SFX_DIR, cls)
        pool = []
        if os.path.isdir(d):
            for f in sorted(os.listdir(d)):
                if f.lower().endswith('.wav'):
                    try:
                        x, sr = sf.read(os.path.join(d, f), dtype='float32')
                        if x.ndim > 1:
                            x = x.mean(axis=1)
                        # 这里**不**调响度——存原始波形。
                        # 响度在 splice() 里按「当句语音有多响」现算，
                        # 因为不同的嘴输出音量不一样（老 GPT-SoVITS 约 0.12，
                        # 新 Qwen3-TTS 约 0.18），写死一个数就会一边轻一边响。
                        pool.append((np.asarray(x, dtype=np.float32), sr, f))
                    except Exception:
                        pass
        _cache[cls] = pool
    if not pool:
        return None
    last = _recent.get(cls)
    pick = None
    for _ in range(6):
        c = random.choice(pool)
        pick = c
        if c[2] != last:
            break
    _recent[cls] = pick[2]
    return pick[0], pick[1]


def _gain(x, target=None):
    """把一条音效拉到跟语音差不多的「听感响度」。

    为什么不能只乘一个系数：她的音效素材**峰值本来就是满的**（0.98），
    而语音也是顶到 0.93 的。同样顶满，语音密集、音效是一瞬间的尖峰，
    乘系数根本乘不上去——一乘就削波。
    所以步骤是：先按目标拉 → 把超过 SOFT 的部分软压 → 再补一次增益
    → 最后才做硬性防削波。软压缩只动尖峰，不动整条音色。
    """
    target = TARGET_RMS if target is None else target
    x = np.asarray(x, dtype=np.float32).reshape(-1)
    r = float(np.sqrt((x ** 2).mean()))
    if r < 1e-6:
        return x

    y = x * (target / r)
    for _ in range(3):                      # 压 → 补，来回几次逼近
        a = np.abs(y)
        over = a > SOFT_KNEE
        if not over.any():
            break
        # 软膝：膝盖以上的部分按比例压扁
        y[over] = (np.sign(y[over]) * (SOFT_KNEE + (a[over] - SOFT_KNEE)
                                       / (1.0 + (a[over] - SOFT_KNEE) * SOFT_RATIO)))
        r2 = float(np.sqrt((y ** 2).mean()))
        if r2 < 1e-6:
            break
        y = y * (target / r2)

    pk = float(np.abs(y).max())
    if pk > PEAK_LIMIT:                     # 兜底，别真削
        y = y * (PEAK_LIMIT / pk)
    return y.astype(np.float32)


def _fade(x, sr, ms=8.0):
    n = min(int(sr * ms / 1000), len(x) // 2)
    if n <= 0:
        return x
    ramp = np.linspace(0.0, 1.0, n, dtype=np.float32)
    x = x.copy()
    x[:n] *= ramp
    x[-n:] *= ramp[::-1]
    return x


def _same_sr(x, sr_from, sr_to):
    if sr_from == sr_to:
        return x
    g = np.gcd(int(sr_from), int(sr_to))
    return resample_poly(x, int(sr_to) // g, int(sr_from) // g).astype(np.float32)


def join(pieces, sr=None, gap=0.13):
    """把若干段 (波形, 采样率) 拼成一条。

    sr 不给就以**最后一段**（通常是语音）为准——那是主体，别动它的采样率，
    把短音效重采样过来就行。她的原声是 48000，TTS 吐出来是 32000。
    """
    pieces = [(x, s) for x, s in pieces if x is not None and len(x)]
    if not pieces:
        return None, None
    if sr is None:
        sr = pieces[-1][1]
    out = []
    for i, (x, s) in enumerate(pieces):
        x = _same_sr(np.asarray(x, dtype=np.float32).reshape(-1), s, sr)
        if i:
            out.append(np.zeros(int(sr * gap), dtype=np.float32))
        out.append(_fade(x, sr))
    return np.concatenate(out), sr


def splice(tags, speech, sr):
    """按标签把音效贴到语音前面。speech 可以是 None（只出声不说话）。

    响度**跟着这一句语音走**：先量语音有多响，再把手里的音效拉到同一个水平。
    不管换哪套嗓子上来都不会一边轻一边响。
    """
    target = TARGET_RMS
    if speech is not None and len(speech):
        s = np.asarray(speech, dtype=np.float32).reshape(-1)
        r = float(np.sqrt((s ** 2).mean()))
        if r > 1e-4:
            target = float(min(max(r, 0.05), 0.30))

    pieces = []
    for t in tags:
        got = _load(t)
        if got is not None:
            x, s = got
            pieces.append((_gain(x, target), s))
            print('[sfx] 贴一声「%s」（对齐到 %.3f）' % (t, target), flush=True)
        else:
            print('[sfx] 没有「%s」这类音，跳过' % t, flush=True)
    if speech is not None and len(speech):
        pieces.append((speech, sr))
    return join(pieces)


if __name__ == '__main__':
    if not has_library():
        print('音效库还没建：先跑 sfx_build.py')
        sys.exit(1)
    for d in sorted(os.listdir(SFX_DIR)):
        p = os.path.join(SFX_DIR, d)
        if os.path.isdir(p):
            n = len([f for f in os.listdir(p) if f.endswith('.wav')])
            print('  %-6s %3d 条' % (d, n))
    print()
    print(parse_tags('[轻笑] 嗯，宝宝回来啦~'))
    print(parse_tags('よくできましたね、えらいえらい'))
    print(parse_tags('「宝宝」这个词（はい）'))
