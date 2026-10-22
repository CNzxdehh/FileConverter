# -*- coding: utf-8 -*-
"""验证 IContextMenu2 / IContextMenu3 能通过 QueryInterface 拿到。

这是"点了没反应"的根因：插了 MF_POPUP 子菜单，Explorer 的菜单消息循环
必须能 QI 到这两个接口才能把消息转下来。缺了它们子菜单照样显示，
但点击永远不触发 InvokeCommand。
"""
from __future__ import annotations

import ctypes
import sys
import uuid
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_smart import G, GUID, build_ctx, data_object, vfn   # noqa: E402

IID_ICM = G("{000214E4-0000-0000-C000-000000000046}")
IID_ICM2 = G("{000214F0-0000-0000-C000-000000000046}")
IID_ICM3 = G("{000214FF-0000-0000-C000-000000000046}")
IID_SEI = G("{000214E8-0000-0000-C000-000000000046}")

FAILS: list[str] = []
WORK = Path(r"C:\mgtmp\qi_test")
WORK.mkdir(parents=True, exist_ok=True)


def qi(shl, iid):
    fn = vfn(shl, 0, ctypes.c_long, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))
    out = ctypes.c_void_p()
    hr = fn(shl, ctypes.byref(iid), ctypes.byref(out))
    return hr, out


def main() -> int:
    dll = Path.home() / r"AppData\Local\Programs\FileConverter\FileConvCtx.dll"
    f = WORK / "probe.mp4"
    f.write_bytes(b"x")

    shl = build_ctx(dll)
    pdto = data_object([f])
    init = vfn(shl, 3, ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
    hr = init(shl, None, pdto, None)
    print(f"IShellExtInit::Initialize = 0x{hr & 0xFFFFFFFF:08X}\n")

    print("=== QueryInterface 各接口 ===")
    for name, iid in (("IContextMenu ", IID_ICM), ("IContextMenu2", IID_ICM2),
                      ("IContextMenu3", IID_ICM3), ("IShellExtInit", IID_SEI)):
        hr, p = qi(shl, iid)
        ok = (hr == 0 and p.value is not None)
        print(f"  [{'OK ' if ok else 'ERR'}] {name} → 0x{hr & 0xFFFFFFFF:08X}"
              + ("" if ok else "  ← 拿不到！"))
        if not ok and name in ("IContextMenu2", "IContextMenu3"):
            FAILS.append(f"{name} 拿不到（子菜单点击会没反应）")
        if p.value:
            vfn(p, 2, ctypes.c_ulong)(p)      # Release

    # HandleMenuMsg / HandleMenuMsg2 能不能调（vtable 下标 6/7）
    print("\n=== HandleMenuMsg / HandleMenuMsg2 调用 ===")
    hr, p = qi(shl, IID_ICM3)
    if p.value:
        obj = ctypes.cast(p, ctypes.POINTER(ctypes.c_void_p))
        vt = ctypes.cast(obj[0], ctypes.POINTER(ctypes.c_void_p))
        for idx, nm in ((6, "HandleMenuMsg "), (7, "HandleMenuMsg2")):
            try:
                if nm.strip() == "HandleMenuMsg":
                    # vfn 造出来的函数原型是 (restype, This, uMsg, wParam, lParam)
                    fn = vfn(p, idx, ctypes.c_long, ctypes.c_uint,
                             ctypes.c_size_t, ctypes.c_ssize_t)
                    r = fn(p, 0x0117, 0, 0)          # WM_INITMENUPOPUP
                else:
                    fn = vfn(p, idx, ctypes.c_long, ctypes.c_uint,
                             ctypes.c_size_t, ctypes.c_ssize_t,
                             ctypes.POINTER(ctypes.c_ssize_t))
                    res = ctypes.c_ssize_t(0)
                    r = fn(p, 0x0117, 0, 0, ctypes.byref(res))
                print(f"  [OK ] {nm}(WM_INITMENUPOPUP) = 0x{r & 0xFFFFFFFF:08X}")
            except Exception as e:
                print(f"  [ERR] {nm} 调用失败: {e}")
                FAILS.append(f"{nm} 调不到")
        vfn(p, 2, ctypes.c_ulong)(p)

    print("\n" + "=" * 60)
    if FAILS:
        print(f"结果：失败 {len(FAILS)} 项")
        for x in FAILS:
            print(f"  - {x}")
        return 1
    print("结果：全部通过 ✔ IContextMenu2/3 已就绪，子菜单点击应该能触发了")
    return 0


if __name__ == "__main__":
    ctypes.WinDLL("ole32").CoInitialize(None)
    sys.exit(main())