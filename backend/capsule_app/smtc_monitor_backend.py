#!/usr/bin/env python3
"""
LsletUI - Windows SMTC 音乐监控后端
通过启动时编译的 C# 小程序调用 WinRT 获取系统正在播放的音乐信息
（歌名、歌手、专辑、封面、播放状态），封面以 base64 PNG 返回；
通过 ctypes 模拟媒体键实现播放/暂停/切歌控制。

说明：不使用 PowerShell 反射 await —— Windows PowerShell 5.1 对
OpenReadAsync 的投影会返回未封装的 __ComObject，无法读取封面流。
C# 编译器（csc + Windows.winmd）能正确处理 WinRT 接口投影。
"""

import json
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal, QTimer

# --- C# SMTC 查询程序源码 ---
SMTC_CS_SOURCE = r"""
using System;
using System.Text;
using Windows.Media.Control;
using Windows.Storage.Streams;

public static class SmtcQuery
{
    static string J(string s)
    {
        if (s == null) s = "";
        var sb = new StringBuilder(s.Length + 8);
        foreach (char c in s)
        {
            switch (c)
            {
                case '"': sb.Append("\\\""); break;
                case '\\': sb.Append("\\\\"); break;
                case '\n': sb.Append("\\n"); break;
                case '\r': sb.Append("\\r"); break;
                case '\t': sb.Append("\\t"); break;
                default:
                    if (c < 0x20) sb.Append("\\u").Append(((int)c).ToString("x4"));
                    else sb.Append(c);
                    break;
            }
        }
        return sb.ToString();
    }

    static string Empty()
    {
        return "{\"playing\":false,\"title\":\"\",\"artist\":\"\",\"album\":\"\","
             + "\"thumbnail\":null,\"source\":\"\"}";
    }

    public static void Main()
    {
        try
        {
            Console.OutputEncoding = Encoding.UTF8;
            var manager = GlobalSystemMediaTransportControlsSessionManager.RequestAsync().AsTask().Result;
            var session = manager.GetCurrentSession();
            if (session == null) { Console.WriteLine(Empty()); return; }

            var props = session.TryGetMediaPropertiesAsync().AsTask().Result;
            var pb = session.GetPlaybackInfo();
            bool playing = pb.PlaybackStatus == GlobalSystemMediaTransportControlsSessionPlaybackStatus.Playing;

            string thumb = "null";
            if (props.Thumbnail != null)
            {
                try
                {
                    var stream = props.Thumbnail.OpenReadAsync().AsTask().Result;
                    uint size = (uint)stream.Size;
                    if (size > 0 && size < 8 * 1024 * 1024)
                    {
                        var reader = new DataReader(stream);
                        reader.LoadAsync(size).AsTask().Wait();
                        byte[] bytes = new byte[size];
                        reader.ReadBytes(bytes);
                        thumb = "\"" + Convert.ToBase64String(bytes) + "\"";
                    }
                }
                catch { thumb = "null"; }
            }

            string json = "{\"playing\":" + (playing ? "true" : "false")
                + ",\"title\":\"" + J(props.Title)
                + "\",\"artist\":\"" + J(props.Artist)
                + "\",\"album\":\"" + J(props.AlbumTitle)
                + "\",\"thumbnail\":" + thumb
                + ",\"source\":\"" + J(session.SourceAppUserModelId) + "\"}";
            Console.WriteLine(json);
        }
        catch (Exception)
        {
            Console.WriteLine(Empty());
        }
    }
}
"""

# 媒体键虚拟键码
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3


def _send_media_key(vk_code):
    """通过 ctypes 模拟媒体键"""
    if sys.platform != "win32":
        return
    import ctypes
    KEYEVENTF_EXTENDEDKEY = 0x0001
    KEYEVENTF_KEYUP = 0x0002
    _user32 = ctypes.WinDLL("user32")
    _user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY, 0)
    _user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)


