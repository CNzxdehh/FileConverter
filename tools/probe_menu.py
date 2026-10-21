# -*- coding: utf-8 -*-
"""直接枚举 Explorer 右键菜单树（IContextMenu），确认级联是否真的有子项。

用法： python tools\\probe_menu.py [文件路径]
输出：菜单项名称 + 子菜单项数量 + 子项名称
"""
import ctypes
import os
import sys
import tempfile
from ctypes import wintypes

ole32 = ctypes.WinDLL("ole32")
shell32 = ctypes.WinDLL("shell32")
user32 = ctypes.WinDLL("user32")


class GUID(ctypes.Structure):
    _fields_ = [("d1", ctypes.c_ulong), ("d2", ctypes.c_ushort),
                ("d3", ctypes.c_ushort), ("d4", ctypes.c_ubyte * 8)]


def g(s: str) -> GUID:
    import uuid
    u = uuid.UUID(s)
    out = GUID()
    out.d1, out.d2, out.d3 = u.fields[0], u.fields[1], u.fields[2]
    for i, b in enumerate(u.bytes[8:]):
        out.d4[i] = b
    return out


IID_IShellFolder = g("{000214E6-0000-0000-C000-000000000046}")
IID_IContextMenu = g("{000214E4-0000-0000-C000-000000000046}")
MF_BYPOSITION = 0x400


def vcall(obj, index, argtypes, args, restype=ctypes.c_long):
    vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))
    proto = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
    return proto(vtbl.contents[index])(obj, *args)


def menu_text(hmenu, index) -> str:
    buf = ctypes.create_unicode_buffer(512)
    user32.GetMenuStringW(wintypes.HMENU(hmenu), index, buf, 512, MF_BYPOSITION)
    return buf.value.replace("&", "")


def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        tempfile.gettempdir(), "fc_probe.txt")
    if not os.path.isfile(target):
        open(target, "w").write("probe")
    print("目标文件:", target)

    ole32.CoInitialize(None)

    pidl = ctypes.c_void_p()
    hr = shell32.SHParseDisplayName(ctypes.c_wchar_p(target), None,
                                    ctypes.byref(pidl), 0, None)
    if hr != 0:
        print(f"[FAIL] SHParseDisplayName 0x{hr & 0xFFFFFFFF:08X}")
        return 1

    psf = ctypes.c_void_p()
    child = ctypes.c_void_p()
    hr = shell32.SHBindToParent(pidl, ctypes.byref(IID_IShellFolder),
                                ctypes.byref(psf), ctypes.byref(child))
    if hr != 0:
        print(f"[FAIL] SHBindToParent 0x{hr & 0xFFFFFFFF:08X}")
        return 1

    # IShellFolder::GetUIObjectOf (vtable 10)
    pcm = ctypes.c_void_p()
    arr = (ctypes.c_void_p * 1)(child)
    hr = vcall(psf, 10,
               [wintypes.HWND, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p),
                ctypes.POINTER(GUID), ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)],
               (None, 1, ctypes.cast(arr, ctypes.POINTER(ctypes.c_void_p)),
                ctypes.byref(IID_IContextMenu), None, ctypes.byref(pcm)))
    if hr != 0 or not pcm.value:
        print(f"[FAIL] GetUIObjectOf 0x{hr & 0xFFFFFFFF:08X}")
        return 1

    hmenu = user32.CreatePopupMenu()
    # IContextMenu::QueryContextMenu (vtable 3)
    hr = vcall(pcm, 3,
               [wintypes.HMENU, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint],
               (hmenu, 0, 1, 0x7FFF, 0))
    if hr < 0:
        print(f"[FAIL] QueryContextMenu 0x{hr & 0xFFFFFFFF:08X}")
        return 1

    n = user32.GetMenuItemCount(hmenu)
    print(f"菜单项总数: {n}\n")

    found = False
    for i in range(n):
        text = menu_text(hmenu, i)
        sub = user32.GetSubMenu(hmenu, i)
        mark = ""
        if "转换文件格式" in text:
            found = True
            mark = "  <=== 我们的项"
        print(f"  [{i}] {text}  (子菜单={sub}){mark}")
        if sub:
            cnt = user32.GetMenuItemCount(sub)
            print(f"        └─ 子项 {cnt} 个")
            for j in range(min(cnt, 25)):
                print(f"           · {menu_text(sub, j)}")

    print("\n结论:", "找到【转换文件格式】" if found else "没找到【转换文件格式】")
    return 0 if found else 2


if __name__ == "__main__":
    sys.exit(main())
