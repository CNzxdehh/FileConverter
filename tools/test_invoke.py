# -*- coding: utf-8 -*-
"""Invoke 回归测试：模拟 Explorer 的 STA 线程点菜单项。

专门验证那个崩溃：Explorer 线程已初始化 COM 时，我们调用 Invoke 不能把它的
COM 环境拆掉（否则后续 COM 调用返回 CO_E_NOTINITIALIZED 或直接 fail-fast）。

用法： python tools\\test_invoke.py [测试图片]
"""
import os
import sys
import tempfile
import time
from ctypes import wintypes

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_com_real import (CLSID, DLL, IID_IClassFactory, IID_IUnknown,  # noqa: E402
                           IID_IShellItem, IID_IShellItemArray, call, g)

import ctypes  # noqa: E402

shell32 = ctypes.WinDLL("shell32", use_last_error=True)
ole32 = ctypes.WinDLL("ole32", use_last_error=True)

CO_E_NOTINITIALIZED = 0x800401F0


def main() -> int:
    ok = True

    # 1) 造一张测试图
    from PIL import Image
    work = os.path.join(tempfile.gettempdir(), "fc_invoke_test")
    os.makedirs(work, exist_ok=True)
    src = os.path.join(work, "invoke_probe.png")
    Image.new("RGB", (200, 120), (30, 140, 210)).save(src)
    print("测试图片:", src)

    # 2) 模拟 Explorer：当前线程先初始化 COM（STA）
    hr = ole32.CoInitialize(None)
    print(f"CoInitialize -> 0x{hr & 0xFFFFFFFF:08X}（S_OK=0 / S_FALSE=1 都正常）")

    # 3) 取真实 IShellItemArray
    psi = ctypes.c_void_p()
    shell32.SHCreateItemFromParsingName(ctypes.c_wchar_p(src), None,
                                        ctypes.byref(IID_IShellItem), ctypes.byref(psi))
    psia = ctypes.c_void_p()
    shell32.SHCreateShellItemArrayFromShellItem(psi, ctypes.byref(IID_IShellItemArray),
                                                ctypes.byref(psia))
    print("IShellItemArray:", "OK" if psia.value else "FAIL")

    # 4) 直接取类厂 → 父项 → 子命令（找 img2webp）
    dll = ctypes.WinDLL(DLL)
    fac = ctypes.c_void_p()
    dll.DllGetClassObject.argtypes = [ctypes.POINTER(type(CLSID)), ctypes.POINTER(type(CLSID)),
                                      ctypes.POINTER(ctypes.c_void_p)]
    dll.DllGetClassObject.restype = ctypes.c_long
    dll.DllGetClassObject(ctypes.byref(CLSID), ctypes.byref(IID_IClassFactory),
                          ctypes.byref(fac))
    parent = ctypes.c_void_p()
    call(fac, 3, [ctypes.c_void_p, ctypes.POINTER(type(IID_IUnknown)),
                  ctypes.POINTER(ctypes.c_void_p)],
         (None, ctypes.byref(IID_IUnknown), ctypes.byref(parent)))

    enum = ctypes.c_void_p()
    call(parent, 10, [ctypes.POINTER(ctypes.c_void_p)], (ctypes.byref(enum),))
    children = []
    while True:
        arr = (ctypes.c_void_p * 1)()
        got = ctypes.c_ulong(0)
        call(enum, 3, [ctypes.c_ulong, ctypes.POINTER(ctypes.c_void_p),
                       ctypes.POINTER(ctypes.c_ulong)],
             (1, ctypes.cast(arr, ctypes.POINTER(ctypes.c_void_p)), ctypes.byref(got)))
        if got.value == 0:
            break
        name = ctypes.c_void_p()
        call(arr[0], 3, [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)],
             (psia, ctypes.byref(name)))
        label = ctypes.wstring_at(name.value) if name.value else ""
        if name.value:
            ole32.CoTaskMemFree(ctypes.cast(name, ctypes.c_void_p))
        children.append((label, arr[0]))
    print(f"子命令 {len(children)} 个")

    target = next((c for c in children if "WEBP" in c[0].upper()), None)
    if not target:
        print("[FAIL] 没找到 图片→WEBP 子命令")
        return 1
    print("将点击:", target[0])

    # 5) 调 Invoke（这就是崩溃的那一步）
    hr = call(target[1], 8, [ctypes.c_void_p, ctypes.c_void_p], (psia, None))
    print(f"Invoke -> 0x{hr & 0xFFFFFFFF:08X}")

    # 6) 关键断言：调用后本线程 COM 必须仍然可用
    # COINIT_APARTMENTTHREADED=0x2：S_FALSE(1)=当前线程已初始化（好）；
    # S_OK(0)=被我们拆掉了又重新初始化（说明 CoUninitialize 错配，就是崩溃原因）
    hr2 = ole32.CoInitializeEx(None, 0x2)
    alive = (hr2 & 0xFFFFFFFF) == 1
    print(f"Invoke 后再 CoInitializeEx -> 0x{hr2 & 0xFFFFFFFF:08X}"
          f"  {'[OK] COM 环境完好（S_FALSE）' if alive else '[FAIL] COM 被拆掉了'}")
    ok = ok and alive
    if (hr2 & 0xFFFFFFFF) == 0:
        ole32.CoUninitialize()

    # 7) 等子进程把文件转出来
    out = os.path.join(work, "invoke_probe_转换后.webp")
    for _ in range(40):
        if os.path.isfile(out):
            break
        time.sleep(0.5)
    produced = os.path.isfile(out)
    print(f"输出文件 {os.path.basename(out)}: {'[OK] 已生成' if produced else '[FAIL] 没有生成'}")
    ok = ok and produced

    ole32.CoUninitialize()
    print("\n结论:", "Invoke 正常，无崩溃风险" if ok else "有问题，见上面 FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
