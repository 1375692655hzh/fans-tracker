@echo off
rem fans-tracker 一键安装(新用户下载解压后双击这个)
chcp 65001 >nul
cd /d %~dp0
echo ================================================
echo   fans-tracker 一键安装
echo ================================================
python --version >nul 2>&1
if errorlevel 1 (
  echo.
  echo [X] 未检测到 Python, 请先安装:
  echo     1. 打开 https://www.python.org/downloads/ 下载 3.10 以上版本
  echo     2. 安装第一屏务必勾选 "Add Python to PATH"
  echo     3. 装完后重新双击本文件
  echo.
  pause
  exit /b 1
)
python main.py setup
echo.
echo 全部完成。正在打开控制台(浏览器地址栏输入 127.0.0.1:8787 可随时回来)…
python main.py web
pause
