r"""把千岁那五句开场问候**提前合成成 wav**，放进界面里。

为什么要提前做：姐姐原来是把问候直接写在屏幕上的，不出声；
改成现场合成又太慢（一进界面要先等嗓子）。提前做好就是点开即响。

用法（转接头要在跑）：
    python scripts/make_greetings.py
改文案就改下面 GREETINGS，重跑一次。
"""
import json
import os
import sys
import urllib.request

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, 'app', 'web', 'assets', 'voice')
SHIM = 'http://127.0.0.1:9882/v1/audio/speech'

# key -> (时段, 日语, 中文)
GREETINGS = {
    'morning':   ('05:00-11:00', 'おはよう。……ちゃんと起きられたね、えらい。',
                  '早呀。……今天也自己爬起来了，好乖。'),
    'noon':      ('11:00-13:00', 'お昼だよ。……おなか、すいてない？',
                  '到中午了哦。……肚子饿不饿？'),
    'afternoon': ('13:00-18:00', '……あ、来てくれた。ちょっと休憩する？',
                  '……啊，你来了。要不要歇一会儿？'),
    'evening':   ('18:00-22:00', 'おかえり。……今日はどうだった？',
                  '回来啦。……今天过得怎么样？'),
    'night':     ('22:00-05:00', '……まだ起きてたの。うん、一緒にいよう。',
                  '……还醒着呀。嗯，姐姐陪着你。'),
}


def synth(text):
    body = json.dumps({'model': 'chitose', 'voice': 'chitose',
                       'input': text, 'response_format': 'wav'}).encode('utf-8')
    req = urllib.request.Request(SHIM, data=body,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=600) as r:
        return r.read()


def main():
    os.makedirs(OUT, exist_ok=True)
    index = {}
    for key, (span, jp, cn) in GREETINGS.items():
        dst = os.path.join(OUT, 'greet_%s.wav' % key)
        if os.path.exists(dst) and '--force' not in sys.argv:
            print('%-10s 已存在，跳过（要重做加 --force）' % key)
        else:
            raw = synth(jp)
            with open(dst, 'wb') as f:
                f.write(raw)
            print('%-10s %6.1f KB  %s' % (key, len(raw) / 1024, jp))
        index[key] = {'span': span, 'file': 'greet_%s.wav' % key, 'jp': jp, 'cn': cn}

    with open(os.path.join(OUT, 'greetings.json'), 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
    print('-> %s' % os.path.join(OUT, 'greetings.json'))


if __name__ == '__main__':
    main()
