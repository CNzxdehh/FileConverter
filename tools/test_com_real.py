# -*- coding: utf-8 -*-
"""离屏复现：用真实的 IShellItemArray 调用我们的 COM 实现，看会不会崩。

不写注册表、不碰 explorer —— 直接 LoadLibrary + DllGetClassObject。
用法： python tools\\test_com_real.py [文件路径]
"""
import ctypes
import os
import sys
from ctypes import wintypes

DLL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "native", "FileConvMenu.dll")

shell32 = ctypes.WinDLL("shell32", use_last_error=True)
ole32 = ctypes.WinDLL("ole32", use_last_error=True)


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


CLSID = g("{7B3F9A12-4C6D-4E21-9A3B-112233445566}")
IID_IShellItem = g("{43826D1E-E718-42EE-BC55-A1E261C37BFE}")
IID_IShellItemArray = g("{B63EA76D-1F85-456F-A19C-48159EFA858B}")
IID_IUnknown = g("{00000000-0000-0000-C000-000000000046}")
IID_IClassFactory = g("{00000001-0000-0000-C000-000000000046}")


def call(obj, index, argtypes, args, restype=ctypes.c_long):
    vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))
    proto = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
    return proto(vtbl.contents[index])(obj, *args)


def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("USERPROFILE", "C:\\")
    print("目标:", target)
    print("DLL :", DLL, "exists=", os.path.isfile(DLL))

    ole32.CoInitialize(None)

    # 1) 真实 IShellItemArray
    psi = ctypes.c_void_p()
    hr = shell32.SHCreateItemFromParsingName(
        ctypes.c_wchar_p(target), None, ctypes.byref(IID_IShellItem), ctypes.byref(psi))
    print(f"SHCreateItemFromParsingName hr=0x{hr & 0xFFFFFFFF:08X}")
    if hr != 0:
        return 1
    psia = ctypes.c_void_p()
    hr = shell32.SHCreateShellItemArrayFromShellItem(
        psi, ctypes.byref(IID_IShellItemArray), ctypes.byref(psia))
    print(f"SHCreateShellItemArrayFromShellItem hr=0x{hr & 0xFFFFFFFF:08X}")
    if hr != 0:
        return 1

    # 2) 直接取类厂（不走注册表）
    dll = ctypes.WinDLL(DLL, use_last_error=True)
    get_class = dll.DllGetClassObject
    get_class.restype = ctypes.c_long
    get_class.argtypes = [ctypes.POINTER(GUID), ctypes.POINTER(GUID),
                          ctypes.POINTER(ctypes.c_void_p)]
    fac = ctypes.c_void_p()
    hr = get_class(ctypes.byref(CLSID), ctypes.byref(IID_IClassFactory), ctypes.byref(fac))
    print(f"DllGetClassObject hr=0x{hr & 0xFFFFFFFF:08X}")

    # 3) CreateInstance
    obj = ctypes.c_void_p()
    hr = call(fac, 3, [ctypes.c_void_p, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)],
              (None, ctypes.byref(IID_IUnknown), ctypes.byref(obj)))
    print(f"CreateInstance hr=0x{hr & 0xFFFFFFFF:08X}")

    # 4) 用真实 psia 逐个方法调用（这些就是 explorer 会调的）
    out = ctypes.c_void_p()
    hr = call(obj, 3, [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)],
              (psia, ctypes.byref(out)))
    title = ctypes.wstring_at(out.value) if out.value else ""
    if out.value:
        ole32.CoTaskMemFree(ctypes.cast(out, ctypes.c_void_p))
    print(f"GetTitle(psia) hr=0x{hr & 0xFFFFFFFF:08X} -> {title!r}")

    out2 = ctypes.c_void_p()
    hr = call(obj, 4, [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)],
              (psia, ctypes.byref(out2)))
    print(f"GetIcon(psia) hr=0x{hr & 0xFFFFFFFF:08X} -> "
          f"{(ctypes.wstring_at(out2.value) if out2.value else '')!r}")

    out3 = ctypes.c_void_p()
    hr = call(obj, 5, [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)],
              (psia, ctypes.byref(out3)))
    print(f"GetToolTip(psia) hr=0x{hr & 0xFFFFFFFF:08X}")

    state = ctypes.c_uint()
    hr = call(obj, 7, [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_uint)],
              (psia, 1, ctypes.byref(state)))
    print(f"GetState(psia) hr=0x{hr & 0xFFFFFFFF:08X} state={state.value}")

    flags = ctypes.c_uint()
    hr = call(obj, 9, [ctypes.POINTER(ctypes.c_uint)], (ctypes.byref(flags),))
    print(f"GetFlags hr=0x{hr & 0xFFFFFFFF:08X} flags=0x{flags.value:X}")

    enum = ctypes.c_void_p()
    hr = call(obj, 10, [ctypes.POINTER(ctypes.c_void_p)], (ctypes.byref(enum),))
    print(f"EnumSubCommands hr=0x{hr & 0xFFFFFFFF:08X}")

    # 5) 一次取 1 个，模拟 explorer 的拉取方式（最容易踩 edge case）
    total = 0
    while True:
        arr = (ctypes.c_void_p * 1)()
        got = ctypes.c_ulong(0)
        hr = call(enum, 3, [ctypes.c_ulong, ctypes.POINTER(ctypes.c_void_p),
                            ctypes.POINTER(ctypes.c_ulong)],
                  (1, ctypes.cast(arr, ctypes.POINTER(ctypes.c_void_p)), ctypes.byref(got)))
        if got.value == 0:
            break
        o = ctypes.c_void_p()
        call(arr[0], 3, [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)],
             (psia, ctypes.byref(o)))
        if o.value:
            ole32.CoTaskMemFree(ctypes.cast(o, ctypes.c_void_p))
        call(arr[0], 2, [], ())
        total += 1
        if total > 200:
            break
    print(f"Next 逐个拉取，共 {total} 个（应为 17）")

    call(enum, 2, [], ())
    call(obj, 2, [], ())
    ole32.CoUninitialize()
    print("\n没有崩溃 —— 我们的 DLL 在真实 shell item 上是安全的")
    return 0


if __name__ == "__main__":
    sys.exit(main())
