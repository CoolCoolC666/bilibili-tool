@echo off
REM ============================================================
REM  B 站视频信息抓取工具  -  首次安装脚本
REM
REM  用途：第一次跑这个工具时双击它，会自动：
REM    1. 检查 Python（没装会提示去下载）
REM    2. 创建虚拟环境 venv\
REM    3. 用清华镜像装依赖（快，国内友好）
REM
REM  之后日常使用直接双击 start.bat 即可
REM ============================================================

chcp 65001 >nul
title B 站视频信息抓取工具 - 首次安装
cls

echo.
echo  ============================================
echo   B 站视频信息抓取工具  -  首次安装
echo  ============================================
echo.

REM ---- 1) 检查 Python ----
echo  [1/3] 检查 Python 环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [X] 没找到 Python！
    echo.
    echo  请先装 Python 3.9 或更高版本，装的时候**勾上 "Add Python to PATH"**。
    echo  下载地址：https://www.python.org/downloads/
    echo.
    echo  装完 Python 后，重新双击这个脚本即可。
    echo.
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo       检测到 %%v
echo.

REM ---- 2) 创建虚拟环境 ----
echo  [2/3] 创建虚拟环境 venv\
if not exist "venv\Scripts\python.exe" (
    python -m venv venv
    if errorlevel 1 (
        echo.
        echo  [X] 创建虚拟环境失败
        pause
        exit /b 1
    )
    echo       虚拟环境已创建
) else (
    echo       虚拟环境已存在，跳过
)
echo.

REM ---- 3) 装依赖 ----
echo  [3/3] 装依赖（用清华镜像，国内更快）...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple >nul
python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 (
    echo.
    echo  [X] 装依赖失败。请检查网络后重试。
    pause
    exit /b 1
)

echo.
echo  ============================================
echo   [OK] 安装完成！
echo  ============================================
echo.
echo   下一步：双击 start.bat 启动 Web 界面
echo           浏览器会自动打开 http://127.0.0.1:5050
echo.
pause
