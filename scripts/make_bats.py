r"""重做那几个双击用的 bat。

三个坑（都踩过，别再踩）：
  1. **bat 必须 CRLF 换行**。写成 LF 的话 cmd 会把几行粘在一起。
  2. **别用 bash 的 `python -c "..."` 生成**。bash 会把 `\\` 吃成 `\`，
     于是 `D:\chitose\venv` 里的 `\v` 变成垂直制表符，
     路径就成了 `D:\chitoseenv`。写到文件里跑，不经过 bash 的引号。
  3. **bat 里别写中文**。`chcp 65001` 只管得住 Python 的输出，
     cmd 自己解析 bat 里的中文 `echo` 时照样会把行劈开
     （宝宝那边看到的是「'��出，输入' 不是内部或外部命令」）。
     **所以 bat 一律纯英文，中文提示全部由 Python 印**（那边编码是对的）。
"""

import io
import os

D = 'D:\\chitose'
PY = D + '\\venv\\Scripts\\python.exe'
LAUNCH = D + '\\scripts\\launch_all.py'

HEAD = ['@echo off', 'chcp 65001 >nul']

BATS = {
    # 「开千岁」现在是**窗口**（app/server.py），不是控制台
    # （以前还有个 start_chitose.bat，跟这个是同一行命令，2026-10-25 去重删掉了）
    '开千岁.bat': ('Chitose', PY + ' -X utf8 ' + LAUNCH + ' --ui'),
    # 控制台那套留着当退路：窗口坏了还能打字找她
    '打字找千岁.bat': ('Chitose - Type mode', PY + ' -X utf8 ' + LAUNCH + ' --text'),
    '关千岁.bat': ('Stop Chitose', PY + ' -X utf8 ' + LAUNCH + ' --stop'),
}


def main():
    for name, (title, cmd) in BATS.items():
        lines = HEAD + [
            'title ' + title,
            'cd /d ' + D,
            cmd,
            'echo.',
            'pause',
        ]
        path = os.path.join(D, name)
        # newline='\r\n' 是关键——bat 必须是 CRLF
        with io.open(path, 'w', encoding='utf-8', newline='\r\n') as f:
            f.write('\n'.join(lines) + '\n')
        bad = [l for l in lines if any(ord(c) > 127 for c in l)]
        print('%-22s %s  %s'
              % (name, 'OK' if not bad else '★还有非 ASCII：%r' % bad, title))


if __name__ == '__main__':
    main()
