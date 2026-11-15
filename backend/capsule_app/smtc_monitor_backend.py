#!/usr/bin/env python3
"""
LsletUI - Windows SMTC 媒体监控后端（音乐 + 视频）
通过启动时编译的 C# 小程序调用 WinRT 获取系统正在播放的媒体信息
（标题、艺术家/UP主、专辑/系列、封面、播放状态、进度、时长），
封面以 base64 PNG 返回；通过 ctypes 模拟媒体键实现播放/暂停/切歌控制。

支持自动识别视频平台（Bilibili/YouTube/抖音/腾讯视频/爱奇艺/优酷/Netflix
等）并返回 media_type="video"，音乐返回 media_type="music"。

说明：不使用 PowerShell 反射 await —— Windows PowerShell 5.1 对
OpenReadAsync 的投影会返回未封装的 __ComObject，无法读取封面流。
C# 编译器（csc + Windows.winmd）能正确处理 WinRT 接口投影。
"""

import json
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, Signal, QTimer

# --- 视频平台识别表 ---
# key 用于 source (AppUserModelId) 的不区分大小写包含匹配，value 为平台中文名
VIDEO_PLATFORM_MAP = [
    # (source_keywords, process_keywords, platform_name)
    # source_keywords: AppUserModelId 中包含的关键词（小写）
    # process_keywords: 窗口/进程名中包含的关键词（小写，备用）
    ([
        "bilibili", "哔哩哔哩", "bili"
    ], ["bilibili", "哔哩哔哩"], "哔哩哔哩"),
    ([
        "youtube"
    ], ["youtube"], "YouTube"),
    ([
        "douyin", "抖音"
    ], ["douyin", "抖音"], "抖音"),
    ([
        "tencent.qqlive", "qqlive", "腾讯视频"
    ], ["qqlive", "腾讯视频"], "腾讯视频"),
    ([
        "iqiyi", "爱奇艺"
    ], ["iqiyi", "爱奇艺"], "爱奇艺"),
    ([
        "youku", "优酷"
    ], ["youku", "优酷"], "优酷"),
    ([
        "sogou", "搜狐视频"
    ], ["sogou", "搜狐视频"], "搜狐视频"),
    ([
        "pptv", "聚力"
    ], ["pptv"], "PP视频"),
    ([
        "mgtv", "芒果tv", "芒果"
    ], ["mgtv", "芒果"], "芒果TV"),
    ([
        "v.qq.com", "vqq"
    ], ["qqvideo", "qq视频"], "腾讯视频"),
    ([
        "netflix"
    ], ["netflix"], "Netflix"),
    ([
        "disney"
    ], ["disney"], "Disney+"),
    ([
        "hbo"
    ], ["hbo", "max"], "HBO"),
    ([
        "primevideo", "amazon.prime"
    ], ["prime", "amazon"], "Prime Video"),
    ([
        "xigua", "西瓜视频"
    ], ["xigua", "西瓜"], "西瓜视频"),
    ([
        "kuaishou", "快手"
    ], ["kuaishou", "快手"], "快手"),
    ([
        "xiaohongshu", "xhs", "rednote", "小红书"
    ], ["xiaohongshu", "小红书"], "小红书"),
    ([
        "ixigua"
    ], ["ixigua"], "西瓜视频"),
    ([
        "funtv", "风行"
    ], ["funtv", "风行"], "风行视频"),
    ([
        "sohu"
    ], ["sohu"], "搜狐"),
    ([
        "le.com", "letv", "乐视"
    ], ["letv", "乐视"], "乐视视频"),
    ([
        "m1905", "1905"
    ], ["1905", "电影网"], "1905电影网"),
    ([
        "acfun", "ac"
    ], ["acfun"], "AcFun"),
]


def _usable_platform_key(key):
    """平台关键词是否可用于匹配。

    只排除确实过于宽泛的短 ASCII 词（如 ac）；中文平台名（抖音/优酷/
    快手/芒果）本身只有 2~3 个字符，不能按长度一刀切掉，否则网页版
    抖音/B站会被判成音乐。
    """
    if key == "ac":
        return False
    return not (key.isascii() and len(key) < 3)


