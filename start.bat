@echo off
rem ============================================================
rem  千岁 - 常规启动
rem
rem  做什么：读 config.json，然后打开桌面窗口。
rem    - voice.enabled 为 false（默认）：静音版，只打字、不加载声音模型
rem    - voice.enabled 为 true：先把 GPT-SoVITS 嗓子叫起来，再开窗
rem
rem  什么时候跑：第一次先跑 setup.bat，以后双击这个就行。
rem  想不改配置直接听声音：双击 start-voice.bat。
rem ============================================================
chcp 65001 >nul
title 千岁
cd /d %~dp0

if not exist venv\Scripts\python.exe (
  echo 还没装好，先双击 setup.bat。
  pause
  exit /b 1
)

venv\Scripts\python.exe -X utf8 scripts\launch_all.py --ui
pause
