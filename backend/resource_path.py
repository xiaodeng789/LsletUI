#!/usr/bin/env python3
"""
资源路径兼容模块
支持两种运行环境：
1. 开发源码模式 (直接运行 .py)
2. PyInstaller/Nuitka 打包本地运行 (dist目录下双击exe)

使用方式：
    from resource_path import get_resource_path, get_config_path
    icon = get_resource_path("img/default_icon.svg")
    config = get_config_path()
"""

import sys
from pathlib import Path


def get_base_path() -> Path:
    """
    获取基础路径，兼容多种运行环境

    1. 开发源码模式：本文件所在目录 (backend/)
    2. Nuitka standalone（新版 _internal 布局）：<exe目录>/_internal/
       Nuitka 2.4+ 会把 --include-data-* 资源全部放到 _internal/ 下
    3. PyInstaller onedir / Nuitka 旧版平铺布局：exe 所在目录

    Returns:
        Path: 基础路径对象
    """
    # Nuitka 编译运行时会向每个模块注入 __compiled__ 全局变量
    if "__compiled__" in globals():
        exe_dir = Path(sys.executable).resolve().parent
        internal_dir = exe_dir / "_internal"
        # 新版 Nuitka standalone：img/、frontend/ 等数据文件在 _internal/ 下
        if internal_dir.is_dir() and (internal_dir / "img").is_dir():
            return internal_dir
        # 旧版 Nuitka（平铺布局）：资源就在 exe 同级
        return exe_dir

    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后 (onedir 模式)
        exe_dir = Path(sys.executable).resolve().parent
        # PyInstaller 6.x+ 把 datas 放在 _internal/ 下
        internal_dir = exe_dir / "_internal"
        if internal_dir.is_dir() and (internal_dir / "img").is_dir():
            return internal_dir
        return exe_dir
    else:
        # 开发模式：使用当前文件所在目录 (backend/)
        return Path(__file__).resolve().parent


def get_resource_path(relative_path: str) -> Path:
    """
    获取资源文件的绝对路径

    Args:
        relative_path: 相对于项目根目录的路径，例如 "img/icon.svg"

    Returns:
        Path: 资源文件的绝对路径

    Examples:
        icon = get_resource_path("img/default_icon.svg")
        frontend = get_resource_path("frontend/dist/index.html")
        config = get_resource_path("island_config.json")
    """
    base = get_base_path()
    resource = base / relative_path
    return resource


def get_resource_str(relative_path: str) -> str:
    """获取资源文件的绝对路径字符串版本"""
    return str(get_resource_path(relative_path))


def get_frontend_path() -> Path:
    """获取前端资源目录路径

    打包后前端随资源根目录放在 frontend/dist；
    开发模式下前端源码位于项目根 frontend/dist（与 backend/ 平级）。
    """
    bundled = get_resource_path("frontend/dist")
    if bundled.is_dir():
        return bundled
    # 开发模式：backend/ 的上级目录（项目根）下的 frontend/dist
    dev_layout = get_base_path().parent / "frontend" / "dist"
    if dev_layout.is_dir():
        return dev_layout
    return bundled


def get_frontend_url() -> str:
    """获取前端入口URL（用于QWebEngineView加载）"""
    index_html = get_frontend_path() / "index.html"
    if index_html.exists():
        return index_html.as_uri()
    return ""


def get_config_path() -> Path:
    """获取配置文件路径"""
    return get_resource_path("island_config.json")


def ensure_config_dir():
    """确保配置文件目录存在"""
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)


# 便捷别名
base_path = get_base_path
resource_path = get_resource_path
resource_str = get_resource_str
frontend_path = get_frontend_path
frontend_url = get_frontend_url


if __name__ == "__main__":
    print("=" * 50)
    print("资源路径兼容模块测试")
    print("=" * 50)
    print(f"运行模式: {'打包' if getattr(sys, 'frozen', False) else '开发'}")
    print(f"基础路径: {get_base_path()}")
    print(f"前端路径: {get_frontend_path()}")
    print(f"前端URL:  {get_frontend_url()}")
    print(f"配置路径: {get_config_path()}")
    print("=" * 50)