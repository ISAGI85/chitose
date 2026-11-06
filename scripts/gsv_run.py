"""包一层再跑 GPT-SoVITS 的子脚本。

它的预处理脚本 import 了 `text.*`（在 GPT_SoVITS/ 下）和 `tools.*`（在根目录下），
而自带的嵌入式 Python 用的是 ._pth，不认 PYTHONPATH，所以只能显式补 sys.path。

用法： <runtime>/python.exe -I gsv_run.py <脚本相对路径> [参数...]
"""

import os
import runpy
import sys

GSV = r'D:/chitose/tools/GPT-SoVITS-v2pro-20250604-nvidia50'

for p in (os.path.join(GSV, 'GPT_SoVITS'), GSV):
    if p not in sys.path:
        sys.path.insert(0, p)

if len(sys.argv) < 2:
    raise SystemExit('用法: gsv_run.py <脚本> [参数...]')

target = sys.argv[1]
sys.argv = sys.argv[1:]
runpy.run_path(target, run_name='__main__')
