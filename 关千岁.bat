@echo off
chcp 65001 >nul
title Stop Chitose
cd /d D:\chitose
D:\chitose\venv\Scripts\python.exe -X utf8 D:\chitose\scripts\launch_all.py --stop
echo.
pause
