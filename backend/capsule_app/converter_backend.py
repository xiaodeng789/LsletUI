#!/usr/bin/env python3
"""
LsletUI - 格式转换器后端
图片（Pillow）/ 音频（ffmpeg）/ 压缩包（zipfile+tarfile）/ 文档（Office COM→PDF）。

设计要点：
- 能力检测在初始化时完成（Pillow 可导入、ffmpeg 可寻址、Office COM 注册表可查），
  前端按 caps 决定目标格式下拉是否灰置；
- convert() 在 daemon 线程执行，结果经 on_done 回调（worker 线程），由调用方
  QTimer.singleShot 投递回 GUI 线程再推给前端；
- 输出文件先落源文件所在目录，目录不可写（PermissionError）时回退
  ~/.pyisland_lite/converted/；重名自动追加序号；
- Office 转换串行执行（同一批任务共用一个 worker 线程），避免并发 COM 混乱。
"""

import shutil
import subprocess
import sys
import tempfile
import threading
import zipfile
import tarfile
from pathlib import Path

# Pillow 可用性（导入失败则图片转换不可用）
try:
    from PIL import Image
    _HAS_PIL = True
except Exception:
    _HAS_PIL = False


# --- 格式矩阵 ---
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff", ".tif"}
IMAGE_TARGETS = ["png", "jpg", "webp", "bmp", "ico", "tiff", "gif"]

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac", ".wma"}
AUDIO_TARGETS = ["mp3", "wav", "m4a", "flac", "ogg", "aac"]

# zip 与 tar 系互转（stdlib 能写/能读的格式）
ARCHIVE_TARGETS = ["zip", "tar.gz", "tar.bz2", "tar.xz"]

DOC_APPS = {
    # 源后缀 -> (COM ProgID, 转换函数名)
    ".doc": "word", ".docx": "word", ".rtf": "word",
    ".xls": "excel", ".xlsx": "excel",
    ".ppt": "ppt", ".pptx": "ppt",
}


def _norm_ext(path):
    return Path(path).suffix.lower()