class SMTCMonitorBackend(QObject):
    """Windows SMTC 音乐监控后端（C#/WinRT 桥接）"""

    # 音乐信息更新信号
    music_info_updated = Signal(dict)
    # 轮询间隔调整信号（跨线程安全：工作线程 → GUI 线程）
    _adjust_interval = Signal(int)

    def __init__(self, web_view=None):
        super().__init__()
        self.web_view = web_view
        self._scanning = False
        self._last_info = None
        self._query_exe = None

        # 编译 C# 查询程序（一次性，缓存到用户目录）
        self._query_exe = self._ensure_query_exe()
        if self._query_exe is None:
            print("[SMTC] C# 查询程序不可用，音乐监控将无法工作")

        # 定时器：每 3 秒轮询一次（自适应：无音乐时降频，减少子进程启动开销）
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._start_scan_thread)
        self._adjust_interval.connect(self._poll_timer.setInterval)
        self._poll_timer.start(3000)

        # 首次延迟 1 秒执行
        QTimer.singleShot(1000, self._start_scan_thread)

    # --- C# 程序编译（仅一次，结果缓存为 exe） ---
    def _ensure_query_exe(self):
        """编译 C# SMTC 查询程序；成功返回 exe 路径，失败返回 None"""
        if sys.platform != "win32":
            return None

        cache_dir = Path.home() / ".pyisland_lite"
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            exe_path = cache_dir / "smtc_query.exe"
            if exe_path.exists():
                return str(exe_path)

            csc = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe")
            if not csc.exists():
                csc = Path(r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe")
            if not csc.exists():
                print("[SMTC] 未找到 csc.exe（Win10/11 需安装 .NET Framework 4.8）")
                return None

            # 查找 Windows.winmd（取版本号最高的 UnionMetadata）
            winmd = self._find_newest_file(
                r"C:\Program Files (x86)\Windows Kits\10\UnionMetadata",
                "Windows.winmd")
            if winmd is None:
                winmd = self._find_newest_file(
                    r"C:\Program Files\Windows Kits\10\UnionMetadata",
                    "Windows.winmd")
            if winmd is None:
                print("[SMTC] 未找到 Windows.winmd（需安装 Windows SDK）")
                return None

            srwr = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\System.Runtime.WindowsRuntime.dll")
            if not srwr.exists():
                srwr = Path(r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\System.Runtime.WindowsRuntime.dll")
            if not srwr.exists():
                print("[SMTC] 未找到 System.Runtime.WindowsRuntime.dll")
                return None

            # 查找最高版本 .NET Framework Facades
            facades_dir = self._find_newest_facades()
            if facades_dir is None:
                print("[SMTC] 未找到 .NET Framework Facades")
                return None

            # 写入 C# 源码（重试一次，规避被杀进程残留句柄导致的 Permission denied）
            cs_path = cache_dir / "smtc_query.cs"
            try:
                cs_path.write_text(SMTC_CS_SOURCE, encoding="utf-8")
            except PermissionError:
                import time
                time.sleep(0.5)
                try:
                    cs_path.unlink(missing_ok=True)
                    cs_path.write_text(SMTC_CS_SOURCE, encoding="utf-8")
                except Exception:
                    cs_path = Path(tempfile.gettempdir()) / "smtc_query_tmp.cs"
                    cs_path.write_text(SMTC_CS_SOURCE, encoding="utf-8")

            ref_args = [f"/r:{winmd}", f"/r:{srwr}"]
            for dll in facades_dir.glob("*.dll"):
                ref_args.append(f"/r:{dll}")

            result = subprocess.run(
                [str(csc), "/nologo", "/target:exe", f"/out:{exe_path}"]
                + ref_args + [str(cs_path)],
                capture_output=True, timeout=60,
                creationflags=self._no_window_flags(),
            )
            if exe_path.exists():
                print("[SMTC] C# 查询程序编译成功")
                return str(exe_path)
            print("[SMTC] 编译失败:",
                  result.stdout.decode("utf-8", "replace")[:300],
                  result.stderr.decode("utf-8", "replace")[:300])
            return None
        except Exception as e:
            print(f"[SMTC] 准备查询程序失败: {e}")
            return None

    @staticmethod
    def _find_newest_file(base_dir, filename):
        """在 base_dir/<版本号>/ 下找最高版本目录中的指定文件。
        注意必须排除 Facade 子目录——那里的 Windows.winmd 只有类型转发，
        缺少 Windows.Media.Control 等真实类型。"""
        base = Path(base_dir)
        if not base.exists():
            return None
        candidates = []
        for p in base.glob(f"*/{filename}"):
            # 版本目录形如 10.0.26100.0
            parts = p.parent.name.split(".")
            if parts and parts[0].isdigit():
                candidates.append(p)
        if not candidates:
            return None
        candidates.sort(key=lambda p: tuple(int(x) for x in p.parent.name.split(".")
                                           if x.isdigit()), reverse=True)
        return candidates[0]

    @staticmethod
    def _find_newest_facades():
        """查找最高版本 .NET Framework 的 Facades 目录"""
        bases = [
            Path(r"C:\Program Files (x86)\Reference Assemblies\Microsoft\Framework\.NETFramework"),
            Path(r"C:\Program Files\Reference Assemblies\Microsoft\Framework\.NETFramework"),
        ]
        for base in bases:
            if not base.exists():
                continue
            candidates = list(base.glob("v4*/Facades"))
            if not candidates:
                continue
            candidates.sort(key=lambda p: p.parent.name, reverse=True)
            return candidates[0]
        return None

    @staticmethod
    def _no_window_flags():
        """CREATE_NO_WINDOW，避免子进程闪现控制台窗口"""
        CREATE_NO_WINDOW = 0x08000000
        return CREATE_NO_WINDOW if sys.platform == "win32" else 0

    # --- 轮询 ---
    def set_web_view(self, web_view):
        self.web_view = web_view

    def _start_scan_thread(self):
        if self._scanning or self._query_exe is None:
            return
        thread = threading.Thread(target=self._fetch_music_info, daemon=True)
        thread.start()

    def _fetch_music_info(self):
        """在后台线程中运行 C# 查询程序获取音乐信息"""
        self._scanning = True
        try:
            result = subprocess.run(
                [self._query_exe],
                capture_output=True, timeout=10,
                creationflags=self._no_window_flags(),
            )
            output = result.stdout.decode("utf-8", errors="replace").strip()
            if not output:
                return

            # 取最后一行 JSON
            info = None
            for line in reversed(output.splitlines()):
                line = line.strip()
                if line.startswith("{"):
                    try:
                        info = json.loads(line)
                        break
                    except json.JSONDecodeError:
                        continue
            if info is None:
                return

            # 仅在信息变化时推送（封面 base64 也参与比较，内容相同则不重复推送）
            if info != self._last_info:
                old = self._last_info or {}
                title_changed = info.get("title") != old.get("title")
                state_changed = info.get("playing") != old.get("playing")
                self._last_info = info
                self.music_info_updated.emit(info)
                if title_changed or state_changed:
                    print(f"[SMTC] {info.get('title')} - {info.get('artist')} "
                          f"({'播放中' if info.get('playing') else '已暂停/无播放'})")

            # 自适应轮询频率：无音乐播放时降频到 8 秒，有音乐时保持 3 秒
            is_playing = info and info.get("playing")
            new_interval = 3000 if is_playing else 8000
            if self._poll_timer.interval() != new_interval:
                self._adjust_interval.emit(new_interval)

        except subprocess.TimeoutExpired:
            print("[SMTC] 查询超时")
        except Exception as e:
            print(f"[SMTC] 获取音乐信息失败: {e}")
        finally:
            self._scanning = False

    def get_last_info(self):
        """获取最近一次的音乐信息"""
        return self._last_info

    # --- 媒体控制 ---
    def play_pause(self):
        _send_media_key(VK_MEDIA_PLAY_PAUSE)
        print("[SMTC] 播放/暂停")
        # 媒体键发出后快速刷新两次：第一次抓即时状态，第二次兜底
        QTimer.singleShot(350, self._start_scan_thread)
        QTimer.singleShot(1000, self._start_scan_thread)

    def next_track(self):
        _send_media_key(VK_MEDIA_NEXT_TRACK)
        print("[SMTC] 下一曲")
        # 切歌后部分播放器需要时间加载，稍晚再刷一次
        QTimer.singleShot(500, self._start_scan_thread)
        QTimer.singleShot(1300, self._start_scan_thread)

    def prev_track(self):
        _send_media_key(VK_MEDIA_PREV_TRACK)
        print("[SMTC] 上一曲")
        QTimer.singleShot(500, self._start_scan_thread)
        QTimer.singleShot(1300, self._start_scan_thread)

    def handle_command(self, command):
        """处理来自前端/胶囊的媒体控制命令"""
        if command == "playpause":
            self.play_pause()
        elif command == "next":
            self.next_track()
        elif command == "prev":
            self.prev_track()

    # --- 前端推送 ---
    def _push_to_frontend(self, info):
        if self.web_view and self.web_view.page():
            try:
                payload = json.dumps(info, ensure_ascii=True)
                js_code = f"window.handleSMTCMusicUpdate && window.handleSMTCMusicUpdate({payload});"
                self.web_view.page().runJavaScript(js_code)
            except Exception as e:
                print(f"[SMTC] 推送到前端失败: {e}")

    def connect_frontend_callback(self):
        self.music_info_updated.connect(self._push_to_frontend)

    def stop(self):
        if self._poll_timer:
            self._poll_timer.stop()
