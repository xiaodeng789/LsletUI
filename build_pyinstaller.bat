@echo off
chcp 65001 >nul 2>&1
echo ========================================
echo LsletUI - PyInstaller 多项目打包脚本
echo onedir 模式 / 禁用 UPX / 带版本信息
echo ========================================
echo.

cd /d "%~dp0backend"

rem ========================================
rem 自动检测 Python 路径
rem ========================================
set "PYTHON_EXE="

rem 尝试系统 PATH 中的 python
where python >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_EXE=python"
    goto :found_python
)

rem 尝试 py launcher
where py >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_EXE=py"
    goto :found_python
)

echo 错误: 未找到 Python，请先安装 Python 3.10+
pause
exit /b 1

:found_python
echo 使用 Python: %PYTHON_EXE%
%PYTHON_EXE% --version
echo.

rem ========================================
rem 检查 PyInstaller
rem ========================================
echo 检查 PyInstaller...
%PYTHON_EXE% -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo PyInstaller 未安装，正在安装...
    %PYTHON_EXE% -m pip install pyinstaller
    if errorlevel 1 (
        echo PyInstaller 安装失败！
        pause
        exit /b 1
    )
)
%PYTHON_EXE% -m PyInstaller --version
echo.

rem ========================================
rem 确保 exe 目录存在
rem ========================================
if not exist "..\exe" mkdir "..\exe"

rem ========================================
rem 清理旧产物目录
rem ========================================
echo 清理旧产物目录...
if exist "..\exe\LsletUI" (
    echo   清理 ..\exe\LsletUI ...
    rmdir /s /q "..\exe\LsletUI"
)
if exist "..\exe\PyIslandLite" (
    echo   清理 ..\exe\PyIslandLite ...
    rmdir /s /q "..\exe\PyIslandLite"
)

echo.
echo 开始多项目打包...
echo 说明：同时打包 LsletUI 和 PyIslandLite 两个可执行文件
echo 这可能需要 10-20 分钟，请耐心等待...
echo.

rem ========================================
rem [1/2] 打包 LsletUI 主应用
rem ========================================
echo ========================================
echo [1/2] 打包 LsletUI 主应用 (PySide6 灵动岛)
echo ========================================
echo.

%PYTHON_EXE% -m PyInstaller ^
    --noconfirm ^
    --clean ^
    LsletUI.spec ^
    --distpath="../exe" ^
    --workpath="../exe/build_LsletUI"

if errorlevel 1 (
    echo.
    echo [错误] LsletUI 打包失败！
    pause
    exit /b 1
)

echo.
echo [LsletUI] 打包完成！
echo.

rem ========================================
rem [2/2] 打包 PyIslandLite 后台服务
rem ========================================
echo ========================================
echo [2/2] 打包 PyIslandLite 后台服务
echo ========================================
echo.

%PYTHON_EXE% -m PyInstaller ^
    --noconfirm ^
    --clean ^
    PyIslandLite.spec ^
    --distpath="../exe" ^
    --workpath="../exe/build_PyIslandLite"

if errorlevel 1 (
    echo.
    echo [错误] PyIslandLite 打包失败！
    pause
    exit /b 1
)

echo.
echo [PyIslandLite] 打包完成！
echo.

rem ========================================
rem 清理构建临时文件
rem ========================================
echo 清理构建临时文件...
if exist "..\exe\build_LsletUI" rmdir /s /q "..\exe\build_LsletUI"
if exist "..\exe\build_PyIslandLite" rmdir /s /q "..\exe\build_PyIslandLite"

rem ========================================
rem 代码签名（降低杀毒误报）
rem ========================================
echo.
echo 正在给 exe 签名...
powershell -NoProfile -ExecutionPolicy Bypass -File "sign_exe.ps1"
if errorlevel 1 (
    echo [警告] 签名失败，exe 未签名（不影响运行，但可能被杀软误报）
) else (
    echo [签名完成]
)

echo.
echo ========================================
echo PyInstaller 多项目打包完成！
echo.
echo 可执行文件位置:
echo   1. LsletUI 主应用:     exe\LsletUI\LsletUI.exe
echo   2. PyIslandLite 服务:  exe\PyIslandLite\PyIslandLite.exe
echo.
echo 分发说明:
echo   - LsletUI: 灵动岛主应用（带前端界面）
echo   - PyIslandLite: 灵动岛后台服务（纯后台运行）
echo   - 分发时请分别打包整个 LsletUI 和 PyIslandLite 文件夹
echo ========================================
echo.
pause