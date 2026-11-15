#!/usr/bin/env python3
"""LsletUI - 启动硬件预检（一次性）

程序启动时执行一次硬件能力检测，结果缓存于模块级单例，
运行期间不重复检测；更换硬件后需重启软件才会重新判定。

判定标准：
- 系统：Windows 10 21H2 (build 19044) 及以上 / Win11；32 位系统直接不支持
- 显卡：NVIDIA RTX 20 系列及以上（A 卡 / GTX 10 系及更早均不支持）
- 物理内存：≥ 16GB（读整机物理内存）
- CPU：不拦截，仅展示核数（最低 4 核，推荐 6 核及以上）

检测在 C++ 底层完成（liquid_glass.dll 的 lg_hw_precheck 导出），
Python 通过 ctypes 取结果。DLL 加载失败时安全降级为"不支持"。

另有"额外依赖检测"（WebView2 运行时、VC++ 2015-2022 x64 运行库），
与特效锁定相互独立，缺失时由启动流程弹窗引导安装。
"""
import ctypes
import os
import sys
import winreg
from pathlib import Path

_DLL_DIR = Path(__file__).resolve().parent

# 依赖下载地址
WEBVIEW2_URL = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
VCREDIST_URL = "https://aka.ms/vs/17/release/vc_redist.x64.exe"


class _LgHwPrecheck(ctypes.Structure):
    _fields_ = [
        ("os_ok", ctypes.c_int),
        ("gpu_ok", ctypes.c_int),
        ("mem_ok", ctypes.c_int),
        ("cpu_cores", ctypes.c_int),
        ("supported", ctypes.c_int),
        ("os_build", ctypes.c_int),
        ("is_64bit", ctypes.c_int),
        ("mem_total_bytes", ctypes.c_ulonglong),
        ("gpu_name", ctypes.c_char * 128),
    ]


def _default_result():
    """DLL 不可用时的安全降级结果：不支持特效，但其余信息尽量可读。"""
    return {
        "supported": False,
        "os_ok": False,
        "gpu_ok": False,
        "mem_ok": False,
        "cpu_cores": os.cpu_count() or 0,
        "os_build": 0,
        "is_64bit": sys.maxsize > 2**32,
        "mem_total_bytes": 0,
        "gpu_name": "",
        "reason": "dll_missing",
    }


class HwPrecheck:
    """硬件预检单例（进程内只检测一次）"""

    _instance = None

    def __init__(self):
        self._result = None
        self._deps = None

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # --- 硬件能力（液态玻璃） ---
    def result(self):
        """返回预检结果 dict；进程内首次调用时真正执行，之后直接复用。"""
        if self._result is None:
            self._result = self._run()
        return self._result

    def _run(self):
        if sys.platform != "win32":
            return _default_result()

        dll_path = _DLL_DIR / "liquid_glass.dll"
        if not dll_path.exists():
            print(f"[HwPrecheck] 未找到 {dll_path}，判定不支持")
            return _default_result()
        try:
            dll = ctypes.CDLL(str(dll_path))
            dll.lg_hw_precheck.argtypes = [ctypes.POINTER(_LgHwPrecheck)]
            dll.lg_hw_precheck.restype = ctypes.c_int
            p = _LgHwPrecheck()
            dll.lg_hw_precheck(ctypes.byref(p))
            gpu_name = bytes(p.gpu_name).decode("utf-8", "ignore").rstrip("\x00")
            result = {
                "supported": bool(p.supported),
                "os_ok": bool(p.os_ok),
                "gpu_ok": bool(p.gpu_ok),
                "mem_ok": bool(p.mem_ok),
                "cpu_cores": int(p.cpu_cores),
                "os_build": int(p.os_build),
                "is_64bit": bool(p.is_64bit),
                "mem_total_bytes": int(p.mem_total_bytes),
                "gpu_name": gpu_name,
                "reason": self._reason(p),
            }
            print(
                f"[HwPrecheck] supported={result['supported']} "
                f"os(build={result['os_build']},64bit={result['is_64bit']},ok={result['os_ok']}) "
                f"gpu({gpu_name or 'unknown'},ok={result['gpu_ok']}) "
                f"mem({result['mem_total_bytes'] / 2**30:.1f}GB,ok={result['mem_ok']}) "
                f"cpu_cores={result['cpu_cores']}"
            )
            return result
        except Exception as e:
            print(f"[HwPrecheck] 检测失败: {e}")
            return _default_result()

    @staticmethod
    def _reason(p):
        if not p.is_64bit:
            return "os_32bit"
        if not p.os_ok:
            return "os_version"
        if not p.gpu_ok:
            return "gpu"
        if not p.mem_ok:
            return "memory"
        return ""

    # --- 额外依赖检测（独立于特效锁定） ---
    def dependencies(self):
        """返回 {'webview2': bool, 'vcredist': bool}。缺失才弹窗，缓存复用。"""
        if self._deps is None:
            self._deps = {
                "webview2": self._has_webview2(),
                "vcredist": self._has_vcredist(),
            }
            missing = [k for k, v in self._deps.items() if not v]
            if missing:
                print(f"[HwPrecheck] 依赖缺失: {', '.join(missing)}")
        return self._deps

    @staticmethod
    def _has_webview2():
        """检测 WebView2 Runtime（Evergreen）。读注册表版本号。"""
        if sys.platform != "win32":
            return True
        subkey = r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(root, subkey, 0, winreg.KEY_READ) as k:
                    ver, _ = winreg.QueryValueEx(k, "pv")
                    if ver and str(ver) not in ("0.0.0.0",):
                        return True
            except OSError:
                continue
        return False

    @staticmethod
    def _has_vcredist():
        """检测 VC++ 2015-2022 x64 运行库（v14，兼容 VS2015~2026 产物）。"""
        if sys.platform != "win32":
            return True
        subkey = r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64"
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(root, subkey, 0,
                                    winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
                    installed, _ = winreg.QueryValueEx(k, "Installed")
                    if int(installed) == 1:
                        return True
            except OSError:
                continue
        # 兜底：System32 下关键 DLL
        win_dir = os.environ.get("SystemRoot", r"C:\Windows")
        sys32 = Path(win_dir) / "System32"
        return (sys32 / "vcruntime140.dll").exists() and (sys32 / "msvcp140.dll").exists()