# Web 浏览器里播放视频时，source 会是 Chrome/Edge 等浏览器，
# 需要通过标题/artist/时长综合判断是视频还是音乐。

# --- 强视频特征词（命中任一即高度可疑为视频） ---
VIDEO_STRONG_TITLE_PATTERNS = [
    re.compile(r"第.{0,4}[集话期部季回話]"),    # 第1集 / 第1话 / 第一季第2集
    re.compile(r"[Ss]\d{1,2}[Ee]\d{1,3}"),      # S01E01 / s2e3
    re.compile(r"全\d+集"),
    re.compile(r"(先行篇|后篇|前篇|完结篇|特别篇|OVA|SP|番外)"),
    re.compile(r"(正片|完整版|花絮|预告|预告篇|官方预告|概念预告)"),
    re.compile(r"(trailer|teaser|preview)\s*(official)?", re.IGNORECASE),
    re.compile(r"(episode|ep\.?)\s*\d{1,3}", re.IGNORECASE),
    re.compile(r"[Ss]eason\s*\d+", re.IGNORECASE),
    re.compile(r"(official\s+video|music\s+video|\bmv\b)", re.IGNORECASE),
]

# --- 辅助视频特征词（需要配合其他条件） ---
VIDEO_WEAK_TITLE_PATTERNS = [
    re.compile(r"(电影|剧集|电视剧|纪录片|动漫|动画|番剧|综艺|综艺片)"),
    re.compile(r"(院线|票房|IMAX|杜比|原声大碟)"),
    re.compile(r"\b(1080p|720p|2160p|4k|8k|hdr|bluray|bdrip|webrip)\b", re.IGNORECASE),
]

# --- 视频平台关键词（标题/artist 里出现的平台名） ---
VIDEO_PLATFORM_KEYWORDS = [
    "哔哩哔哩", "bilibili", "b站",
    "youtube", "yt",
    "抖音", "douyin", "tiktok",
    "腾讯视频", "iqiyi", "爱奇艺", "youku", "优酷",
    "mgtv", "芒果tv",
    "netflix", "disney", "hbo", "prime video", "primevideo",
    "西瓜视频", "ixigua",
    "快手", "kuaishou",
    "小红书", "xiaohongshu", "rednote",
    "acfun",
    "vimeo", "dailymotion",
    "drm", "streaming",
]

# --- 强音乐特征词（浏览器场景下命中即强制为音乐） ---
MUSIC_STRONG_TITLE_PATTERNS = [
    re.compile(r"\b(song|track|single|album)\b", re.IGNORECASE),
    re.compile(r"\b(official\s+audio|audio|lyric\s+video|visualizer)\b", re.IGNORECASE),
    re.compile(r"(原曲|cover|翻唱|原唱|live\s+at|acoustic|remix|edit|bootleg|歌词版|音频)"),
]

# --- 艺术家特征词（如果 artist 含这些，高度可疑为视频的 UP主/频道） ---
VIDEO_ARTIST_HINTS = [
    # YouTube 频道常用格式
    re.compile(r"\|\s*\w+", ),          # "Some Video | Channel Name"
    re.compile(r"-\s*\w+\s*-\s*\w+"),  # 某些频道名格式
    # B站 UP主常见特征（但这个太宽泛，只作为辅助）
]

# --- 平台页面/窗口标题后缀（B 站网页标题形如 "视频名_哔哩哔哩_bilibili"） ---
_TITLE_PLATFORM_SUFFIX = [
    re.compile(r"[_\-\s|]*哔哩哔哩[_\-\s|]*bilibili\s*$", re.IGNORECASE),
    re.compile(r"[_\-\s|]*bilibili\s*$", re.IGNORECASE),
    re.compile(r"[_\-\s|]*小红书\s*$"),
]

