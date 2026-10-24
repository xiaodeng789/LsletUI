@echo off
echo ========================================
echo LsletUI - Nuitka多项目模式打包脚本
echo ========================================
echo.

cd /d "%~dp0backend"

echo 检查Python环境...
set "PYTHON_EXE=python"
where python >nul 2>&1
if errorlevel 1 (
    set "PYTHON_EXE=py"
    where py >nul 2>&1
    if errorlevel 1 (
        echo 错误: 未找到Python，请先安装 Python 3.10+
        pause
        exit /b 1
    )
)
%PYTHON_EXE% --version
if errorlevel 1 (
    echo 错误: 未找到Python
    pause
    exit /b 1
)

echo.
echo 生成图标...
%PYTHON_EXE% make_ico.py
if errorlevel 1 (
    echo 错误: 图标生成失败
    pause
    exit /b 1
)

echo.
echo 开始多项目模式打包...
echo 说明：同时打包 LsletUI 和 PyIslandLite 两个可执行文件
echo 这可能需要10-20分钟，请耐心等待...
echo.

rem 清理上次的产物目录，避免文件冲突
if exist "..\exe\LsletUI" (
    echo 清理旧产物目录 ..\exe\LsletUI ...
    rmdir /s /q "..\exe\LsletUI"
)
if exist "..\exe\PyIslandLite" (
    echo 清理旧产物目录 ..\exe\PyIslandLite ...
    rmdir /s /q "..\exe\PyIslandLite"
)
if exist "..\exe\main.build" (
    echo 清理旧构建目录 ..\exe\main.build ...
    rmdir /s /q "..\exe\main.build"
)

echo.
echo [1/2] 打包 LsletUI 主应用...
echo.

%PYTHON_EXE% -m nuitka ^
    --standalone ^
    --windows-console-mode=disable ^
    --assume-yes-for-downloads ^
    --windows-icon-from-ico=img/default_icon.ico ^
    --enable-plugin=pyside6 ^
    --include-qt-modules=QtMultimedia ^
    --include-data-files=widget.html=widget.html ^
    --include-data-files=img/default_icon.svg=img/default_icon.svg ^
    --include-data-dir=../frontend/dist=frontend/dist ^
    --output-filename=LsletUI.exe ^
    --output-dir=../exe ^
    --windows-product-version=1.0.0 ^
    --windows-file-description="LsletUI - Lightweight Dynamic Island Application" ^
    --windows-company-name="LsletUI Team" ^
    --windows-product-name="LsletUI" ^
    main.py

if errorlevel 1 (
    echo.
    echo LsletUI 打包失败！
    pause
    exit /b 1
)

rem standalone 产物目录名为 main.dist（按入口文件命名），重命名为 LsletUI
if exist "..\exe\main.dist" (
    if exist "..\exe\LsletUI" rmdir /s /q "..\exe\LsletUI"
    move "..\exe\main.dist" "..\exe\LsletUI" >nul
)

echo.
echo [2/2] 打包 PyIslandLite 灵动岛服务...
echo.

%PYTHON_EXE% -m nuitka ^
    --standalone ^
    --windows-console-mode=disable ^
    --assume-yes-for-downloads ^
    --windows-icon-from-ico=img/default_icon.ico ^
    --include-data-files=island_config.json=island_config.json ^
    --output-filename=PyIslandLite.exe ^
    --output-dir=../exe ^
    --windows-product-version=1.0.0 ^
    --windows-file-description="PyIslandLite - Island Background Service" ^
    --windows-company-name="PyIsland Team" ^
    --windows-product-name="PyIslandLite" ^
    island_service.py

if errorlevel 1 (
    echo.
    echo PyIslandLite 打包失败！
    pause
    exit /b 1
)

rem standalone 产物目录名为 island_service.dist，重命名为 PyIslandLite
if exist "..\exe\island_service.dist" (
    if exist "..\exe\PyIslandLite" rmdir /s /q "..\exe\PyIslandLite"
    move "..\exe\island_service.dist" "..\exe\PyIslandLite" >nul
)

echo.
echo ========================================
echo 多项目模式打包完成！
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