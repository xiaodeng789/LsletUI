#!/usr/bin/env python3
"""
PyIsland Lite - 灵动岛启动脚本
简单的后台运行灵动岛
"""

import sys
import subprocess
from pathlib import Path

def main():
    """主函数"""
    print("=" * 50)
    print("PyIsland Lite - 灵动岛启动器")
    print("=" * 50)
    print()
    print("正在启动灵动岛...")
    print()
    
    backend_dir = Path(__file__).parent / "backend"
    service_script = backend_dir / "main.py"

    python_exe = sys.executable

    try:
        # 启动灵动岛服务（PySide6 版本，支持 iPhone 风格胶囊动画）
        subprocess.run([python_exe, str(service_script)],
                      cwd=str(backend_dir))
    except KeyboardInterrupt:
        print("\n灵动岛已停止")
    except Exception as e:
        print(f"启动失败: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())