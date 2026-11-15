@echo off
rem LsletUI 液态玻璃层构建脚本（VS 18 Community + CMake）
setlocal
cd /d %~dp0

set BUILD_DIR=build
set DEST_DIR=..\..\backend\capsule_app

if not exist %BUILD_DIR% mkdir %BUILD_DIR%
cd %BUILD_DIR%

cmake -G "Visual Studio 18 2026" -A x64 ..
if errorlevel 1 goto :err

cmake --build . --config Release
if errorlevel 1 goto :err

copy /y Release\liquid_glass.dll %DEST_DIR%\liquid_glass.dll
if errorlevel 1 goto :err

echo.
echo [OK] liquid_glass.dll 已生成并拷贝到 %DEST_DIR%
goto :eof

:err
echo.
echo [FAIL] 构建失败
exit /b 1
