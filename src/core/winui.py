# -*- coding: utf-8 -*-
"""Windows 原生 UI：可选分配的控制台、消息框、文件夹选择框。

程序以 windows 子系统打包（默认不弹窗口），只有真正开始转换的那个进程
才会 AllocConsole 弹出"小黑窗口"，避免多文件同时选中时一堆黑窗口闪现。
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import ctypes
from ctypes import wintypes

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

MB_OK = 0x0
MB_ICONINFO = 0x40
MB_ICONERROR = 0x10
MB_ICONWARN = 0x30
MB_TOPMOST = 0x40000

_SW_HIDE, _SW_SHOW = 0, 5

_console_ready = False
_buffer: list[str] = []


# --------------------------------------------------------------------------
# 控制台
# --------------------------------------------------------------------------
def ensure_console(title: str = "文件格式转换") -> bool:
    """分配并显示一个控制台窗口，同时把 stdout/stderr 重定向过去。"""
    global _console_ready
    if _console_ready:
        return True
    if os.environ.get("FILECONV_NO_CONSOLE") == "1":   # 自动化测试用：完全不开窗
        return False
    try:
        if not _kernel32.GetConsoleWindow():
            _kernel32.AllocConsole()
        _kernel32.SetConsoleTitleW(title)
        # 让 \r 进度条等即时输出
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)  # type: ignore[union-attr]
            sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)  # type: ignore[union-attr]
        except Exception:
            pass
        conout = open("CONOUT$", "w", encoding="utf-8", errors="replace")
        conerr = open("CONOUT$", "w", encoding="utf-8", errors="replace")
        sys.stdout = conout
        sys.stderr = conerr
        try:  # 扩大缓冲区，避免长进度回绕丢字
            _user32.SendMessageTimeoutW(
                _kernel32.GetConsoleWindow(), 0x0005, 0, 0, 0x0002, 1000, None
            )
        except Exception:
            pass
        _console_ready = True
        sys.stdout.write("")
        for line in _buffer:
            print(line)
        _buffer.clear()
        return True
    except Exception:
        return False


def has_console() -> bool:
    return _console_ready


def print_safe(msg: str = "") -> None:
    """控制台未就绪时先缓存，就绪后自动补印。"""
    if _console_ready:
        try:
            print(msg)
        except Exception:
            pass
    else:
        _buffer.append(msg)


def progress(msg: str) -> None:
    """单行刷新的进度显示。"""
    if not _console_ready:
        return
    try:
        width = 78
        sys.stdout.write("\r" + msg.ljust(width)[:width])
        sys.stdout.flush()
    except Exception:
        pass


def end_progress() -> None:
    if _console_ready:
        try:
            sys.stdout.write("\n")
            sys.stdout.flush()
        except Exception:
            pass


def set_topmost(enable: bool = True) -> None:
    hwnd = _kernel32.GetConsoleWindow()
    if hwnd:
        _user32.SetWindowPos(
            hwnd, -1 if enable else -2, 0, 0, 0, 0, 0x0001 | 0x0002
        )


# --------------------------------------------------------------------------
# 消息框
# --------------------------------------------------------------------------
def silent() -> bool:
    """静默模式（自检 / 自动化场景）：不弹窗，只往控制台或调用方输出。"""
    return os.environ.get("FILECONV_SILENT") == "1"


def msgbox(text: str, title: str = "文件格式转换", icon: int = MB_ICONINFO) -> None:
    if silent():
        print_safe(f"\n--- 提示框（静默模式）：{title} ---\n{text}\n")
        return
    try:
        _user32.MessageBoxW(None, text, title, MB_OK | icon | MB_TOPMOST)
    except Exception:
        print_safe(f"[{title}] {text}")


def error_box(text: str, title: str = "转换失败") -> None:
    msgbox(text, title, MB_ICONERROR)


def info_box(text: str, title: str = "转换完成") -> None:
    msgbox(text, title, MB_ICONINFO)


# --------------------------------------------------------------------------
# 文件夹选择（借 PowerShell + WinForms，避免打包 tkinter 的几十 MB 体积）
# --------------------------------------------------------------------------
def pick_folder(description: str = "选择输出文件夹", initial: str | Path | None = None) -> Path | None:
    tmp = Path(tempfile.gettempdir()) / f"pickfolder_{os.getpid()}.txt"
    if tmp.exists():
        try:
            tmp.unlink()
        except Exception:
            pass
    init = str(initial or "")
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "$d = New-Object System.Windows.Forms.FolderBrowserDialog;"
        "$d.Description = $env:FC_DESC;"
        "$d.ShowNewFolderButton = $true;"
        "if ($env:FC_INIT -ne '') { $d.SelectedPath = $env:FC_INIT };"
        "if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {"
        "  [System.IO.File]::WriteAllText($env:FC_OUT, $d.SelectedPath,"
        "   (New-Object System.Text.UTF8Encoding($false))) }"
    )
    env = dict(os.environ)
    env.update({"FC_DESC": description, "FC_INIT": init, "FC_OUT": str(tmp)})
    try:
        subprocess.run(
            [
                "powershell", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass",
                "-Command", ps,
            ],
            env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
            timeout=600,
        )
    except Exception as e:
        msgbox(f"打开文件夹选择框失败：{e}\n可直接用资源管理器手工指定：", "提示", MB_ICONWARN)
        return None
    if tmp.exists():
        try:
            val = tmp.read_text(encoding="utf-8").strip()
        finally:
            try:
                tmp.unlink()
            except Exception:
                pass
        if val:
            return Path(val)
    return None


def open_url(url: str) -> None:
    try:
        ctypes.windll.shell32.ShellExecuteW(None, "open", url, None, None, 1)
    except Exception:
        pass


# -------------------------------------------------------------------------- #
# 原生选择框（TaskDialogIndirect + 命令链接按钮）
#
# 用途：右键菜单点【转换文件格式】后，弹一个系统原生对话框让用户点选转换方案。
# 相比注册表级联子菜单，这条路 100% 可靠（不依赖 shell 的级联渲染）。
# -------------------------------------------------------------------------- #
class _TASKDIALOG_BUTTON(ctypes.Structure):
    _fields_ = [("nButtonID", ctypes.c_int), ("pszButtonText", ctypes.c_wchar_p)]


class _TASKDIALOGCONFIG(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("hwndParent", ctypes.c_void_p),
        ("hInstance", ctypes.c_void_p),
        ("dwFlags", ctypes.c_uint),
        ("dwCommonButtons", ctypes.c_uint),
        ("pszWindowTitle", ctypes.c_wchar_p),
        ("hMainIcon", ctypes.c_void_p),
        ("pszMainInstruction", ctypes.c_wchar_p),
        ("pszContent", ctypes.c_wchar_p),
        ("cButtons", ctypes.c_uint),
        ("pButtons", ctypes.POINTER(_TASKDIALOG_BUTTON)),
        ("nDefaultButton", ctypes.c_int),
        ("cRadioButtons", ctypes.c_uint),
        ("pRadioButtons", ctypes.c_void_p),
        ("nDefaultRadioButton", ctypes.c_int),
        ("pszVerificationText", ctypes.c_wchar_p),
        ("pszExpandedInformation", ctypes.c_wchar_p),
        ("pszExpandedControlText", ctypes.c_wchar_p),
        ("pszCollapsedControlText", ctypes.c_wchar_p),
        ("hFooterIcon", ctypes.c_void_p),
        ("pszFooter", ctypes.c_wchar_p),
        ("pfCallback", ctypes.c_void_p),
        ("lpCallbackData", ctypes.c_void_p),
        ("cxWidth", ctypes.c_uint),
    ]


