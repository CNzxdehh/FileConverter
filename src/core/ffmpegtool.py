# -*- coding: utf-8 -*-
"""ffmpeg 定位 / 检测 / 带进度执行。"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from . import winui

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

# ffmpeg 常见落点（含绿色便携约定：程序目录 ffmpeg\\bin\\ffmpeg.exe）
_CANDIDATES = [
    "",  # PATH
    r"%LOCALAPPDATA%\Microsoft\WinGet\Links",   # winget install Gyan.FFmpeg 的落地目录
    r"%LOCALAPPDATA%\Programs\ffmpeg\bin",
    r"%USERPROFILE%\scoop\shims",               # scoop install ffmpeg
    r"C:\Program Files\ffmpeg\bin",
    r"C:\ffmpeg\bin",
    r"%~dp0ffmpeg\bin",                         # 绿色便携：程序目录\ffmpeg\bin\ffmpeg.exe
    r"%~dp0ffmpeg",                             # 绿色便携：程序目录\ffmpeg\ffmpeg.exe
]


def _expand(p: str, base_dir: Path) -> Path | None:
    p = p.replace("%~dp0", str(base_dir) + os.sep)
    try:
        expanded = os.path.expandvars(p)
    except Exception:
        expanded = p
    return Path(expanded) if expanded else None


def base_dir() -> Path:
    """exe / 源码根目录（用于找便携版 ffmpeg）。"""
    import sys

    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def find_ffmpeg(explicit: str | None = None) -> Path | None:
    """返回 ffmpeg.exe 路径，找不到返回 None。"""
    if explicit:
        p = Path(explicit)
        if p.is_file():
            return p
    base = base_dir()
    for cand in _CANDIDATES:
        if not cand:
            hit = shutil.which("ffmpeg")
            if hit:
                return Path(hit)
            continue
        d = _expand(cand, base)
        if d:
            f = d / "ffmpeg.exe"
            if f.is_file():
                return f
    # 源码运行时也允许 <项目根>/ffmpeg/ffmpeg.exe
    for maybe in (base / "ffmpeg" / "ffmpeg.exe", base / "ffmpeg.exe", base.parent / "ffmpeg" / "ffmpeg.exe"):
        if maybe.is_file():
            return maybe
    return None


def find_ffprobe(ffmpeg: Path | None) -> Path | None:
    if ffmpeg:
        sibling = ffmpeg.with_name("ffprobe.exe")
        if sibling.is_file():
            return sibling
    return shutil.which("ffprobe") and Path(shutil.which("ffprobe"))  # type: ignore[arg-type]


def version(ffmpeg: Path) -> str:
    try:
        out = subprocess.run(
            [str(ffmpeg), "-version"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", creationflags=CREATE_NO_WINDOW, timeout=15,
        ).stdout
        m = re.search(r"ffmpeg version (\S+)", out)
        return m.group(1) if m else "unknown"
    except Exception:
        return "unknown"


def ensure_ffmpeg(cfg: dict) -> Path:
    """音视频转换前调用；缺失时给出下载指引。"""
    ff = find_ffmpeg(cfg.get("ffmpeg_path"))
    if ff:
        return ff
    if winui.silent():
        raise RuntimeError("未找到 ffmpeg（静默模式，不弹下载指引）")
    guide = (
        "没有找到 ffmpeg，音视频转换需要它。\\n\\n"
        "三种办法任选其一：\\n"
        "1) 下载 Windows 静态版（gyan.dev essentials）：\\n"
        "   https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip\\n"
        "   解压后把 ffmpeg.exe 放到本程序目录的 ffmpeg\\ 文件夹里，或放进 PATH；\\n"
        "2) 用 winget 安装： winget install Gyan.FFmpeg\\n"
        "3) 已有 ffmpeg 但没在 PATH 里：右键菜单里点【检查运行环境】查看搜索路径。\\n\\n"
        "放进 PATH 或放到程序目录 ffmpeg\\ 后无需重启，重新右键即可。\\n\\n"
        "是否现在打开下载页面？"
    )
    from ctypes import windll

    ret = windll.user32.MessageBoxW(
        None, guide, "缺少 ffmpeg", 0x24 | 0x40000  # MB_ICONQUESTION | MB_YESNO | TOPMOST
    )
    if ret == 6:
        winui.open_url("https://www.gyan.dev/ffmpeg/builds/")
    raise SystemExit(2)


_HMS = re.compile(r"(\d+):(\d+):([\d.]+)")


def duration(ffprobe: Path | None, src: Path) -> float | None:
    """获取媒体时长（秒），失败返回 None。"""
    try:
        if ffprobe:
            out = subprocess.run(
                [str(ffprobe), "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(src)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                creationflags=CREATE_NO_WINDOW, timeout=20,
            ).stdout.strip()
            return float(out) if out else None
    except Exception:
        pass
    return None


def _fmt(sec: float) -> str:
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def run(args: list[str], total: float | None, label: str = "") -> tuple[bool, str]:
    """执行一条 ffmpeg 命令，控制台显示百分比进度。

    args 不含 ffmpeg 路径；由本函数前置 -hide_banner/-nostdin/-progress pipe:1。
    返回 (是否成功, 错误信息)。
    """
    ff = Path(args[0])
    full = [str(ff), "-hide_banner", "-nostdin", "-loglevel", "error",
            "-progress", "pipe:1", "-nostats", "-y", *args[1:]]
    try:
        proc = subprocess.Popen(
            full, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding="utf-8", errors="replace", bufsize=1, creationflags=CREATE_NO_WINDOW,
        )
    except Exception as e:
        return False, f"无法启动 ffmpeg：{e}"

    err_lines: list[str] = []
    last = ""

    def drain_err() -> None:
        # stderr 与 stdout 可能同时阻塞，放到线程里读，避免死锁
        import threading

        def _loop():
            nonlocal err_lines
            try:
                for line in proc.stderr:  # type: ignore[union-attr]
                    err_lines.append(line.rstrip())
                    if len(err_lines) > 40:
                        err_lines.pop(0)
            except Exception:
                pass

        threading.Thread(target=_loop, daemon=True).start()

    drain_err()

    t0 = time.time()
    try:
        for line in proc.stdout:  # type: ignore[union-attr]
            line = line.strip()
            if line.startswith("out_time_us="):
                us = line.split("=", 1)[1].strip()
                try:
                    t = int(us) / 1_000_000
                except ValueError:
                    continue
                if total and total > 0:
                    pct = min(100.0, t / total * 100)
                    bar_len = 24
                    filled = int(bar_len * pct / 100)
                    bar = "█" * filled + "·" * (bar_len - filled)
                    last = (f"{label} [{bar}] {pct:5.1f}%  "
                            f"{_fmt(t)}/{_fmt(total)}  speed~{t / max(time.time() - t0, 0.1):.1f}x")
                else:
                    last = f"{label} 已处理 {_fmt(t)}  用时 {time.time() - t0:.0f}s"
                winui.progress(last)
            elif line == "progress=end":
                break
    except Exception:
        pass

    try:
        proc.wait(timeout=None)
    except Exception:
        proc.kill()

    winui.end_progress()
    if proc.returncode == 0:
        return True, ""
    tail = " | ".join(err_lines[-6:]) or f"ffmpeg 退出码 {proc.returncode}"
    return False, tail[:600]