class FormatConverter:
    """格式转换器：能力检测 + 异步转换"""

    def __init__(self):
        self._ffmpeg = self._find_ffmpeg()
        self._office = self._detect_office()

    # --- 能力检测 ---
    @staticmethod
    def _find_ffmpeg():
        """PATH → exe 同级 → _internal（Nuitka standalone）→ ~/.pyisland_lite"""
        found = shutil.which("ffmpeg")
        if found:
            return found
        try:
            base = Path(sys.executable).parent
            for cand in (base / "ffmpeg.exe", base / "_internal" / "ffmpeg.exe",
                         Path.home() / ".pyisland_lite" / "ffmpeg.exe"):
                if cand.is_file():
                    return str(cand)
        except Exception:
            pass
        return None

    @staticmethod
    def _detect_office():
        """查注册表判断 Word/Excel/PowerPoint COM 是否注册（HKLM 或 HKCU）"""
        import winreg
        apps = {}
        for app in ("word", "excel", "ppt"):
            prog_id = {"word": "Word.Application",
                       "excel": "Excel.Application",
                       "ppt": "PowerPoint.Application"}[app]
            ok = False
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    winreg.OpenKey(hive, r"Software\Classes\%s" % prog_id)
                    ok = True
                    break
                except OSError:
                    continue
            apps[app] = ok
        return apps

    def caps(self):
        """能力表（推给前端决定下拉可用性）"""
        return {
            "image": _HAS_PIL,
            "audio": self._ffmpeg is not None,
            "archive": True,
            "word": self._office.get("word", False),
            "excel": self._office.get("excel", False),
            "ppt": self._office.get("ppt", False),
        }

    def targets_for(self, path):
        """某个源文件可转换的目标格式列表（源格式自身除外）"""
        ext = _norm_ext(path)
        if ext in IMAGE_EXTS and _HAS_PIL:
            return [t for t in IMAGE_TARGETS
                    if f".{t}" != ext and not (t == "jpg" and ext == ".jpeg")]
        if ext in AUDIO_EXTS and self._ffmpeg:
            return [t for t in AUDIO_TARGETS if f".{t}" != ext]
        if ext == ".zip" or ext == ".tar" or ext in (".gz", ".bz2", ".xz"):
            # 同格式排除：zip→zip / tar→tar / tar.gz→tar.gz
            if ext == ".zip":
                return [t for t in ARCHIVE_TARGETS if t != "zip"]
            if ext == ".tar":
                return [t for t in ARCHIVE_TARGETS if t != "tar"]
            return [t for t in ARCHIVE_TARGETS if t != f"tar{ext}"]
        if ext in DOC_APPS and self._office.get(DOC_APPS[ext], False):
            return ["pdf"]
        return []

    # --- 异步转换入口 ---
    def convert_batch(self, items, on_result, on_all_done=None):
        """批量转换（单 worker 线程串行执行，Office COM 并发不安全）

        items: [{"id": 前端条目id, "path": 源路径, "target": 目标格式}, ...]
        on_result(result): 每项完成后回调（worker 线程），result =
            {"id":..., "ok": bool, "outPath": str|None, "error": str|None}
        """
        def worker():
            for item in items:
                result = {"id": item.get("id"), "ok": False,
                          "outPath": None, "error": None}
                try:
                    result["outPath"] = self._convert_one(
                        item["path"], item["target"])
                    result["ok"] = True
                except Exception as e:
                    result["error"] = f"{type(e).__name__}: {e}"
                try:
                    on_result(result)
                except Exception:
                    pass
            if on_all_done:
                try:
                    on_all_done()
                except Exception:
                    pass
        threading.Thread(target=worker, daemon=True,
                         name="convert-worker").start()

    # --- 输出路径 ---
    @staticmethod
    def _unique_dst(src, target):
        """输出路径：源目录优先，不可写回退 ~/.pyisland_lite/converted；重名加序号"""
        stem = Path(src).stem
        name = f"{stem}.{target}"
        base_dir = Path(src).parent
        fallback = Path.home() / ".pyisland_lite" / "converted"
        try:
            probe = base_dir / f"~lsletui_write_probe_{stem}"
            probe.write_bytes(b"")
            probe.unlink()
            out_dir = base_dir
        except (PermissionError, OSError):
            fallback.mkdir(parents=True, exist_ok=True)
            out_dir = fallback
        dst = out_dir / name
        if not dst.exists():
            return dst
        i = 1
        while True:
            cand = out_dir / f"{stem}_{i}.{target}"
            if not cand.exists():
                return cand
            i += 1

    # --- 单个转换分派 ---
    def _convert_one(self, src, target):
        src = str(src)
        if not Path(src).is_file():
            raise FileNotFoundError(src)
        dst = self._unique_dst(src, target)
        ext = _norm_ext(src)
        if ext in IMAGE_EXTS:
            self._convert_image(src, dst, target)
        elif ext in AUDIO_EXTS:
            self._convert_audio(src, dst)
        elif ext == ".zip" or ext == ".tar" or ext in (".gz", ".bz2", ".xz"):
            self._convert_archive(src, dst, target)
        elif ext in DOC_APPS:
            self._convert_doc(src, dst, ext)
        else:
            raise ValueError(f"不支持的源格式: {ext}")
        return str(dst)

    # --- 图片（Pillow） ---
    @staticmethod
    def _convert_image(src, dst, target):
        if not _HAS_PIL:
            raise RuntimeError("Pillow 未安装，无法转换图片")
        fmt_map = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG",
                   "webp": "WEBP", "bmp": "BMP", "ico": "ICO",
                   "tiff": "TIFF", "gif": "GIF"}
        fmt = fmt_map[target]
        img = Image.open(src)
        try:
            if fmt == "JPEG":
                # 带 alpha 通道的图平铺白底再转 RGB，避免 JPEG 报错/黑底
                if img.mode in ("RGBA", "LA", "PA"):
                    img = img.convert("RGBA")
                    bg = Image.new("RGB", img.size, (255, 255, 255))
                    bg.paste(img, mask=img.split()[-1])
                    img = bg
                elif img.mode != "RGB":
                    img = img.convert("RGB")
                img.save(dst, fmt, quality=90)
            elif fmt == "ICO":
                img.save(dst, fmt,
                         sizes=[(16, 16), (32, 32), (48, 48), (64, 64),
                                (128, 128), (256, 256)])
            elif fmt in ("PNG", "WEBP", "BMP", "TIFF", "GIF"):
                if img.mode == "P" and fmt in ("BMP", "TIFF"):
                    img = img.convert("RGBA")
                # 动图取首帧即可（GIF 转静态格式场景极少）
                img.save(dst, fmt)
        finally:
            try:
                img.close()
            except Exception:
                pass

    # --- 音频（ffmpeg） ---
    def _convert_audio(self, src, dst):
        if not self._ffmpeg:
            raise RuntimeError("未找到 ffmpeg，无法转换音频")
        cmd = [self._ffmpeg, "-y", "-nostdin", "-hide_banner",
               "-loglevel", "error", "-i", src, "-vn", str(dst)]
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              creationflags=0x08000000)  # CREATE_NO_WINDOW
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg 失败: {(proc.stderr or '').strip()[:300]}")

    # --- 压缩包（zipfile + tarfile，经临时目录整包搬运） ---
    @staticmethod
    def _convert_archive(src, dst, target):
        with tempfile.TemporaryDirectory(prefix="lsletui_conv_") as tmp:
            tmp = Path(tmp)
            # 解开源
            if src.lower().endswith(".zip"):
                with zipfile.ZipFile(src) as zf:
                    zf.extractall(tmp)
            else:
                # filter="data" 拒绝绝对路径与 .. 穿越（Python 3.12+ 内置）
                with tarfile.open(src) as tf:
                    tf.extractall(tmp, filter="data")
            # 打包目标
            if target == "zip":
                with zipfile.ZipFile(dst, "w",
                                     zipfile.ZIP_DEFLATED) as zf:
                    for p in sorted(tmp.rglob("*")):
                        if p.is_file():
                            zf.write(p, p.relative_to(tmp).as_posix())
            else:
                mode = {"tar.gz": "w:gz", "tar.bz2": "w:bz2",
                        "tar.xz": "w:xz"}[target]
                with tarfile.open(dst, mode) as tf:
                    for p in sorted(tmp.rglob("*")):
                        tf.add(p, arcname=p.relative_to(tmp).as_posix())

    # --- 文档（Office COM → PDF） ---
    @staticmethod
    def _safe_quit(app):
        """Word/Excel 退出时偶发 RPC 错误（进程已自行终止），无害，吞掉即可"""
        try:
            app.Quit()
        except Exception:
            pass

    def _convert_doc(self, src, dst, ext):
        app = DOC_APPS[ext]
        if not self._office.get(app, False):
            raise RuntimeError("本机未安装对应的 Office 组件")
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        try:
            src_abs = str(Path(src).resolve())
            dst_abs = str(Path(dst).resolve())
            if app == "word":
                word = win32com.client.DispatchEx("Word.Application")
                try:
                    word.Visible = False
                    word.DisplayAlerts = 0
                    # ConfirmConversions=False 避免 RTF 等触发转换对话框
                    doc = word.Documents.Open(src_abs, False, True)
                    try:
                        doc.SaveAs(dst_abs, FileFormat=17)  # wdFormatPDF
                    finally:
                        doc.Close(False)
                finally:
                    self._safe_quit(word)
            elif app == "excel":
                excel = win32com.client.DispatchEx("Excel.Application")
                try:
                    excel.Visible = False
                    excel.DisplayAlerts = False
                    wb = excel.Workbooks.Open(src_abs, ReadOnly=True)
                    try:
                        wb.ExportAsFixedFormat(0, dst_abs)  # xlTypePDF
                    finally:
                        wb.Close(False)
                finally:
                    self._safe_quit(excel)
            else:  # ppt
                ppt = win32com.client.DispatchEx("PowerPoint.Application")
                try:
                    pres = ppt.Presentations.Open(src_abs, ReadOnly=True,
                                                  WithWindow=False)
                    try:
                        pres.SaveAs(dst_abs, 32)  # ppSaveAsPDF
                    finally:
                        pres.Close()
                finally:
                    self._safe_quit(ppt)
        finally:
            # 不调用 CoUninitialize()：会销毁进程级 COM 状态，导致其他
            # COM 线程（通话/蓝牙/日历）的 ctypes.windll 缓存失效 → 0xC0000005
            pass
