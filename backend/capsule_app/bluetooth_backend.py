#!/usr/bin/env python3
"""
LsletUI - 轻量级灵动岛应用
蓝牙后端模块
"""

import threading
import json
import re
import subprocess
import time
from PySide6.QtCore import QObject, Signal, QTimer


class BluetoothBackend(QObject):
    """蓝牙后端，使用PowerShell获取Windows系统已连接的蓝牙设备列表，并推送给前端"""

    # 设备列表更新信号，主线程中处理
    devices_updated = Signal(list)
    # 蓝牙开关状态信号：True=开启, False=关闭
    bt_status_changed = Signal(bool)

    SCAN_INTERVAL_S = 60  # 扫描间隔（秒）

    def __init__(self, web_view=None):
        super().__init__()
        self.web_view = web_view
        self.connected_devices = []
        self.scanning = False
        self.bt_enabled = None  # None=未知, True=开启, False=关闭
        self._countdown_remaining = self.SCAN_INTERVAL_S

        # 状态轮询定时器：每15秒检测一次蓝牙开关状态（ctypes 直查服务状态，开销极低）
        self._status_timer = QTimer()
        self._status_timer.timeout.connect(self._check_status_tick)
        self._status_timer.start(15000)

        # 倒计时+扫描定时器：仅在蓝牙开启时运行
        self._scan_timer = QTimer()
        self._scan_timer.timeout.connect(self._on_scan_tick)

        self.devices_updated.connect(self._push_to_frontend)

        # 首次检测，延迟1秒执行
        QTimer.singleShot(1000, self._check_status_tick)

    def set_web_view(self, web_view):
        """设置web_view，用于向前端推送数据"""
        self.web_view = web_view

    def _check_status_tick(self):
        """定期检测蓝牙开关状态，控制扫描定时器的启停"""
        bt_on = self._check_bluetooth_enabled()
        if self.bt_enabled != bt_on:
            self.bt_enabled = bt_on
            self.bt_status_changed.emit(bt_on)
            if bt_on:
                # 蓝牙刚开启：重置倒计时，启动扫描定时器
                self._countdown_remaining = self.SCAN_INTERVAL_S
                self._scan_timer.start(1000)
                self._start_scan_thread()
            else:
                # 蓝牙关闭：停止扫描和倒计时
                self._scan_timer.stop()
                self._update_devices([])
        self._push_status()

    def _on_scan_tick(self):
        """每秒触发：倒计时归零时发起扫描"""
        self._countdown_remaining -= 1
        if self._countdown_remaining <= 0:
            self._countdown_remaining = self.SCAN_INTERVAL_S
            self._start_scan_thread()
        self._push_countdown()

    def _start_scan_thread(self):
        """在独立线程中启动蓝牙扫描，避免阻塞Qt主线程"""
        if self.scanning:
            return
        thread = threading.Thread(target=self._scan_connected_devices, daemon=True)
        thread.start()

    def _scan_connected_devices(self):
        """使用PowerShell扫描已连接的蓝牙设备"""
        self.scanning = True
        try:
            devices_list = self._get_connected_bluetooth_devices()
            self._update_devices(devices_list)
        except subprocess.TimeoutExpired:
            print("[Bluetooth] 扫描蓝牙设备超时")
            self._update_devices([])
        except Exception as e:
            print(f"[Bluetooth] 扫描蓝牙设备失败: {e}")
            self._update_devices([])
        finally:
            self.scanning = False

    def _check_bluetooth_enabled(self):
        """检测系统蓝牙无线电是否开启（通过 ctypes 查询 bthserv 服务状态，避免 PowerShell 启动开销）"""
        try:
            import ctypes
            from ctypes import wintypes

            SERVICE_QUERY_STATUS = 0x0004
            SERVICE_RUNNING = 4
            SERVICE_STOPPED = 1

            advapi32 = ctypes.WinDLL("advapi32")
            advapi32.OpenSCManagerW.restype = wintypes.HANDLE
            advapi32.OpenSCManagerW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
            advapi32.OpenServiceW.restype = wintypes.HANDLE
            advapi32.OpenServiceW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, wintypes.DWORD]
            advapi32.CloseServiceHandle.restype = wintypes.BOOL
            advapi32.CloseServiceHandle.argtypes = [wintypes.HANDLE]

            class SERVICE_STATUS(ctypes.Structure):
                _fields_ = [
                    ("dwServiceType", wintypes.DWORD),
                    ("dwCurrentState", wintypes.DWORD),
                    ("dwControlsAccepted", wintypes.DWORD),
                    ("dwWin32ExitCode", wintypes.DWORD),
                    ("dwServiceSpecificExitCode", wintypes.DWORD),
                    ("dwCheckPoint", wintypes.DWORD),
                    ("dwWaitHint", wintypes.DWORD),
                ]

            QueryServiceStatus = advapi32.QueryServiceStatus
            QueryServiceStatus.restype = wintypes.BOOL
            QueryServiceStatus.argtypes = [wintypes.HANDLE, ctypes.POINTER(SERVICE_STATUS)]

            scm = advapi32.OpenSCManagerW(None, None, SERVICE_QUERY_STATUS)
            if not scm:
                return True
            try:
                svc = advapi32.OpenServiceW(scm, "bthserv", SERVICE_QUERY_STATUS)
                if not svc:
                    return True
                try:
                    status = SERVICE_STATUS()
                    if QueryServiceStatus(svc, ctypes.byref(status)):
                        return status.dwCurrentState == SERVICE_RUNNING
                finally:
                    advapi32.CloseServiceHandle(svc)
            finally:
                advapi32.CloseServiceHandle(scm)
            return True
        except Exception as e:
            print(f"[Bluetooth] 检测蓝牙状态失败: {e}")
            return True
    
    def _get_connected_bluetooth_devices(self):
        """调用PowerShell获取已连接的蓝牙设备，延迟导入所有 heavy 模块"""
        try:
            # 延迟导入，避免启动时加载
            import subprocess
            import json
            import re
            import base64

            # PowerShell命令：获取已连接的蓝牙设备。
            # 关键：不直接输出中文 JSON —— 不同系统的控制台代码页
            # （GBK / UTF-8）不一致会导致设备名乱码。这里把 UTF-8 编码的
            # JSON 再做一次 Base64，Python 侧按 UTF-8 解码，与系统代码页完全无关。
            powershell_command = """
            $json = Get-PnpDevice -Class Bluetooth | Where-Object { $_.Status -eq 'OK' } | Select-Object FriendlyName, DeviceId | ConvertTo-Json -Compress
            if ($null -eq $json) { '' } else { [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json)) }
            """
            # 在Windows上隐藏PowerShell窗口，避免弹出黑框
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

            # 以字节方式捕获输出，自行做 Base64 -> UTF-8 解码
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", powershell_command],
                capture_output=True,
                startupinfo=startupinfo,
                timeout=15
            )

            if result.returncode != 0:
                err = result.stderr.decode("utf-8", errors="replace")
                print(f"[Bluetooth] PowerShell命令执行失败: {err}")
                return []

            b64_text = result.stdout.decode("ascii", errors="ignore").strip()
            if not b64_text:
                print("[Bluetooth] PowerShell返回空输出")
                return []
            try:
                json_text = base64.b64decode(b64_text).decode("utf-8")
            except Exception as e:
                print(f"[Bluetooth] Base64/UTF-8 解码失败: {e}")
                return []
            try:
                devices = json.loads(json_text)
            except json.JSONDecodeError as e:
                print(f"[Bluetooth] JSON解析失败: {e}, 输出内容: {json_text[:200]}...")
                return []
            if not isinstance(devices, list):
                devices = [devices] if devices else []

            # 过滤掉系统蓝牙适配器与协议服务节点，只保留真实外设。
            # 注意：不要加入"无线"这类过宽的中文关键词——真实设备（如
            # "Microsoft 真无线蓝牙鼠标"）名称里也包含它，会被误杀。
            filter_patterns = [
                r'Microsoft.*枚举器',
                r'蓝牙枚举器',
                r'LE.*枚举器',
                r'Bluetooth.*Adapter',
                r'Microsoft.*Bluetooth',
                r'英特尔.*无线蓝牙',
                r'Intel Wireless Bluetooth',
                r'Avrcp',
                r'传输',
                r'Device',
                r'通用属性',
                r'通用访问',
                r'区域网',
                r'推送',
                r'访问'
            ]
            combined_filter = re.compile('|'.join(filter_patterns), re.IGNORECASE)
            
            devices_list = []
            for idx, device in enumerate(devices):
                name = device.get('FriendlyName', '未知设备')
                # 过滤系统设备
                if combined_filter.search(name):
                    continue
                # 跳过空名称
                if not name or name == '未知设备':
                    continue
                device_id = device.get('DeviceId', f'unknown_{idx}')
                # 模拟电量，后续可以扩展获取真实电量
                battery_value = 85 + (len(devices_list) * 7) % 15  # 85%-100%之间
                devices_list.append({
                    "id": device_id,
                    "name": name,
                    "battery": f"{battery_value}%",
                    "batteryValue": battery_value
                })
            
            return devices_list
            
        except Exception as e:
            print(f"[Bluetooth] 解析PowerShell输出失败: {e}")
            return []
    
    def _update_devices(self, devices):
        """更新设备列表并发出信号"""
        self.connected_devices = devices
        if devices:
            print(f"[Bluetooth] 更新蓝牙设备列表: {len(devices)} 个设备已连接")
            for d in devices:
                print(f"  - {d['name']} ({d['id']})")
        else:
            print("[Bluetooth] 未发现已连接的蓝牙设备")
        self.devices_updated.emit(devices)

    def _push_to_frontend(self, devices):
        """将设备列表和蓝牙状态推送给前端"""
        if self.web_view and self.web_view.page():
            try:
                payload = json.dumps({
                    "devices": devices,
                    "btEnabled": self.bt_enabled,
                }, ensure_ascii=True)
                js_code = f"window.handleBluetoothDevicesUpdate && window.handleBluetoothDevicesUpdate({payload});"
                self.web_view.page().runJavaScript(js_code)
            except Exception as e:
                print(f"[Bluetooth] 推送数据到前端失败: {e}")

    def _push_countdown(self):
        """将倒计时秒数推送给前端"""
        if self.web_view and self.web_view.page():
            try:
                js_code = f"window.handleBluetoothCountdown && window.handleBluetoothCountdown({self._countdown_remaining});"
                self.web_view.page().runJavaScript(js_code)
            except Exception:
                pass

    def _push_status(self):
        """将蓝牙开关状态推送给前端"""
        if self.web_view and self.web_view.page():
            try:
                js_val = "true" if self.bt_enabled else "false" if self.bt_enabled is False else "null"
                js_code = f"window.handleBluetoothStatus && window.handleBluetoothStatus({js_val});"
                self.web_view.page().runJavaScript(js_code)
            except Exception:
                pass

    def stop(self):
        """停止后台任务"""
        self._status_timer.stop()
        self._scan_timer.stop()


