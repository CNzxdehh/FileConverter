# -*- coding: utf-8 -*-
"""隔离验证 FileConvCtx.dll（IContextMenu 级联右键子菜单外壳扩展）。

设计原则：**不写注册表、不碰 Explorer**。
用 LoadLibrary + GetProcAddress 直接拿 DllGetClassObject，
然后在测试进程里把 Explorer 右键时会做的事完整跑一遍：

    1. CreateInstance(IShellExtInit)
    2. 从 shell 取真实 IDataObject（SHParseDisplayName + GetUIObjectOf），
       支持多选（一次传 2 个 pidl，验证 HDROP 循环）
    3. IShellExtInit::Initialize
    4. QI(IContextMenu) —— 验证「双 vtable 子对象」布局没写错
    5. QueryContextMenu —— 检查插入的是 MF_POPUP 级联项、子项数=17、文字正确
    6. InvokeCommand  —— 检查真的把 FileConverter.exe runm <动词> 拉起来了

任何一步返回非 0 都算失败。跑通之前不许注册进 Explorer。
"""

from __future__ import annotations

import ctypes
import os
import re
import subprocess
import sys
import time
import uuid
from ctypes import wintypes
from pathlib import Path

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
u32 = ctypes.WinDLL("user32", use_last_error=True)
o32 = ctypes.WinDLL("ole32", use_last_error=True)
s32 = ctypes.WinDLL("shell32", use_last_error=True)

MF_BYPOSITION = 0x00000400
MF_POPUP = 0x00000010
MIIM_SUBMENU = 0x00000004
FAILS: list[str] = []


def ok(msg: str) -> None:
    print(f"  [OK]   {msg}")


def bad(msg: str) -> None:
    print(f"  [FAIL] {msg}")
    FAILS.append(msg)


def check(cond: bool, msg: str) -> bool:
    (ok if cond else bad)(msg)
    return cond


def hr_s(v: int) -> str:
    return f"0x{v & 0xFFFFFFFF:08X}"


# --------------------------------------------------------------------------- #
class GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]


def G(s: str) -> GUID:
    u = uuid.UUID(s)
    g = GUID()
    g.Data1, g.Data2, g.Data3 = u.fields[0], u.fields[1], u.fields[2]
    for i, b in enumerate(u.bytes[8:]):
        g.Data4[i] = b
    return g


IID_IClassFactory = G("{00000001-0000-0000-C000-000000000046}")
IID_IShellExtInit = G("{000214E8-0000-0000-C000-000000000046}")
IID_IContextMenu = G("{000214E4-0000-0000-C000-000000000046}")
IID_IDataObject = G("{0000010e-0000-0000-C000-000000000046}")
CLSID_CTX = G("{B2C4E111-7A9D-4C3E-8F21-9D4E5A6B7C8D}")


def vfn(p, idx, restype, *argtypes):
    """取 COM vtable 第 idx 个方法（第一个参数固定是 This 指针）。

    ⚠️ 两层解引用不能省：p → 对象，对象首字段才是 vtable 指针，
       再从这个指针取第 idx 项才是函数地址。
    """
    obj = ctypes.cast(p, ctypes.POINTER(ctypes.c_void_p))    # obj[0] = vtable
    vtbl = ctypes.cast(obj[0], ctypes.POINTER(ctypes.c_void_p))
    return ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vtbl[idx])


def release(p) -> None:
    if p and p.value:
        try:
            vfn(p, 2, ctypes.c_ulong)(p)
        except Exception:
            pass


class CMINVOKECOMMANDINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("fMask", wintypes.DWORD),
                ("hwnd", wintypes.HWND), ("lpVerb", ctypes.c_void_p),
                ("lpParameters", ctypes.c_void_p), ("lpDirectory", ctypes.c_void_p),
                ("nShow", ctypes.c_int), ("dwHotKey", wintypes.DWORD),
                ("hIcon", wintypes.HANDLE)]


# --------------------------------------------------------------------------- #
def expected_verbs(root: Path) -> list[tuple[str, str]]:
    """从 native/verbs_gen.h 解析期望的动词表，避免测试和源码漂移。"""
    h = root / "native" / "verbs_gen.h"
    out = []
    for m in re.finditer(r'\{L"([^"]+)",\s*L"([^"]+)"\}', h.read_text(encoding="utf-8")):
        out.append((m.group(1), m.group(2)))
    return out


