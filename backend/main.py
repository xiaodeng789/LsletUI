#!/usr/bin/env python3
"""
LsletUI - 轻量级灵动岛应用
主入口文件
"""

import sys
import os
import gc
from pathlib import Path

# 添加当前目录到Python路径
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

# 关闭 Python 自动循环垃圾回收（关键稳定性措施）：
# 本应用多个后台线程使用 COM（winrt 通知、pywin32 蓝牙 STA）。COM 接口指针必须在创建它的套间线程内 Release，
# 而自动 GC 可能在任意线程（如下载监控线程 json 解析触发分配）回收这些
# 指针，跨套间调用 vtable 会直接 0xC0000005 访问违例杀死进程。
# 各 COM 线程在自己的循环内/退出前显式 gc.collect()，在所属套间内回收。
gc.disable()

# 导入资源路径兼容模块
from resource_path import get_resource_path, get_config_path

def main():
    """主函数"""
    try:
        # 延迟导入以优化启动时间（capsule_app.main 内含单实例互斥锁检查）
        from capsule_app.main import run
        
        # 运行应用
        exit_code = run()
        sys.exit(exit_code)
        
    except ImportError as e:
        print(f"导入错误: {e}")
        print("请确保已安装所有依赖: pip install -r requirements.txt")
        sys.exit(1)
    except Exception as e:
        print(f"启动错误: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()