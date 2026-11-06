@echo off
rem Development launcher: opens the window with WebView2 remote debugging on.
cd /d %~dp0
set WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=--remote-debugging-port=9222
"%~dp0venv\Scripts\python.exe" -X utf8 "%~dp0scripts\launch_all.py" --ui