# ---------------------------------------------------------------------------
# 蓝牙音频设备（耳机）连接 / 断开实时监控
# ---------------------------------------------------------------------------

# 经典蓝牙音频服务 UUID（出现在音频子节点的 DeviceID 中）：
# HSP(1108) / A2DP Source(110A) / A2DP Sink(110B) /
# AVRCP Target(110E) / AVRCP Controller(110F) / HFP-HF(111E)
_BT_AUDIO_UUIDS = (
    "00001108", "0000110A", "0000110B",
    "0000110E", "0000110F", "0000111E",
)
# 外设主节点（区别于 USB 蓝牙适配器 / 枚举器 / 各协议服务子节点）
_BT_MAIN_NODE_RE = re.compile(r"(?:BLUETOOTH|BTHLE)DEVICE_([0-9A-F]{12})$")
_BT_MAC_RE = re.compile(r"[0-9A-F]{12}")
_BT_WQL = (
    "SELECT * FROM __InstanceOperationEvent WITHIN 1 WHERE "
    "TargetInstance ISA 'Win32_PnPEntity' AND "
    "TargetInstance.PNPClass = 'Bluetooth'"
)
_BT_RECONCILE_SQL = (
    "SELECT Name, DeviceID FROM Win32_PnPEntity "
    "WHERE PNPClass = 'Bluetooth'"
)


