@echo off
rem ============================================================
rem  千岁 - 强制声音版启动
rem
rem  做什么：不看 config.json 的 voice.enabled，直接打开声音，
rem          先把 GPT-SoVITS 嗓子和转接头叫起来，再开窗。
rem
rem  前提：已经按 README 的「可选一：让她出声」放好了
rem        GPT-SoVITS v2Pro 整合包、权重和参考音频。
rem  需要：NVIDIA 显卡。第一次加载模型要一两分钟。
rem ============================================================
chcp 65001 >nul
title 千岁 - 声音版
cd /d %~dp0

if not exist venv\Scripts\python.exe (
  echo 还没装好，先双击 setup.bat。
  pause
  exit /b 1
)

set CHITOSE_VOICE=on
venv\Scripts\python.exe -X utf8 scripts\launch_all.py --ui
pause
