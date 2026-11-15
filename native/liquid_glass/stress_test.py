#!/usr/bin/env python3
"""liquid_glass.dll 稳定性压测：专门打旧实现崩溃的几条路径。

阶段 1（单线程高频，等同真实 App 的调用方式）
    多面板共享桌面复制 + 高频 set_bounds/set_params/show/hide/attach，
    外加周期性 destroy+recreate。旧实现在这里会：
      * 每面板各建一套 device+duplication，同一 output 的复制对象互踢成
        ACCESS_LOST，失效后循环不再阻塞 → 满速空转狂轰驱动；
      * 在调用线程里直接 ResizeBuffers + 建 RTV，与渲染线程 Draw/Present 并发；
      * Unmap 之后还通过失效的 pData 指针写 Pass2 常量 → 写已释放的驱动暂存内存。

阶段 2（跨线程销毁）
    模拟解释器收尾时 GC 线程调 lg_destroy。属主线程必须在泵消息，
    否则任何跨线程窗口调用都会互锁——新实现用 PostMessage 异步关窗规避。
"""
import ctypes
import ctypes.wintypes as wt
import os
import random
import sys
import threading
import time

DLL = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "build", "Release", "liquid_glass.dll")
u = ctypes.windll.user32
k = ctypes.windll.kernel32

u.CreateWindowExW.restype = wt.HWND
u.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
                              ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                              wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID]
u.DefWindowProcW.restype = ctypes.c_ssize_t
u.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
u.PeekMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT, wt.UINT]
u.DestroyWindow.argtypes = [wt.HWND]
u.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)
_keepalive = []


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("style", wt.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON), ("hCursor", wt.HANDLE),
                ("hbrBackground", wt.HBRUSH), ("lpszMenuName", wt.LPCWSTR),
                ("lpszClassName", wt.LPCWSTR), ("hIconSm", wt.HICON)]


def make_host_window(idx):
    name = f"LsletUI_StressHost_{idx}_{random.randint(100000, 999999)}"
    _keepalive.append(WNDPROC(lambda h, m, w, l: u.DefWindowProcW(h, m, w, l)))
    wc = WNDCLASSEXW()
    wc.cbSize = ctypes.sizeof(wc)
    wc.lpfnWndProc = _keepalive[-1]
    wc.hInstance = k.GetModuleHandleW(None)
    wc.lpszClassName = name
    if not u.RegisterClassW(ctypes.byref(wc)):
        raise OSError(f"RegisterClassW 失败 0x{ctypes.get_last_error():08X}")
    hwnd = u.CreateWindowExW(0, name, name, 0, 100, 100, 400, 300,
                             None, None, k.GetModuleHandleW(None), None)
    if not hwnd:
        raise OSError("CreateWindowExW 失败")
    u.ShowWindow(hwnd, 5)
    return int(hwnd)


def pump():
    msg = wt.MSG()
    n = 0
    while u.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
        u.TranslateMessage(ctypes.byref(msg))
        u.DispatchMessageW(ctypes.byref(msg))
        n += 1
    return n


class LgParams(ctypes.Structure):
    _fields_ = [("cornerRadius", ctypes.c_float), ("blurSigma", ctypes.c_float),
                ("displacementScale", ctypes.c_float),
                ("aberrationIntensity", ctypes.c_float), ("saturation", ctypes.c_float)]


def bind(dll):
    dll.lg_default_params.argtypes = [ctypes.POINTER(LgParams)]
    dll.lg_create.restype = ctypes.c_void_p
    dll.lg_create.argtypes = [ctypes.POINTER(LgParams)]
    dll.lg_attach.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    dll.lg_set_bounds.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_int]
    dll.lg_set_params.argtypes = [ctypes.c_void_p, ctypes.POINTER(LgParams)]
    dll.lg_show.argtypes = [ctypes.c_void_p, ctypes.c_int]
    dll.lg_hide.argtypes = [ctypes.c_void_p, ctypes.c_int]
    dll.lg_destroy.argtypes = [ctypes.c_void_p]
    dll.lg_shutdown_engine.restype = None


