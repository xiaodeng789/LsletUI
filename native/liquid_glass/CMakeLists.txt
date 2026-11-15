cmake_minimum_required(VERSION 3.20)
project(liquid_glass LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 静态链接 CRT，避免目标机器缺 VC 运行时
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")

add_library(liquid_glass SHARED
    src/liquid_glass.cpp
    src/liquid_glass.h
)

target_include_directories(liquid_glass PRIVATE src)

target_compile_definitions(liquid_glass PRIVATE
    WIN32_LEAN_AND_MEAN
    NOMINMAX
    UNICODE
    _UNICODE
)

# 源码含 UTF-8 注释，强制编译器按 UTF-8 解析
target_compile_options(liquid_glass PRIVATE /utf-8)

# DXGI 1.2+ / D3D11 / DirectComposition / DWM
target_link_libraries(liquid_glass PRIVATE
    d3d11
    dxgi
    dcomp
    dwmapi
    d3dcompiler
    user32
    gdi32
)

# 输出名固定为 liquid_glass.dll
set_target_properties(liquid_glass PROPERTIES
    OUTPUT_NAME "liquid_glass"
    PREFIX ""
)
