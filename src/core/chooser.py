# -*- coding: utf-8 -*-
"""原生选择框（纯 Win32 自绘窗口，不依赖 comctl32 / TaskDialog）。

右键菜单点【转换文件格式】后弹这个窗口，列出可用转换方案供点选。
之所以不用 TaskDialogIndirect：本机不管怎么配都返回 E_INVALIDARG，
自己画一个 ListBox 窗口最稳。
"""
import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WS_OVERLAPPED = 0x00000000
WS_CAPTION = 0x00C00000
WS_SYSMENU = 0x00080000
WS_VISIBLE = 0x10000000
WS_CHILD = 0x40000000
WS_BORDER = 0x00800000
WS_VSCROLL = 0x00200000
WS_TABSTOP = 0x00010000
LBS_NOTIFY = 0x0001
LBS_NOINTEGRALHEIGHT = 0x0100
BS_PUSHBUTTON = 0x00000000
BS_DEFPUSHBUTTON = 0x00000001

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_COMMAND = 0x0111
WM_SETFONT = 0x0030
WM_GETMINMAXINFO = 0x0024

LB_ADDSTRING = 0x0180
LB_SETCURSEL = 0x0186
LB_GETCURSEL = 0x0188

DEFAULT_GUI_FONT = 17
IDOK, IDCANCEL = 1, 2

LRESULT = ctypes.c_longlong
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, ctypes.c_uint,
                             wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", ctypes.c_uint),
                ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR)]


class MSG(ctypes.Structure):
    _fields_ = [("hwnd", wintypes.HWND), ("message", ctypes.c_uint),
                ("wParam", wintypes.WPARAM), ("lParam", wintypes.LPARAM),
                ("time", wintypes.DWORD), ("pt", wintypes.POINT)]


_user32 = user32
_user32.CreateWindowExW.restype = wintypes.HWND
_user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
_user32.DefWindowProcW.restype = LRESULT
_user32.DefWindowProcW.argtypes = [wintypes.HWND, ctypes.c_uint,
                                   wintypes.WPARAM, wintypes.LPARAM]
_user32.SendMessageW.restype = LRESULT
_user32.SendMessageW.argtypes = [wintypes.HWND, ctypes.c_uint,
                                 wintypes.WPARAM, wintypes.LPARAM]

# 窗口之间的状态
_state = {"hwnd": None, "list": None, "hinst": None, "result": None,
          "options": [], "wndproc_ref": None}


def _wndproc(hwnd, msg, wparam, lparam):
    if msg == WM_COMMAND:
        cmd = wparam & 0xFFFF
        if cmd == IDOK:
            sel = _user32.SendMessageW(_state["list"], LB_GETCURSEL, 0, 0)
            _state["result"] = int(sel) if sel >= 0 else None
            _user32.DestroyWindow(hwnd)
            return 0
        if cmd == IDCANCEL:
            _state["result"] = None
            _user32.DestroyWindow(hwnd)
            return 0
    if msg == WM_CLOSE:
        _state["result"] = None
        _user32.DestroyWindow(hwnd)
        return 0
    if msg == WM_DESTROY:
        _state["hwnd"] = None
        return 0
    return _user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def _ensure_class() -> str:
    cls = "FileConvChooserWindow"
    hinst = kernel32.GetModuleHandleW(None)
    _state["hinst"] = hinst
    wc = WNDCLASSW()
    wc.lpfnWndProc = _state["wndproc_ref"] or _wndproc
    wc.hInstance = hinst
    wc.lpszClassName = cls
    wc.hCursor = _user32.LoadCursorW(None, ctypes.c_wchar_p(32512))  # IDC_ARROW
    wc.hbrBackground = gdi32.GetStockObject(4)                       # COLOR_WINDOW
    _user32.RegisterClassW(ctypes.byref(wc))
    return cls


def choose_one(instruction: str, content: str, options: list[str],
               title: str = "转换文件格式") -> int | None:
    """弹出选择窗口；返回选中下标（0 基），取消返回 None，创建失败返回 -2。"""
    if not options:
        return None
    try:
        _state["wndproc_ref"] = WNDPROC(_wndproc)
        _state["result"] = None
        cls = _ensure_class()

        hwnd = _user32.CreateWindowExW(
            0, cls, title,
            WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_VISIBLE,
            320, 220, 520, 470, None, None, _state["hinst"], None)
        if not hwnd:
            return -2
        _state["hwnd"] = hwnd

        font = gdi32.GetStockObject(DEFAULT_GUI_FONT)

        st = _user32.CreateWindowExW(0, "STATIC", instruction, WS_CHILD | WS_VISIBLE,
                                     18, 14, 484, 40, hwnd, None, _state["hinst"], None)
        _user32.SendMessageW(st, WM_SETFONT, font, 1)

        st2 = _user32.CreateWindowExW(0, "STATIC", content, WS_CHILD | WS_VISIBLE,
                                      18, 56, 484, 20, hwnd, None, _state["hinst"], None)
        _user32.SendMessageW(st2, WM_SETFONT, font, 1)

        lb = _user32.CreateWindowExW(
            0, "LISTBOX", None,
            WS_CHILD | WS_VISIBLE | WS_BORDER | WS_VSCROLL | WS_TABSTOP
            | LBS_NOTIFY | LBS_NOINTEGRALHEIGHT,
            18, 84, 484, 300, hwnd, ctypes.c_void_p(1000), _state["hinst"], None)
        _user32.SendMessageW(lb, WM_SETFONT, font, 1)
        keep = []                       # 字符串必须活着，直到 SendMessage 返回
        for text in options:
            buf = ctypes.c_wchar_p(text)
            keep.append(buf)
            _user32.SendMessageW(lb, LB_ADDSTRING, 0,
                                 ctypes.cast(buf, ctypes.c_void_p).value)
        _user32.SendMessageW(lb, LB_SETCURSEL, 0, 0)
        _state["list"] = lb

        ok = _user32.CreateWindowExW(0, "BUTTON", "确定", WS_CHILD | WS_VISIBLE | WS_TABSTOP
                                     | BS_DEFPUSHBUTTON,
                                     300, 394, 96, 30, hwnd, ctypes.c_void_p(IDOK),
                                     _state["hinst"], None)
        _user32.SendMessageW(ok, WM_SETFONT, font, 1)
        cancel = _user32.CreateWindowExW(0, "BUTTON", "取消", WS_CHILD | WS_VISIBLE
                                         | WS_TABSTOP | BS_PUSHBUTTON,
                                         406, 394, 96, 30, hwnd, ctypes.c_void_p(IDCANCEL),
                                         _state["hinst"], None)
        _user32.SendMessageW(cancel, WM_SETFONT, font, 1)

        _user32.SetFocus(lb)

        msg = MSG()
        while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if not _user32.IsDialogMessageW(hwnd, ctypes.byref(msg)):
                _user32.TranslateMessage(ctypes.byref(msg))
                _user32.DispatchMessageW(ctypes.byref(msg))

        _user32.DestroyWindow(hwnd)
        return _state["result"]
    except Exception:
        import traceback
        traceback.print_exc()
        return -2