def phase1(dll, hosts, secs):
    """单线程高频：完全等同 Qt GUI 线程的调用方式"""
    rng = random.Random(1)
    p = LgParams()
    dll.lg_default_params(ctypes.byref(p))

    panels = []
    for h in hosts:
        panel = dll.lg_create(ctypes.byref(p))
        if not panel:
            print(f"[p1] lg_create 失败 0x{ctypes.get_last_error():08X}")
            return None, 0
        dll.lg_attach(panel, h)
        dll.lg_set_bounds(panel, 200, 200, 900, 600)
        dll.lg_show(panel, 0)
        panels.append(panel)
    print(f"[p1] {len(panels)} 个面板已创建（共享一套 device + duplication）")

    t0 = time.time()
    calls = cycles = 0
    last_cycle = t0
    while time.time() - t0 < secs:
        for _ in range(200):
            panel = rng.choice(panels)
            dll.lg_set_bounds(panel, rng.randint(-100, 2000), rng.randint(-100, 1500),
                              rng.randint(1, 2560), rng.randint(1, 1600))
            if rng.random() < 0.2:
                q = LgParams()
                dll.lg_default_params(ctypes.byref(q))
                q.cornerRadius = rng.uniform(0.0, 40.0)
                q.blurSigma = rng.uniform(0.5, 20.0)
                q.displacementScale = rng.uniform(0.0, 0.2)
                q.aberrationIntensity = rng.uniform(0.0, 2.0)
                dll.lg_set_params(panel, ctypes.byref(q))
            if rng.random() < 0.15:
                dll.lg_show(panel, 0) if rng.random() < 0.6 else dll.lg_hide(panel, 0)
            if rng.random() < 0.05:
                # 混入无效锚点句柄：窗口已销毁后仍被重钉
                dll.lg_attach(panel, rng.choice(hosts + [0, 0xDEADBEEF, 1]))
            calls += 1
        pump()
        cycles += 1

        # 周期性销毁/重建，制造「渲染线程正在用这个面板」与「API 要拆它」的重叠
        if time.time() - last_cycle > 1.0:
            last_cycle = time.time()
            victim = panels.pop(0)
            dll.lg_hide(victim, 0)
            dll.lg_destroy(victim)
            new = dll.lg_create(ctypes.byref(p))
            if not new:
                print(f"[p1] 重建失败 0x{ctypes.get_last_error():08X}")
                return panels, calls
            dll.lg_attach(new, hosts[cycles % len(hosts)])
            dll.lg_set_bounds(new, 300, 300, 1000, 700)
            dll.lg_show(new, 0)
            panels.append(new)
    return panels, calls


def phase2(dll, hosts):
    """跨线程销毁：属主线程持续泵消息，模拟解释器收尾时 GC 线程调 lg_destroy"""
    p = LgParams()
    dll.lg_default_params(ctypes.byref(p))
    panel = dll.lg_create(ctypes.byref(p))
    if not panel:
        return False
    dll.lg_attach(panel, hosts[0])
    dll.lg_set_bounds(panel, 400, 400, 800, 500)
    dll.lg_show(panel, 0)
    time.sleep(0.3)
    pump()

    done = {}

    def elsewhere():
        dll.lg_hide(panel, 0)
        dll.lg_destroy(panel)
        done["ok"] = True

    th = threading.Thread(target=elsewhere)
    th.start()
    t0 = time.time()
    while th.is_alive() and time.time() - t0 < 10.0:
        pump()
        time.sleep(0.005)
    th.join(timeout=1.0)
    # 让渲染线程走完两轮回收
    for _ in range(40):
        pump()
        time.sleep(0.02)
    if not done.get("ok"):
        print("[p2] 跨线程 lg_destroy 超时（互锁）")
        return False
    print(f"[p2] 跨线程销毁完成，耗时 {time.time() - t0:.2f}s")
    return True


def main():
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
    dll = ctypes.CDLL(DLL, use_last_error=True)
    bind(dll)
    if not dll.lg_is_supported():
        print("[stress] 系统不支持，跳过")
        return 0

    hosts = [make_host_window(i) for i in range(4)]
    print(f"[stress] 宿主窗口 {len(hosts)} 个: {[hex(h) for h in hosts]}")

    panels, calls = phase1(dll, hosts, secs)
    if panels is None:
        return 2
    ok2 = phase2(dll, hosts)

    for panel in panels:
        dll.lg_hide(panel, 0)
        dll.lg_destroy(panel)
    dll.lg_shutdown_engine()
    for h in hosts:
        u.DestroyWindow(h)
    pump()
    print(f"[stress] 通过: {secs:.0f}s 高频调用 {calls} 次，跨线程销毁 {'OK' if ok2 else 'FAIL'}")
    return 0 if ok2 else 3


if __name__ == "__main__":
    sys.exit(main())
