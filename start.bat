@echo off
REM ============================================================
REM  B 站视频信息抓取工具  -  启动脚本（日常使用）
REM
REM  用途：双击启动 Web 界面（http://127.0.0.1:5050）
REM  前提：已经跑过 install.bat
REM ============================================================

chcp 65001 >nul
title B 站视频信息抓取工具
cls

echo.
echo  ============================================
echo   B 站视频信息抓取工具  -  Web 版
echo  ============================================
echo.

REM 检查虚拟环境
if not exist "venv\Scripts\python.exe" (
    echo  [X] 没找到虚拟环境！
    echo  请先双击 install.bat 完成首次安装。
    echo.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

REM 2 秒后自动打开浏览器
echo  启动 Web 服务中...
echo  2 秒后浏览器会自动打开 http://127.0.0.1:5050
echo  按 Ctrl+C 可停止服务
echo.

start "" cmd /c "timeout /t 2 /nobreak >nul && start "" http://127.0.0.1:5050"

python run_web.py

echo.
echo  服务已停止
pause
