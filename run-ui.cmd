@echo off
cd /d D:\chitose
set WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=9222
venv\Scripts\python.exe -X utf8 scripts\launch_all.py --ui
