@echo off
echo ========================================
echo LsletUI - 轻量级灵动岛应用
echo ========================================
echo.

cd /d "%~dp0\backend"

echo 检查Python环境...
python --version
if errorlevel 1 (
    echo 错误: 未找到Python，请安装Python 3.9或更高版本
    pause
    exit /b 1
)

echo.
echo 检查依赖...
pip show PySide6 >nul 2>&1
if errorlevel 1 (
    echo 正在安装依赖...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo 错误: 依赖安装失败
        pause
        exit /b 1
    )
)

echo.
echo 启动LsletUI...
python main.py

if errorlevel 1 (
    echo.
    echo 应用异常退出
    pause
)