@echo off
chcp 65001 >nul 2>&1
echo ========================================
echo LsletUI 免费版 - Nuitka 多项目模式打包脚本
echo 说明：产物为 LsletUIFree.exe + PyIslandLite.exe
echo ========================================
echo.

cd /d "%~dp0backend"

rem ========================================
rem 自动检测 Python 路径（不再写死本机绝对路径）
rem ========================================
set "PYTHON_EXE="
where python >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_EXE=python"
    goto :found_python
)
where py >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_EXE=py"
    goto :found_python
)
echo 错误: 未找到 Python，请先安装 Python 3.10+ 并加入 PATH
pause
exit /b 1

:found_python
echo 使用 Python: %PYTHON_EXE%
%PYTHON_EXE% --version
echo.

echo 检查 Nuitka...
%PYTHON_EXE% -m nuitka --version >nul 2>&1
if errorlevel 1 (
    echo Nuitka 未安装，正在安装...
    %PYTHON_EXE% -m pip install nuitka ordered-set
    if errorlevel 1 (
        echo Nuitka 安装失败！
        pause
        exit /b 1
    )
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

rem 清理上次的产物目录，避免文件冲突
if exist "..\exe\LsletUIFree" (
    echo 清理旧产物目录 ..\exe\LsletUIFree ...
    rmdir /s /q "..\exe\LsletUIFree"
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
    --include-package=capsule_app ^
    --include-data-dir=img=img ^
    --include-data-files=island_config.json=island_config.json ^
    --include-data-files=capsule_app/liquid_glass.dll=capsule_app/liquid_glass.dll ^
    --output-filename=LsletUIFree.exe ^
    --output-dir=../exe ^
    --windows-product-version=0.2.0.0 ^
    --windows-file-description="LsletUI Free - Lightweight Dynamic Island Application" ^
    --windows-company-name="LsletUI Team" ^
    --windows-product-name="LsletUI Free" ^
    main.py

if errorlevel 1 (
    echo.
    echo LsletUIFree 打包失败！
    pause
    exit /b 1
)

rem standalone 产物目录名为 main.dist（按入口文件命名），重命名为 LsletUIFree
if exist "..\exe\main.dist" (
    if exist "..\exe\LsletUIFree" rmdir /s /q "..\exe\LsletUIFree"
    move "..\exe\main.dist" "..\exe\LsletUIFree" >nul
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
    --windows-product-version=0.1.0.0 ^
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
echo   1. LsletUI 免费版主应用: exe\LsletUIFree\LsletUIFree.exe
echo   2. PyIslandLite 服务:    exe\PyIslandLite\PyIslandLite.exe
echo.
echo 分发说明:
echo   - LsletUIFree: 灵动岛主应用（原生界面，含日志控制台）
echo   - PyIslandLite: 灵动岛后台服务（纯后台运行）
echo   - 分发时请分别打包整个 LsletUIFree 和 PyIslandLite 文件夹
echo ========================================
echo.
pause