def running_procs() -> dict[str, str]:
    """{pid: 命令行}。

    ⚠️ 必须按 PID 差分：同一个动词连点两次时命令行完全相同，
       只比对命令行会把第二次的新进程当成"早就存在"而漏掉。
    """
    ps = ('Get-CimInstance Win32_Process -Filter "Name=\'FileConverter.exe\'" '
          "| ForEach-Object { $_.ProcessId.ToString() + '|' + $_.CommandLine }")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                            "-Command", ps], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30)
        out: dict[str, str] = {}
        for ln in (r.stdout or "").splitlines():
            if "|" in ln:
                pid, cmd = ln.split("|", 1)
                out[pid.strip()] = cmd.strip()
        return out
    except Exception:
        return {}


# --------------------------------------------------------------------------- #
def main() -> int:
    root = Path(__file__).resolve().parents[1]
    dll_path = Path(sys.argv[1]) if len(sys.argv) > 1 else \
        Path.home() / "AppData/Local/Programs/FileConverter/FileConvCtx.dll"

    print(f"DLL : {dll_path}")
    if not dll_path.is_file():
        bad(f"找不到 DLL：{dll_path}")
        return 1
    if not (dll_path.parent / "FileConverter.exe").is_file():
        bad(f"DLL 旁边没有 FileConverter.exe，Launch 会直接放弃：{dll_path.parent}")
        return 1

    expected = expected_verbs(root)
    print(f"期望子项数：{len(expected)}\n")

    # 子进程会继承本进程环境：关掉控制台窗口和弹窗，避免测试时糊一屏幕窗口
    os.environ["FILECONV_NO_CONSOLE"] = "1"
    os.environ["FILECONV_SILENT"] = "1"

    # --- 测试文件 -----------------------------------------------------------
    tmp = Path(r"C:\mgtmp\fileconv_ctx_test")
    tmp.mkdir(parents=True, exist_ok=True)
    files = []
    for i in range(2):
        f = tmp / f"sample{i}.txt"
        f.write_text("hello fileconv\n", encoding="utf-8")
        files.append(f)

    o32.CoInitialize(None)

    # --- 1) LoadLibrary + DllGetClassObject --------------------------------
    print("[1] LoadLibrary / DllGetClassObject")
    # ⚠️ x64 下这两个都返回指针，必须显式声明 restype，否则被截断成 32 位 int
    k32.LoadLibraryW.argtypes = [wintypes.LPCWSTR]
    k32.LoadLibraryW.restype = ctypes.c_void_p
    k32.GetProcAddress.argtypes = [ctypes.c_void_p, wintypes.LPCSTR]
    k32.GetProcAddress.restype = ctypes.c_void_p
    h = k32.LoadLibraryW(str(dll_path))
    if not check(bool(h), f"LoadLibrary 成功 (err={ctypes.get_last_error()})"):
        return 1
    addr = k32.GetProcAddress(h, b"DllGetClassObject")
    if not check(bool(addr), "导出函数 DllGetClassObject 存在"):
        return 1
    DGCO = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.POINTER(GUID), ctypes.POINTER(GUID),
                              ctypes.POINTER(ctypes.c_void_p))(addr)
    cf = ctypes.c_void_p()
    hr = DGCO(ctypes.byref(CLSID_CTX), ctypes.byref(IID_IClassFactory), ctypes.byref(cf))
    if not check(hr == 0, f"DllGetClassObject (hr={hr_s(hr)})"):
        return 1

    # --- 2) CreateInstance(IShellExtInit) ----------------------------------
    print("\n[2] IClassFactory::CreateInstance(IShellExtInit)")
    ci = vfn(cf, 3, ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(GUID),
             ctypes.POINTER(ctypes.c_void_p))
    shl = ctypes.c_void_p()
    hr = ci(cf, None, ctypes.byref(IID_IShellExtInit), ctypes.byref(shl))
    if not check(hr == 0 and bool(shl.value), f"CreateInstance (hr={hr_s(hr)})"):
        return 1

    # --- 3) 造真实 IDataObject（多选 2 个文件）------------------------------
    print("\n[3] 构造 IDataObject（多选 2 个文件）")
    s32.SHGetDesktopFolder.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
    s32.SHGetDesktopFolder.restype = ctypes.c_long
    psf = ctypes.c_void_p()
    hr = s32.SHGetDesktopFolder(ctypes.byref(psf))
    if not check(hr == 0, f"SHGetDesktopFolder (hr={hr_s(hr)})"):
        return 1

    s32.SHParseDisplayName.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p,
                                       ctypes.POINTER(ctypes.c_void_p),
                                       wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    s32.SHParseDisplayName.restype = ctypes.c_long
    pidls = []
    for f in files:
        p = ctypes.c_void_p()
        sfgao = wintypes.DWORD()
        hr = s32.SHParseDisplayName(str(f), None, ctypes.byref(p), 0, ctypes.byref(sfgao))
        if not check(hr == 0, f"SHParseDisplayName {f.name} (hr={hr_s(hr)})"):
            return 1
        pidls.append(p)

    gdof = vfn(psf, 10, ctypes.c_long, wintypes.HWND, ctypes.c_uint,
               ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(GUID),
               ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_void_p))
    arr = (ctypes.c_void_p * len(pidls))(*[ctypes.c_void_p(p.value) for p in pidls])
    pdto = ctypes.c_void_p()
    hr = gdof(psf, None, len(pidls), arr, ctypes.byref(IID_IDataObject), None,
              ctypes.byref(pdto))
    if not check(hr == 0 and bool(pdto.value), f"GetUIObjectOf(IDataObject) (hr={hr_s(hr)})"):
        return 1

    # --- 4) IShellExtInit::Initialize --------------------------------------
    print("\n[4] IShellExtInit::Initialize")
    init = vfn(shl, 3, ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
    hr = init(shl, None, pdto, None)
    if not check(hr == 0, f"Initialize（应收集到 2 个路径）(hr={hr_s(hr)})"):
        return 1

    # --- 5) QI(IContextMenu) —— 验证双 vtable 布局 --------------------------
    print("\n[5] QueryInterface(IContextMenu) —— 验证双 vtable 子对象布局")
    qi = vfn(shl, 0, ctypes.c_long, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))
    ctx = ctypes.c_void_p()
    hr = qi(shl, ctypes.byref(IID_IContextMenu), ctypes.byref(ctx))
    if not check(hr == 0 and bool(ctx.value), f"QI(IContextMenu) (hr={hr_s(hr)})"):
        return 1

    # --- 6) QueryContextMenu ------------------------------------------------
    print("\n[6] IContextMenu::QueryContextMenu")
    u32.CreatePopupMenu.restype = wintypes.HMENU
    hmenu = u32.CreatePopupMenu()
    qcm = vfn(ctx, 3, ctypes.c_long, wintypes.HMENU, ctypes.c_uint, ctypes.c_uint,
              ctypes.c_uint, ctypes.c_uint)
    # ⚠️ idCmdFirst 故意取 5000：这样「绝对菜单 ID」=5000+i 与「相对偏移」=i
    #    是两组不同的值，才能分别验证 InvokeCommand 两种解释都认。
    IDFIRST = 5000
    hr = qcm(ctx, hmenu, 0, IDFIRST, 0x7FFF, 0)
    code = hr & 0xFFFF
    check(hr >= 0, f"QueryContextMenu 返回成功码 (hr={hr_s(hr)})")
    if not check(code == len(expected), f" returned count = {len(expected)}（实得 {code}）"):
        return 1

    n = u32.GetMenuItemCount(hmenu)
    check(n == 1, f"顶层只插入了 1 项 (实得 {n})")

    u32.GetSubMenu.restype = wintypes.HMENU
    u32.GetSubMenu.argtypes = [wintypes.HMENU, ctypes.c_int]
    sub = u32.GetSubMenu(hmenu, 0)
    is_popup = bool(u32.GetMenuState(hmenu, 0, MF_BYPOSITION) & MF_POPUP)
    check(bool(sub) and is_popup, "该顶项是 MF_POPUP 级联（不是普通菜单项）")

    u32.GetMenuStringW.argtypes = [wintypes.HMENU, ctypes.c_uint, wintypes.LPWSTR,
                                   ctypes.c_int, ctypes.c_uint]
    buf = ctypes.create_unicode_buffer(260)
    u32.GetMenuStringW(hmenu, 0, buf, 260, MF_BYPOSITION)
    check(buf.value == "转换文件格式", f"顶级文字 = 转换文件格式（实得「{buf.value}」）")

    nsub = u32.GetMenuItemCount(sub)
    check(nsub == len(expected), f"子菜单项数 = {len(expected)}（实得 {nsub}）")

    print("  子项清单：")
    for i in range(min(nsub, len(expected))):
        b = ctypes.create_unicode_buffer(260)
        u32.GetMenuStringW(sub, i, b, 260, MF_BYPOSITION)
        mid = u32.GetMenuItemID(sub, i)
        want_id, want_label = expected[i]
        good = (b.value == want_label) and (mid == IDFIRST + i)
        mark = "  [OK]  " if good else "  [FAIL]"
        print(f"    {mark} id={mid:<3} {b.value}")
        if not good:
            FAILS.append(f"子项{i}: 期望 id={IDFIRST+i} 「{want_label}」，实得 id={mid} 「{b.value}」")

    # --- 6.5) GetCommandString（经典菜单用它显示状态栏提示）-----------------
    print("\n[6.5] IContextMenu::GetCommandString（A/W 两版 + 越界防护）")
    GCS_VERBW, GCS_HELPTEXTW, GCS_VALIDATEW = 4, 5, 6
    gcs = vfn(ctx, 5, ctypes.c_long, ctypes.c_size_t, ctypes.c_uint,
              ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint)

    wb = ctypes.create_unicode_buffer(260)
    hr = gcs(ctx, 0, GCS_VERBW, None, ctypes.cast(wb, ctypes.c_void_p), 260)
    check(hr == 0 and wb.value == expected[0][0],
          f"GCS_VERBW(0) → 「{expected[0][0]}」 (hr={hr_s(hr)}, 实得「{wb.value}」)")

    wb2 = ctypes.create_unicode_buffer(260)
    hr = gcs(ctx, 1, GCS_HELPTEXTW, None, ctypes.cast(wb2, ctypes.c_void_p), 260)
    want_tip = f"用 FileConverter 执行：{expected[1][1]}"
    check(hr == 0 and wb2.value == want_tip,
          f"GCS_HELPTEXTW(1) → 「{want_tip}」 (实得「{wb2.value}」)")

    hr = gcs(ctx, 16, GCS_VALIDATEW, None, ctypes.cast(wb2, ctypes.c_void_p), 260)
    check(hr == 0, f"GCS_VALIDATEW(16) 合法 id → S_OK (hr={hr_s(hr)})")

    hr = gcs(ctx, 9999, GCS_VALIDATEW, None, ctypes.cast(wb2, ctypes.c_void_p), 260)
    check(hr != 0, f"GCS_VALIDATEW(9999) 越界 id → 拒绝 (hr={hr_s(hr)})")

    ab = ctypes.create_string_buffer(260)
    hr = gcs(ctx, 2, 0, None, ctypes.cast(ab, ctypes.c_void_p), 260)   # GCS_VERBA
    check(hr == 0 and ab.value.decode("mbcs", "replace") == expected[2][0],
          f"GCS_VERBA(2) → 「{expected[2][0]}」 (实得「{ab.value.decode('mbcs','replace')}」)")

    # --- 7) InvokeCommand ---------------------------------------------------
    # 两种 ID 解释都要认：Explorer 实际传"绝对菜单 ID"(idCmdFirst+i)，
    # 自己写的宿主（本测试）通常传"相对偏移"(i)。只认一种 → 另一端"点了没反应"。
    print("\n[7] IContextMenu::InvokeCommand（两种 ID 解释都要认）")
    inv = vfn(ctx, 4, ctypes.c_long, ctypes.POINTER(CMINVOKECOMMANDINFO))

    def invoke(raw_id: int) -> tuple[int, list[str]]:
        b4 = set(running_procs())
        ici = CMINVOKECOMMANDINFO()
        ici.cbSize = ctypes.sizeof(ici)
        ici.nShow = 1
        ici.lpVerb = ctypes.c_void_p(raw_id)
        h = inv(ctx, ctypes.byref(ici))
        got: list[str] = []
        for _ in range(20):
            time.sleep(0.25)
            now = running_procs()
            got = [now[p] for p in set(now) - b4]
            if got:
                break
        return h, got

    for style, raw in (("绝对菜单 ID", IDFIRST + 1), ("相对偏移", 1)):
        print(f"  -- 按【{style}】传 lpVerb = {raw} --")
        hr, spawned = invoke(raw)
        check(hr == 0, f"  InvokeCommand 返回 S_OK (hr={hr_s(hr)})")
        if spawned:
            ok("  检测到新进程：")
            for c in spawned:
                print(f"      {c}")
            blob = spawned[0]
            check(" runm " in blob and "docx2pdf" in blob, "  命令行为 runm docx2pdf")
            check(all(f.name in blob for f in files), "  2 个选中文件都在（多选生效）")
        else:
            bad("  没有检测到新起的 FileConverter.exe 进程（Launch 没生效）")

    # --- 清理 ---------------------------------------------------------------
    release(ctx)
    release(shl)
    release(pdto)
    release(psf)
    release(cf)
    for p in pidls:
        try:
            o32.CoTaskMemFree(ctypes.cast(p, ctypes.c_void_p))
        except Exception:
            pass
    u32.DestroyMenu(hmenu)
    o32.CoUninitialize()

    print("\n" + "=" * 60)
    if FAILS:
        print(f"结果：失败 {len(FAILS)} 项")
        for f in FAILS:
            print(f"  - {f}")
        return 1
    print("结果：全部通过 ✔ 级联子菜单外壳扩展可以安全注册")
    return 0


if __name__ == "__main__":
    sys.exit(main())
