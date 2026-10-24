#!/usr/bin/env python3
"""
LsletUI - 应用测试脚本
"""

import sys
import os
from pathlib import Path

# 添加当前目录到Python路径
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

def test_imports():
    """测试所有模块是否可以正常导入"""
    print("测试模块导入...")
    
    try:
        from capsule_app.main import show_toast, run
        print("✓ main模块导入成功")
    except ImportError as e:
        print(f"✗ main模块导入失败: {e}")
        return False
    
    # 测试蓝牙和进程监控模块（需要PySide6）
    try:
        from capsule_app.bluetooth_backend import BluetoothBackend
        print("✓ bluetooth_backend模块导入成功")
    except ImportError as e:
        print(f"⚠ bluetooth_backend模块导入失败（PySide6未安装）: {e}")
        # 不返回False，因为这是可选的
    
    try:
        from capsule_app.process_monitor_backend import ProcessMonitorBackend
        print("✓ process_monitor_backend模块导入成功")
    except ImportError as e:
        print(f"⚠ process_monitor_backend模块导入失败（PySide6未安装）: {e}")
        # 不返回False，因为这是可选的
    
    return True

def test_tkinter():
    """测试tkinter后端"""
    print("\n测试tkinter后端...")
    
    try:
        import tkinter as tk
        print(f"✓ tkinter版本: {tk.TkVersion}")
        
        # 创建测试窗口
        root = tk.Tk()
        root.title("LsletUI 测试")
        root.geometry("300x200")
        
        # 测试标签
        label = tk.Label(root, text="LsletUI 测试成功！", font=('Arial', 12))
        label.pack(pady=20)
        
        # 测试按钮
        test_button = tk.Button(root, text="测试按钮", command=lambda: print("按钮被点击"))
        test_button.pack(pady=10)
        
        # 自动关闭
        root.after(3000, root.destroy)
        
        print("✓ tkinter窗口创建成功")
        root.mainloop()
        print("✓ tkinter主循环正常结束")
        
        return True
    except Exception as e:
        print(f"✗ tkinter测试失败: {e}")
        return False

def test_capsule_window():
    """测试胶囊窗口组件"""
    print("\n测试胶囊窗口组件...")
    
    try:
        # 检查widget.html是否存在
        widget_path = current_dir / "widget.html"
        if widget_path.exists():
            print(f"✓ widget.html存在: {widget_path}")
        else:
            print(f"✗ widget.html不存在: {widget_path}")
            return False
        
        # 检查图标文件
        img_dir = current_dir / "img"
        if img_dir.exists():
            icons = list(img_dir.glob("*.svg")) + list(img_dir.glob("*.ico")) + list(img_dir.glob("*.png"))
            print(f"✓ 找到{len(icons)}个图标文件")
        else:
            print("✗ 图标目录不存在")
            return False
        
        return True
    except Exception as e:
        print(f"✗ 胶囊窗口测试失败: {e}")
        return False

def test_frontend_structure():
    """测试前端结构"""
    print("\n测试前端结构...")
    
    frontend_dir = current_dir.parent / "frontend"
    if not frontend_dir.exists():
        print("✗ 前端目录不存在")
        return False
    
    # 检查关键文件
    key_files = [
        "package.json",
        "vite.config.js",
        "index.html",
        "src/main.js",
        "src/App.vue"
    ]
    
    for file in key_files:
        file_path = frontend_dir / file
        if file_path.exists():
            print(f"✓ {file} 存在")
        else:
            print(f"✗ {file} 不存在")
            return False
    
    # 检查功能模块
    features_dir = frontend_dir / "src" / "features"
    if features_dir.exists():
        features = ["bluetooth", "todo", "transfer", "about", "wait"]
        for feature in features:
            feature_dir = features_dir / feature
            if feature_dir.exists():
                print(f"✓ {feature} 模块存在")
            else:
                print(f"✗ {feature} 模块不存在")
    
    return True

def test_memory_optimization():
    """测试内存优化配置"""
    print("\n测试内存优化配置...")
    
    try:
        # 检查requirements.txt
        req_path = current_dir / "requirements.txt"
        if req_path.exists():
            with open(req_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if "PySide6" in content:
                    print("✓ requirements.txt包含PySide6依赖")
                else:
                    print("✗ requirements.txt缺少PySide6依赖")
        
        # 检查pyproject.toml
        pyproject_path = current_dir / "pyproject.toml"
        if pyproject_path.exists():
            print("✓ pyproject.toml存在")
        
        return True
    except Exception as e:
        print(f"✗ 内存优化配置测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("=" * 50)
    print("LsletUI - 应用测试")
    print("=" * 50)
    
    tests = [
        ("模块导入测试", test_imports),
        ("tkinter后端测试", test_tkinter),
        ("胶囊窗口测试", test_capsule_window),
        ("前端结构测试", test_frontend_structure),
        ("内存优化测试", test_memory_optimization),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n{'=' * 30}")
        print(f"运行测试: {test_name}")
        print(f"{'=' * 30}")
        
        try:
            if test_func():
                passed += 1
                print(f"✓ {test_name} 通过")
            else:
                print(f"✗ {test_name} 失败")
        except Exception as e:
            print(f"✗ {test_name} 异常: {e}")
    
    print(f"\n{'=' * 50}")
    print(f"测试结果: {passed}/{total} 测试通过")
    print(f"{'=' * 50}")
    
    if passed == total:
        print("所有测试通过！LsletUI 准备就绪。")
        return 0
    else:
        print("部分测试失败，请检查相关模块。")
        return 1

if __name__ == "__main__":
    sys.exit(main())