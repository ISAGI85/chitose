@echo off
chcp 65001 >nul
title Chitose - Type mode
cd /d %~dp0
"%~dp0venv\Scripts\python.exe" -X utf8 "%~dp0scripts\launch_all.py" --text
echo.
pause
