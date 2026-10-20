# -*- coding: utf-8 -*-
"""验证 COM 外壳扩展：能否实例化、标题/子命令是否正确。

用法： python tools\\test_com.py
"""
import ctypes
import sys
import uuid
from ctypes import wintypes

CLSID = "{7B3F9A12-4C6D-4E21-9A3B-112233445566}"
IID_IUnknown = "{00000000-0000-0000-C000-000000000046}"
IID_IExplorerCommand = "{A08CE4D0-FA25-44AB-B57C-C7B1C323E0B9}"
IID_IEnumExplorerCommand = "{A88826F8-186F-4987-AADE-EA0CEF8FBFE8}"

ole32 = ctypes.WinDLL("ole32", use_last_error=True)
ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


def guid(s: str) -> GUID:
    u = uuid.UUID(s)
    g = GUID()
    g.Data1, g.Data2, g.Data3 = u.fields[0], u.fields[1], u.fields[2]
    rest = u.bytes[8:]
    for i, b in enumerate(rest):
        g.Data4[i] = b
    return g


def vtbl_call(obj: ctypes.c_void_p, index: int, argtypes, args):
    """调用 COM 对象的第 index 个虚函数。"""
    vtbl = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))
    fn_ptr = vtbl.contents[index]
    proto = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)
    fn = proto(fn_ptr)
    return fn(obj, *args)


def read_co_str(ptr) -> str:
    if not ptr:
        return ""
    s = ctypes.wstring_at(ptr)
    ole32.CoTaskMemFree(ctypes.cast(ptr, ctypes.c_void_p))
    return s


def main() -> int:
    ole32.CoInitialize(None)
    cls, iid_u = guid(CLSID), guid(IID_IUnknown)
    p = ctypes.c_void_p()
    hr = ole32.CoCreateInstance(ctypes.byref(cls), None, 1, ctypes.byref(iid_u),
                                ctypes.byref(p))
    if hr != 0 or not p:
        print(f"[FAIL] CoCreateInstance hr=0x{hr & 0xFFFFFFFF:08X}")
        print("       说明 CLSID 没注册，或 DLL 加载失败（依赖缺失/位数不对）")
        return 1
    print("[OK]   对象创建成功")

    # GetTitle (vtable 索引 3)
    out = ctypes.c_void_p()
    hr = vtbl_call(p, 3, [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)], (None, ctypes.byref(out)))
    title = read_co_str(out.value)
    print(f"[{'OK' if hr == 0 and title else 'FAIL'}]   GetTitle = {title!r}")

    # GetIcon (索引 4)
    out2 = ctypes.c_void_p()
    vtbl_call(p, 4, [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)], (None, ctypes.byref(out2)))
    print(f"[OK]    GetIcon  = {read_co_str(out2.value)!r}")

    # GetFlags (索引 9)
    flags = ctypes.c_uint()
    vtbl_call(p, 9, [ctypes.POINTER(ctypes.c_uint)], (ctypes.byref(flags),))
    print(f"[{'OK' if flags.value & 1 else 'FAIL'}]   GetFlags = 0x{flags.value:X}（1=有子菜单）")

    # EnumSubCommands (索引 10)
    enum = ctypes.c_void_p()
    hr = vtbl_call(p, 10, [ctypes.POINTER(ctypes.c_void_p)], (ctypes.byref(enum),))
    if hr != 0 or not enum:
        print(f"[FAIL] EnumSubCommands hr=0x{hr & 0xFFFFFFFF:08X}")
        return 1

    # Next：一次取 100 个
    arr = (ctypes.c_void_p * 100)()
    fetched = ctypes.c_ulong(0)
    vtbl_call(enum, 3, [ctypes.c_ulong, ctypes.POINTER(ctypes.c_void_p),
                        ctypes.POINTER(ctypes.c_ulong)],
              (100, ctypes.cast(arr, ctypes.POINTER(ctypes.c_void_p)), ctypes.byref(fetched)))
    n = fetched.value
    print(f"[{'OK' if n > 0 else 'FAIL'}]   子命令数量 = {n}")
    labels = []
    for i in range(n):
        o = ctypes.c_void_p()
        hr = vtbl_call(arr[i], 3, [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)],
                       (None, ctypes.byref(o)))
        labels.append(read_co_str(o.value))
        vtbl_call(arr[i], 2, [], ())  # Release
    for i, s in enumerate(labels, 1):
        print(f"        {i:>2}. {s}")

    vtbl_call(enum, 2, [], ())  # Release enum
    vtbl_call(p, 2, [], ())     # Release parent
    ole32.CoUninitialize()

    ok = hr == 0 and n > 0 and title == "转换文件格式"
    print("\n结论:", "COM 扩展工作正常" if ok else "有问题，见上面 FAIL 项")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
