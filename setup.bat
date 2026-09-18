@echo off
rem fans-tracker 一键安装(新用户下载后双击这个)
chcp 65001 >nul
cd /d %~dp0
echo ================================================
echo   fans-tracker 一键安装
echo ================================================
python --version >nul 2>&1 || (echo [X] 未检测到 Python, 请先安装 Python 3.10+ & pause & exit /b 1)
python main.py setup
echo.
echo 安装完成, 正在打开控制台…
python main.py web
pause
