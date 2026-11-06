@echo off
chcp 65001 >nul
title 千岁 - 安装
cd /d %~dp0

where py >nul 2>nul
if errorlevel 1 (
  echo.
  echo 没找到 Python。
  echo 先去 python.org 下载 3.10 以上版本，安装时勾选「Add Python to PATH」。
  echo.
  pause
  exit /b 1
)

if not exist venv\Scripts\python.exe (
  echo 正在建虚拟环境...
  py -3 -m venv venv
)

echo 正在装依赖，第一次要几分钟...
venv\Scripts\python.exe -m pip install -U pip
venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo 依赖装失败了，把上面的报错发出来看看。
  pause
  exit /b 1
)

if not exist config.json (
  copy config.example.json config.json >nul
  echo.
  echo 已经生成 config.json。
  echo 打开它，把 brain 里的 base_url、api_key、model 填好。
  echo 如果你已经放好了声音包，把 voice.enabled 改成 true。
)

echo.
echo 装好啦。下一步：编辑 config.json，然后双击 start.bat。
pause