# --- 客户端窗口标题（只是 App 口号，不含具体视频名，需要兜底） ---
# 抖音电脑版 SMTC 上报的就是窗口标题而不是当前视频名，直接展示会误导
GENERIC_VIDEO_TITLE_PATTERNS = [
    re.compile(r"抖音精选电脑版|抖音旗下优质视频平台|抖音[-\s]*记录美好生活"),
    re.compile(r"哔哩哔哩客户端|bilibili\s*客户端", re.IGNORECASE),
    re.compile(r"快手[-\s]*记录世界记录你"),
    re.compile(r"小红书[-\s]*你的生活指南"),
]

VIDEO_FALLBACK_TITLE = "正在播放视频"

# --- 音乐源黑名单（AppUserModelId 明确是音乐播放器 → 强制 music） ---
MUSIC_SOURCE_BLOCKLIST = [
    "spotify", "apple.music", "itunes",
    "cloudmusic", "netease",              # 网易云音乐
    "qqmusic", "qqmusic.exe",
    "qianqian",                            # 千千音乐
    "kugou", "kugoumusic",
    "kuwo",
    "foobar",
    "aimp",
    "media.monkey", "mediamonkey",
    "audacity",
    "musicbee",
]

# --- 纯视频播放器（能播视频也能播音频，source 命中默认判视频但可降级） ---
VIDEO_PLAYER_SOURCES = [
    "vlc", "mpv", "mpc", "potplayer", "mplayer", "kmplayer", "golang.vlc",
]

# --- 浏览器 source 关键词（用于识别"当前是在浏览器里播放"） ---
BROWSER_SOURCE_KEYWORDS = [
    "chrome", "msedge", "firefox", "brave", "opera", "vivaldi",
    "arc", "safari", "browser", "chromium",
]

# --- C# SMTC 查询程序源码（增强版：包含 position/duration） ---
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
             + "\"thumbnail\":null,\"source\":\"\","
             + "\"position_ms\":0,\"duration_ms\":0}";
    }

    public static void Main()
    {
        try
        {
            Console.OutputEncoding = Encoding.UTF8;
            var manager = GlobalSystemMediaTransportControlsSessionManager.RequestAsync().AsTask().Result;

            // 枚举所有 SMTC 会话：GetCurrentSession() 只返回"当前"一个，
            // 视频 App 在播放但另一个暂停的音乐 App 占着 current 时会被漏掉。
            // 选择策略：优先播放中的会话；同级别下沿用 current。
            var current = manager.GetCurrentSession();
            var session = current;
            var sessions = manager.GetSessions();
            var diag = new StringBuilder();
            for (int i = 0; i < sessions.Count; i++)
            {
                var s = sessions[i];
                string id = "";
                string st = "?";
                try
                {
                    id = s.SourceAppUserModelId == null ? "" : s.SourceAppUserModelId;
                    st = s.GetPlaybackInfo().PlaybackStatus.ToString();
                }
                catch { }
                if (diag.Length > 0) diag.Append(";");
                diag.Append(id).Append(":").Append(st);

                bool curPlaying = false;
                try
                {
                    curPlaying = session != null
                        && session.GetPlaybackInfo().PlaybackStatus
                            == GlobalSystemMediaTransportControlsSessionPlaybackStatus.Playing;
                }
                catch { }
                if (curPlaying) continue;

                bool candPlaying = false;
                try
                {
                    candPlaying = s.GetPlaybackInfo().PlaybackStatus
                        == GlobalSystemMediaTransportControlsSessionPlaybackStatus.Playing;
                }
                catch { }
                if (candPlaying) { session = s; break; }
            }
            // 会话清单走 stderr，Python 侧用于诊断（哪些 App 注册了 SMTC）
            Console.Error.WriteLine("SESSIONS:" + diag.ToString());

            if (session == null) { Console.WriteLine(Empty()); return; }

            var props = session.TryGetMediaPropertiesAsync().AsTask().Result;
            var pb = session.GetPlaybackInfo();
            bool playing = pb.PlaybackStatus == GlobalSystemMediaTransportControlsSessionPlaybackStatus.Playing;

            // 获取播放进度与时长（Timeline 属性）
            long positionMs = 0;
            long durationMs = 0;
            try
            {
                var timeline = session.GetTimelineProperties();
                if (timeline != null)
                {
                    // TimelinePosition 和 EndTime 都是 TimeSpan，单位 100ns tick
                    positionMs = timeline.Position.Ticks / 10000;
                    durationMs = timeline.EndTime.Ticks / 10000;
                    if (durationMs <= 0) durationMs = 0;
                    if (positionMs < 0) positionMs = 0;
                }
            }
            catch { /* 某些播放器不支持 Timeline，忽略 */ }

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
                + ",\"source\":\"" + J(session.SourceAppUserModelId)
                + "\",\"position_ms\":" + positionMs
                + ",\"duration_ms\":" + durationMs
                + "}";
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


_proc_cache = {"at": 0.0, "names": set()}


def _running_process_names():
    """当前运行的进程名集合（小写，不带 .exe）。2 秒缓存，避免每轮快照开销。"""
    global _proc_cache
    now = time.time()
    if now - _proc_cache["at"] < 2.0 and _proc_cache["names"]:
        return _proc_cache["names"]
    names = set()
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        TH32CS_SNAPPROCESS = 0x00000002

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * 260),
            ]

        kernel32 = ctypes.WinDLL("kernel32")
        snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        try:
            if snap != ctypes.c_void_p(-1).value:
                entry = PROCESSENTRY32W()
                entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
                if kernel32.Process32FirstW(snap, ctypes.byref(entry)):
                    while True:
                        name = entry.szExeFile.lower()
                        if name.endswith(".exe"):
                            name = name[:-4]
                        names.add(name)
                        if not kernel32.Process32NextW(snap, ctypes.byref(entry)):
                            break
        finally:
            kernel32.CloseHandle(snap)
    _proc_cache = {"at": now, "names": names}
    return names