class BluetoothConnectionMonitor(QObject):
    """耳机连接 / 断开实时监控。

    原理：WMI 的 Win32_PnPEntity 只包含“当前在位”的设备节点——已配对但
    断开的蓝牙耳机（如本机 K90）会整体从 WMI 中消失，Get-PnpDevice 里的
    幽灵节点（Code 45）不会出现。因此连接 = 实例创建、断开 = 实例删除，
    订阅 __InstanceOperationEvent 即可拿到秒级实时事件，无需高频轮询。

    判定“耳机”而非鼠标/键盘：除了外设主节点（DeviceID 以
    BLUETOOTHDEVICE_<MAC> 结尾）能被查到之外，还必须存在 A2DP/AVRCP/HFP
    等音频协议子节点。事件只负责唤醒，实际状态以重新对账（reconcile）
    为准，并加了 4 秒轮询兜底，防止漏事件。
    """

    # 连接状态变化：{"name": 设备名, "connected": True/False}
    connection_changed = Signal(dict)

    DEBOUNCE_S = 1.5      # 事件后等主节点/子节点到齐再对账
    POLL_S = 4.0          # 兜底轮询间隔
    RECONCILE_RETRY = 3   # WMI 瞬时失败重试次数

    def __init__(self, start=True):
        super().__init__()
        self._stop_event = threading.Event()
        self._thread = None
        # 当前在位的耳机 mac -> 友好名称（首次对账为基线，不发通知）
        self._connected = {}
        self._baseline_done = False
        if start:
            self.start()

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="bt-connection-monitor", daemon=False)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        # 等待 COM 线程安全退出，避免跨套间 GC 导致 0xC0000005
        if self._thread is not None and self._thread.is_alive():
            self._stop_event.set()  # 确保线程知道要退出
            self._thread.join(timeout=5.0)
            if self._thread.is_alive():
                print("[Bluetooth] 警告: 连接监控 COM 线程未能在 5 秒内退出")

    # --- 后台线程 ---
    def _run(self):
        try:
            import pythoncom
            import win32com.client
        except ImportError as e:
            print(f"[Bluetooth] 连接监控启动失败（缺少 pywin32）: {e}")
            return

        pythoncom.CoInitialize()
        watcher = None
        try:
            wmi = win32com.client.GetObject("winmgmts:")
            self._reconcile(wmi, initial=True)

            while not self._stop_event.is_set():
                # 事件订阅断了就重建（WMI 服务偶发重启）
                if watcher is None:
                    try:
                        watcher = wmi.ExecNotificationQuery(_BT_WQL)
                    except Exception as e:
                        print(f"[Bluetooth] 事件订阅失败，{self.POLL_S}s 后重试: {e}")
                        self._stop_event.wait(self.POLL_S)
                        continue

                dirty_deadline = None
                last_poll = time.monotonic()
                while not self._stop_event.is_set():
                    try:
                        ev = watcher.NextEvent(1000)  # 阻塞 1s
                        pnp_class = getattr(ev.TargetInstance, "PNPClass", "")
                        if pnp_class == "Bluetooth":
                            dirty_deadline = time.monotonic() + self.DEBOUNCE_S
                    except pythoncom.com_error:
                        pass  # 超时无事件，正常
                    except Exception as e:
                        print(f"[Bluetooth] 事件监听异常，重新订阅: {e}")
                        watcher = None
                        break

                    now = time.monotonic()
                    if dirty_deadline is not None and now >= dirty_deadline:
                        self._reconcile(wmi)
                        dirty_deadline = None
                        last_poll = now
                        # 绝不能 gc.collect()：GC 回收进程级垃圾链，会把其他
                        # COM 线程的对象跨套间 Release → 0xC0000005
                    elif now - last_poll >= self.POLL_S:
                        self._reconcile(wmi)
                        last_poll = now
                        # 绝不能 gc.collect()：GC 回收进程级垃圾链，会把其他
                        # COM 线程的对象跨套间 Release → 0xC0000005。
                        # 本线程查询对象都是局部变量，引用计数确定性释放。
        finally:
            # 不调用 CoUninitialize()：它会销毁进程级 COM 状态，
            # 导致其他线程的 ctypes.windll 缓存失效 → _ctypes.pyd 0xC0000005
            pass

    # --- 状态对账 ---
    def _query_rows(self, wmi):
        """返回当前在位蓝牙节点 [(name, device_id_upper), ...]"""
        last_err = None
        for _ in range(self.RECONCILE_RETRY):
            try:
                rows = []
                for d in wmi.ExecQuery(_BT_RECONCILE_SQL):
                    name = d.Name or ""
                    device_id = (d.DeviceID or "").upper()
                    rows.append((name, device_id))
                return rows
            except Exception as e:
                last_err = e
                time.sleep(0.3)
        print(f"[Bluetooth] 对账查询失败: {last_err}")
        return None

    def _reconcile(self, wmi, initial=False):
        """查询在位设备并与上次状态比对，发出连接/断开通知"""
        rows = self._query_rows(wmi)
        if rows is None:
            return

        main_nodes = {}   # mac -> 友好名称
        audio_macs = set()
        for name, device_id in rows:
            tail = device_id.split("\\")[-1]
            m = _BT_MAIN_NODE_RE.search(tail)
            if m:
                main_nodes.setdefault(m.group(1), name)
            if any(uuid in device_id for uuid in _BT_AUDIO_UUIDS):
                audio_macs.update(_BT_MAC_RE.findall(device_id))

        now_connected = {mac: name for mac, name in main_nodes.items()
                         if mac in audio_macs}

        if initial or not self._baseline_done:
            # 启动基线：程序启动前就连着的耳机不弹通知
            self._connected = dict(now_connected)
            self._baseline_done = True
            if now_connected:
                print(f"[Bluetooth] 基线：已连接耳机 "
                      f"{list(now_connected.values())}")
            return

        prev = self._connected
        for mac, name in now_connected.items():
            if mac not in prev:
                print(f"[Bluetooth] 耳机已连接: {name} ({mac})")
                self.connection_changed.emit({"name": name, "connected": True})
        for mac, name in prev.items():
            if mac not in now_connected:
                print(f"[Bluetooth] 耳机已断开: {name} ({mac})")
                self.connection_changed.emit({"name": name, "connected": False})
        self._connected = dict(now_connected)