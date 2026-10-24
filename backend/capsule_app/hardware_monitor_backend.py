#!/usr/bin/env python3
"""
LsletUI - 轻量级灵动岛应用
硬件监控后端模块：CPU / 内存 / GPU / 网速 / 温度（psutil + pynvml）
"""

import time
import warnings

from PySide6.QtCore import QObject, Signal, QTimer

POLL_MS = 2000  # 采样间隔

# 高负载进入阈值：任一指标达到即记一次高样本
HIGH_CPU = 88.0
HIGH_MEM = 92.0
HIGH_GPU = 90.0
HIGH_GPU_TEMP = 85.0
# 迟滞：退出需连续 EXIT_STREAK 次低于（进入阈值 - EXIT_DELTA），避免负载抖动导致闪烁
EXIT_DELTA = 6.0
ENTER_STREAK = 2  # 连续 2 次高样本（约 4s）才弹出，滤掉瞬时尖峰
EXIT_STREAK = 4   # 连续 4 次回落（约 8s）才收回


class HardwareMonitorBackend(QObject):
    """轮询 CPU/内存/GPU/网速/温度，高负载时发 alert_changed

    psutil 的 cpu_percent(interval=None)/net_io_counters 均为非阻塞瞬时
    调用，NVML 亦然，因此直接在主线程 QTimer 里采样（单次 <5ms），
    无需额外工作线程。
    """

    stats_updated = Signal(dict)        # 每次采样：cpu/mem/gpu/gpu_temp/net_up/net_down
    alert_changed = Signal(bool, dict)  # 高负载开始(True)/结束(False)，附带当前采样

    def __init__(self):
        super().__init__()
        self._last_net = None  # (monotonic, bytes_sent, bytes_recv)
        self._net_up = 0.0
        self._net_down = 0.0
        self._high_streak = 0
        self._low_streak = 0
        self._alerting = False
        self._nvml = None
        self._nvml_handle = None

        self._init_nvml()
        try:
            import psutil
            # 首次调用仅建立基线（返回 0），下一轮才出真实值
            psutil.cpu_percent(interval=None)
        except Exception:
            pass

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(POLL_MS)
        # 尽快产出第一份含网速的采样（网速需要两次采样差分）
        QTimer.singleShot(POLL_MS // 4, self._poll)

    def _init_nvml(self):
        """初始化 NVML（无 NVIDIA 显卡/驱动异常时静默降级为无 GPU 数据）"""
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                import pynvml
            pynvml.nvmlInit()
            self._nvml = pynvml
            self._nvml_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        except Exception as e:
            print(f"[Hardware] NVML 不可用（无 GPU 数据）: {e}")

    def _sample(self):
        """采集一次系统指标"""
        import psutil

        stats = {
            "cpu": psutil.cpu_percent(interval=None),
            "mem": psutil.virtual_memory().percent,
            "gpu": None,
            "gpu_temp": None,
            "net_up": 0.0,
            "net_down": 0.0,
        }

        # 网速 = 相邻两次计数的差分
        now = time.monotonic()
        c = psutil.net_io_counters()
        if self._last_net is not None:
            t0, s0, r0 = self._last_net
            dt = now - t0
            if dt > 0:
                self._net_up = max(0.0, (c.bytes_sent - s0) / dt)
                self._net_down = max(0.0, (c.bytes_recv - r0) / dt)
        self._last_net = (now, c.bytes_sent, c.bytes_recv)
        stats["net_up"] = self._net_up
        stats["net_down"] = self._net_down

        # GPU 利用率 / 显存占用 / 温度（温度是本机唯一可得的硬件温度：
        # psutil.sensors_* 与 WMI MSAcpi_ThermalZoneTemperature 在 Windows
        # 均不可用，见项目记录）
        if self._nvml is not None and self._nvml_handle is not None:
            try:
                u = self._nvml.nvmlDeviceGetUtilizationRates(self._nvml_handle)
                m = self._nvml.nvmlDeviceGetMemoryInfo(self._nvml_handle)
                stats["gpu"] = float(u.gpu)
                stats["gpu_mem"] = (m.used / m.total * 100.0) if m.total else None
                stats["gpu_temp"] = float(self._nvml.nvmlDeviceGetTemperature(
                    self._nvml_handle, self._nvml.NVML_TEMPERATURE_GPU))
            except Exception:
                pass  # 驱动繁忙/设备暂时不可达：本轮缺 GPU 数据
        return stats

    @staticmethod
    def _is_high(stats):
        if stats.get("cpu") is not None and stats["cpu"] >= HIGH_CPU:
            return True
        if stats.get("mem") is not None and stats["mem"] >= HIGH_MEM:
            return True
        gpu = stats.get("gpu")
        temp = stats.get("gpu_temp")
        if gpu is not None and gpu >= HIGH_GPU:
            return True
        if temp is not None and temp >= HIGH_GPU_TEMP:
            return True
        return False

    def _poll(self):
        try:
            stats = self._sample()
        except Exception as e:
            print(f"[Hardware] 采样失败: {e}")
            return

        self.stats_updated.emit(stats)

        if self._is_high(stats):
            self._high_streak += 1
            self._low_streak = 0
            if not self._alerting and self._high_streak >= ENTER_STREAK:
                self._alerting = True
                self.alert_changed.emit(True, stats)
        else:
            self._high_streak = 0
            if self._alerting:
                self._low_streak += 1
                if self._low_streak >= EXIT_STREAK:
                    self._alerting = False
                    self._low_streak = 0
                    self.alert_changed.emit(False, stats)

    def stop(self):
        """停止轮询并释放 NVML"""
        try:
            if self._timer.isActive():
                self._timer.stop()
        except Exception:
            pass
        if self._nvml is not None:
            try:
                self._nvml.nvmlShutdown()
            except Exception:
                pass
            self._nvml = None
            self._nvml_handle = None