def _process_alive_for_source(source):
    """根据 SMTC source (AUMID) 推断对应进程是否存活。
    例如 electron.app.douyin → douyin；bilibili → bilibili。
    取 AUMID 各段做包含匹配，命中任一运行中进程名即视为存活。"""
    if not source:
        return False
    names = _running_process_names()
    if not names:
        return True   # 快照失败时保守视为存活（保持宽限，不闪断）
    # AUMID 形如 electron.app.douyin / com.sxxx.bilibili / 直接进程名
    # 只用"段 == 进程名"的精确匹配：避免 douyin_tray/douyin_guard 等
    # 常驻辅助进程在主程序关闭后仍被误判为存活
    fragments = [seg for seg in re.split(r"[.\s]+", source.lower()) if len(seg) >= 4]
    for frag in fragments:
        if frag in names:
            return True
    return False


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
        self._last_raw_title = None   # 上一次的原始标题（用于"同一条内容"判定）
        self._query_exe = None
        # 空标题计时起点：用于短暂保留上一次内容，避免灵动岛闪回默认形态
        self._empty_since = None

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

    # --- C# 程序编译（缓存 + 源码变化自动重编） ---
    def _ensure_query_exe(self):
        """编译 C# SMTC 查询程序；成功返回 exe 路径，失败返回 None"""
        import hashlib

        if sys.platform != "win32":
            return None

        cache_dir = Path.home() / ".pyisland_lite"
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            exe_path = cache_dir / "smtc_query.exe"
            # 源码 hash 文件：用于检测 SMTC_CS_SOURCE 是否变化，变化则重编
            hash_path = cache_dir / "smtc_query.source_hash"
            current_hash = hashlib.sha256(SMTC_CS_SOURCE.encode("utf-8")).hexdigest()

            need_recompile = True
            if exe_path.exists() and hash_path.exists():
                try:
                    cached_hash = hash_path.read_text(encoding="utf-8").strip()
                    if cached_hash == current_hash:
                        need_recompile = False
                except Exception:
                    pass

            if not need_recompile:
                return str(exe_path)

            # 删掉旧 exe 确保干净重编
            if exe_path.exists():
                try:
                    exe_path.unlink()
                except Exception:
                    pass

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

            compile_start = time.time()
            result = subprocess.run(
                [str(csc), "/nologo", "/target:exe", f"/out:{exe_path}"]
                + ref_args + [str(cs_path)],
                capture_output=True, timeout=60,
                creationflags=self._no_window_flags(),
            )
            # 必须验证 exe 真的是本次新产出的：csc 覆盖失败（文件被并发轮询占用
            # 或杀软拦截）时旧 exe 仍在，仅凭 exists() 会误判"编译成功"，
            # 且 hash 写不进去导致每次启动都空转重编
            exe_fresh = exe_path.exists() \
                and exe_path.stat().st_mtime >= compile_start - 2
            if exe_fresh:
                # 写入 hash 文件标记已编译的源码版本
                try:
                    hash_path.write_text(current_hash, encoding="utf-8")
                except Exception:
                    pass
                print("[SMTC] C# 查询程序编译成功（含视频支持）")
                return str(exe_path)
            if exe_path.exists():
                # 旧 exe 沿用（功能可用），但不写 hash，下次启动继续重试
                print("[SMTC] 编译未生效（exe 被占用或被拦截），本次沿用旧版本，下次启动重试")
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

    # --- 视频平台识别（打分机制，多维综合判定） ---
    @staticmethod
    def _detect_media_type(info, last_type=None):
        """根据 SMTC 返回的 source / title / artist / duration 综合判断媒体类型。

        返回 (media_type, platform_name)：
          media_type: "video" 或 "music"
          platform_name: 识别到的视频平台中文名（仅 video 时有值）

        last_type: 上一次的判定结果，用于迟滞（hysteresis），
                   避免相邻两次轮询之间类型来回翻转。

        判定策略（按优先级）：
          1) AUMID 精确命中音乐黑名单 → 强制 music
          2) AUMID 精确命中视频平台 → 强制 video（返回平台名）
          3) AUMID 是纯视频播放器（VLC/MPV/PotPlayer）→ 默认 video
          4) 其他情况 → 基于标题/artist/时长打分
        """
        source = (info.get("source") or "").lower()
        title = info.get("title") or ""
        artist = info.get("artist") or ""
        album = info.get("album") or ""
        duration_ms = info.get("duration_ms") or 0

        is_browser = any(kw in source for kw in BROWSER_SOURCE_KEYWORDS)

        # --- 0) 音乐源黑名单（最高优先级） ---
        # 注意：source 为空时不触发（某些无 AUMID 的应用）
        for bl_key in MUSIC_SOURCE_BLOCKLIST:
            if bl_key in source:
                return "music", ""

        # --- 1) 视频平台精确匹配（AUMID 命中） ---
        for src_keys, _proc, platform in VIDEO_PLATFORM_MAP:
            for key in src_keys:
                if not _usable_platform_key(key):
                    continue
                if key in source:
                    return "video", platform

        # --- 2) 纯视频播放器（VLC/MPV 等，默认判视频，但让标题特征可覆盖） ---
        source_is_video_player = any(kw in source for kw in VIDEO_PLAYER_SOURCES)

        # --- 3) 打分开始 ---
        video_score = 0
        music_score = 0

        # 3a) 标题强视频特征（+4 分）
        for pat in VIDEO_STRONG_TITLE_PATTERNS:
            if pat.search(title):
                video_score += 4
                break  # 一个足够

        # 3b) 标题辅助视频特征（+2 分）
        for pat in VIDEO_WEAK_TITLE_PATTERNS:
            if pat.search(title):
                video_score += 2
                break

        # 3c) 标题/artist 含视频平台名（+3 分，浏览器外也有效）
        lower_title_artist = (title + " " + artist).lower()
        matched_platform = ""
        for src_keys, _proc, platform in VIDEO_PLATFORM_MAP:
            for key in src_keys:
                if not _usable_platform_key(key):
                    continue
                if key.lower() in lower_title_artist:
                    video_score += 3
                    matched_platform = platform
                    break
            if matched_platform:
                break

        # 3d) 标题含强音乐特征（+4 分 music）
        for pat in MUSIC_STRONG_TITLE_PATTERNS:
            if pat.search(title):
                music_score += 4
                break

        # 3e) artist 长度/内容判断（浏览器场景下 UP主/频道名通常较长 +1 分 video）
        artist_stripped = artist.strip()
        if is_browser:
            # 浏览器场景：artist 通常是视频的 UP主/频道名（长），
            # 或音乐的歌手名（也可能长，但如果还有其他特征辅助）
            if artist_stripped and len(artist_stripped) >= 4:
                # 有 artist 不直接加分，只作为辅助
                pass
            elif not artist_stripped:
                # 浏览器 + 无 artist → 视频概率略高
                video_score += 1

            # artist 含 YouTube 频道格式 "Video Title | Channel Name"
            for pat in VIDEO_ARTIST_HINTS:
                if pat.search(artist) or pat.search(title):
                    video_score += 2
                    break

        # 3f) album 字段判断：视频通常无专辑/album 为空，音乐通常有
        has_album = bool(album and len(album.strip()) > 2)
        if has_album:
            music_score += 2

        # 3f-2) 浏览器长内容加成：浏览器 + 无专辑 + 无音乐特征 + 时长久于 3 分钟
        #       典型如 YouTube 教程/访谈/游戏实况，既没有集数标记也没有专辑字段，
        #       单靠时长打分不足以越过阈值，补一个浏览器上下文加成
        if is_browser and not has_album and music_score == 0 \
                and duration_ms > 3 * 60 * 1000:
            video_score += 2

        # 3g) 时长辅助判断：
        #     < 90 秒 → 大概率短视频/歌曲
        #     90s ~ 3min → 灰色地带
        #     3 ~ 15 min → 可能是 MV/短视频/B站视频
        #     > 15 min → 可能是长视频/电影/直播/播客
        #     > 60 min → 大概率视频/电影/直播（古典音乐/长播客除外）
        if duration_ms > 0:
            duration_min = duration_ms / 60000.0
            if duration_min < 1.5:
                # 短：无法区分，不加分
                pass
            elif 1.5 <= duration_min <= 3:
                # 中短：略向视频倾斜
                video_score += 1
            elif 3 < duration_min <= 15:
                # 中长：明显视频倾向
                video_score += 2
            elif 15 < duration_min <= 60:
                # 长：强视频倾向（但播客也是这个时长）
                video_score += 3
                # 如果同时有 music 特征（song/cover/album）则抵消
                if music_score >= 3:
                    video_score -= 2
            else:
                # > 60 min：大概率视频/直播/电影（古典音乐/超长专辑例外）
                video_score += 4
                if music_score >= 3:
                    video_score -= 2

        # 3h) source_is_video_player 加分
        if source_is_video_player:
            video_score += 3

        # --- 4) 迟滞（hysteresis）：已经判定为视频时，只有音乐证据明显反超
        #        才切回音乐。duration_ms 在 seek/缓冲时会瞬时变 0，导致打分掉档，
        #        没有迟滞就会出现"视频↔音乐"每几秒翻一次的现象（一断一断）。
        if last_type == "video":
            if music_score < video_score + 4:
                return "video", matched_platform

        # --- 5) 最终判定 ---
        # 音乐源精确命中已在前面处理过，到这里的 source 要么是浏览器/未知应用
        # 要么是视频播放器
        if video_score >= music_score + 3:
            # 视频分明显高 → 判定视频
            platform = matched_platform
            return "video", platform
        elif music_score >= video_score + 2:
            # 音乐分明显高 → 判定音乐
            return "music", ""
        elif video_score >= 5 and music_score <= 1:
            # 视频分高且几乎没音乐特征
            platform = matched_platform
            return "video", platform
        elif source_is_video_player and video_score >= music_score:
            # VLC/MPV 等视频播放器 → 默认视频
            platform = matched_platform
            return "video", platform
        else:
            # 难以判断 → 默认音乐（保守，避免误伤音乐）
            # 例外：如果时长 > 30 分钟且没有明显音乐特征 → 视频
            if duration_ms > 30 * 60 * 1000 and music_score == 0 and video_score >= 2:
                platform = matched_platform
                return "video", platform
            return "music", ""

    @staticmethod
    def _polish_title(title, platform):
        """清理视频标题：去掉 B 站页面后缀；客户端口号式标题改为兜底文案"""
        t = (title or "").strip()
        if not t:
            return t
        for pat in _TITLE_PLATFORM_SUFFIX:
            t = pat.sub("", t).strip()
        if any(pat.search(t) for pat in GENERIC_VIDEO_TITLE_PATTERNS):
            return VIDEO_FALLBACK_TITLE if platform else t
        return t

    @staticmethod
    def _enrich_info(info, prev=None):
        """给原始 SMTC info 补充 media_type / platform 字段

        向后兼容：原始字段（playing/title/artist/album/thumbnail/source）
        全部保留，仅新增三个字段：
          media_type: "video" | "music"
          platform: 视频平台中文名（仅 video 时非空）
          position_ms, duration_ms: 播放进度与时长（毫秒）
        无这两个字段时补 0 避免下游 KeyError。

        prev: 上一次推送的 info，用于类型迟滞与平台名继承。
        """
        if info is None:
            return info
        # 补默认值（老 C# 程序产物可能没这俩字段）
        info.setdefault("position_ms", 0)
        info.setdefault("duration_ms", 0)
        prev = prev or {}
        media_type, platform = SMTCMonitorBackend._detect_media_type(
            info, last_type=prev.get("media_type"))
        # 本次没识别出平台名时沿用上一次的，避免第二行标签闪烁
        if media_type == "video" and not platform \
                and prev.get("media_type") == "video":
            platform = prev.get("platform") or ""
        info["media_type"] = media_type
        info["platform"] = platform
        if media_type == "video":
            # 抖音电脑版只给窗口标题；B 站网页标题带 "哔哩哔哩" 后缀，统一清理
            info["title"] = SMTCMonitorBackend._polish_title(
                info.get("title"), platform)
            if not info["title"] and platform:
                info["title"] = VIDEO_FALLBACK_TITLE
        return info

    # --- 轮询 ---
    def set_web_view(self, web_view):
        self.web_view = web_view

    def _start_scan_thread(self):
        if self._scanning or self._query_exe is None:
            return
        thread = threading.Thread(target=self._fetch_music_info, daemon=True)
        thread.start()

    def _fetch_music_info(self):
        """在后台线程中运行 C# 查询程序获取媒体信息（音乐或视频）"""
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

            # stderr 的会话清单诊断：变化时打印，便于排查视频 App 是否注册 SMTC
            try:
                err = result.stderr.decode("utf-8", errors="replace")
                for line in err.splitlines():
                    line = line.strip()
                    if line.startswith("SESSIONS:"):
                        sessions_str = line[len("SESSIONS:"):]
                        if sessions_str != getattr(self, "_last_sessions", None):
                            self._last_sessions = sessions_str
                            print(f"[SMTC] 会话清单: {sessions_str or '(无)'}")
                        break
            except Exception:
                pass

            # 取最后一行 JSON
            raw_info = None
            for line in reversed(output.splitlines()):
                line = line.strip()
                if line.startswith("{"):
                    try:
                        raw_info = json.loads(line)
                        break
                    except json.JSONDecodeError:
                        continue
            if raw_info is None:
                return

            prev = self._last_info or {}

            # 时长粘滞：GetTimelineProperties 在 seek/缓冲/切集时会瞬时返回 0，
            # 直接采用会让时长打分掉档，导致类型在视频/音乐之间来回翻
            if not raw_info.get("duration_ms") and prev.get("duration_ms"):
                raw_info["duration_ms"] = prev["duration_ms"]

            # "同一条内容"判定必须用原始标题：抖音等客户端的口号式标题会被
            # 兜底成"正在播放视频"再存进 _last_info，拿替换后的标题比较会
            # 永远判为不同内容，类型迟滞失效
            raw_title_now = (raw_info.get("title") or "").strip()
            same_content = bool(self._last_raw_title) \
                and raw_title_now == self._last_raw_title
            if raw_title_now:
                self._last_raw_title = raw_title_now

            # 空标题宽限：浏览器 SMTC 会话重建时可能瞬时拿不到标题，
            # 短暂保留上一次内容，避免灵动岛闪回默认形态（宽窄来回跳）
            # 桌面视频客户端（抖音/B站客户端等 Electron 应用）播放中 SMTC 会话
            # 会整体消失又重建，宽限需要更长：进程还活着 → 最多保留 15 秒；
            # 进程已退出 → 立即清空。
            now = time.time()
            if raw_info.get("title"):
                self._empty_since = None
            elif prev.get("title"):
                if self._empty_since is None:
                    self._empty_since = now
                prev_source = (prev.get("source") or "").lower()
                prev_is_browser = any(
                    kw in prev_source for kw in BROWSER_SOURCE_KEYWORDS)
                if not prev_is_browser and prev.get("platform"):
                    # 桌面视频客户端：进程存活时宽限 15 秒，退出则立即清空
                    # （进程已死不用 hold：raw_info 保持空，走正常推送清空岛上内容）
                    # 短视频平台切换频繁，宽限过长会让旧内容残留、显得"延迟高"
                    if _process_alive_for_source(prev_source):
                        if now - self._empty_since < 15.0:
                            hold = dict(prev)
                            hold["playing"] = False
                            raw_info = hold
                            same_content = True   # 沿用上一条的平台/类型
                        else:
                            self._empty_since = None
                    else:
                        self._empty_since = None
                elif now - self._empty_since < 12.0:
                    hold = dict(prev)
                    hold["playing"] = False
                    raw_info = hold
                    same_content = True   # 沿用上一条的平台/类型
                else:
                    self._empty_since = None
            else:
                self._empty_since = None

            # 补充 media_type / platform 字段
            # 迟滞只在"同一条内容"内生效（标题未变）。换片/切歌时必须重新判定
            info = self._enrich_info(raw_info, prev=prev if same_content else None)

            # 推送判定：忽略 position_ms（每轮都在变，否则会被误判为"有变化"）；
            # 但进度推进 ≥1 秒时仍推送，用于刷新进度条
            sig_keys = ("title", "artist", "album", "source",
                        "playing", "media_type", "platform",
                        "duration_ms", "thumbnail")
            new_sig = tuple(info.get(k) for k in sig_keys)
            old_sig = tuple(prev.get(k) for k in sig_keys)
            pos_delta = abs((info.get("position_ms") or 0)
                            - (prev.get("position_ms") or 0))
            if new_sig != old_sig or pos_delta >= 1000:
                old = prev
                title_changed = info.get("title") != old.get("title")
                state_changed = info.get("playing") != old.get("playing")
                type_changed = info.get("media_type") != old.get("media_type")
                self._last_info = info
                self.music_info_updated.emit(info)
                if title_changed or state_changed or type_changed:
                    media_label = "视频" if info.get("media_type") == "video" else "音乐"
                    platform_part = f" [{info.get('platform')}]" if info.get("platform") else ""
                    print(
                        f"[SMTC-{media_label}{platform_part}] {info.get('title')} "
                        f"- {info.get('artist')} "
                        f"({'播放中' if info.get('playing') else '已暂停/无播放'})"
                    )

            # 自适应轮询频率：视频平台播放时 1 秒（短视频切换频繁，需要跟手），
            # 音乐播放时 3 秒，无播放时也 3 秒——空闲降到 8 秒会让"开始播放"
            # 最多晚 8 秒才被发现，正是用户感知到的"延迟高"
            is_playing = info and info.get("playing")
            if is_playing and info.get("media_type") == "video":
                new_interval = 1000
            elif is_playing:
                new_interval = 3000
            else:
                new_interval = 3000
            if self._poll_timer.interval() != new_interval:
                self._adjust_interval.emit(new_interval)

        except subprocess.TimeoutExpired:
            print("[SMTC] 查询超时")
        except Exception as e:
            print(f"[SMTC] 获取媒体信息失败: {e}")
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
