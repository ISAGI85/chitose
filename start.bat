@echo off
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
