# -*- coding: utf-8 -*-
"""验证智能判断：右键不同文件类型时，级联菜单只列出相关转换项。

设计要点：
  - 每种类型各建一个真实文件，走 GetUIObjectOf 拿 IDataObject
  - 调 QueryContextMenu 后读子菜单项，核对数量和标题
  - 混合类型（PDF+图片）应该取并集
  - 未知类型（.txt）应该全列（不能让菜单变空）

预期（verbs_gen.h 顺序：0 pdf2docx,1 docx2pdf,2 pdf2txt,3 docx2txt,4 pdf2img,
5 pdfmerge,6 img2png,7 img2jpg,8 img2webp,9 img2pdf,10 imgs2pdf,11 imgcompress,
12 aud2mp3,13 aud2wav,14 vid2mp3,15 vid2mp4,16 vid2gif）：
  .pdf  → 4 项  标题「转换 PDF」
  .docx → 2 项  标题「转换 Word」
  .jpg  → 6 项  标题「转换图片」
  .mp3  → 2 项  标题「转换音频」
  .mp4  → 3 项  标题「转换视频」
  .txt  → 17 项 标题「转换文件格式」
  .pdf+.jpg 混合 → 10 项（4+6）
"""
from __future__ import annotations

import ctypes
import re
import sys
import uuid
from ctypes import wintypes
from pathlib import Path

u32 = ctypes.WinDLL("user32", use_last_error=True)
o32 = ctypes.WinDLL("ole32", use_last_error=True)

FAILS: list[str] = []
WORK = Path(r"C:\mgtmp\smart_test")


def ok(m): print(f"  [OK]   {m}")
def bad(m): print(f"  [FAIL] {m}"); FAILS.append(m)
def check(c, m): (ok if c else bad)(m); return c


class GUID(ctypes.Structure):
    _fields_ = [("d1", ctypes.c_ulong), ("d2", ctypes.c_ushort),
                ("d3", ctypes.c_ushort), ("d4", ctypes.c_ubyte * 8)]


def G(s: str) -> GUID:
    u = uuid.UUID(s)
    g = GUID()
    g.d1, g.d2, g.d3 = u.fields[0], u.fields[1], u.fields[2]
    for i, b in enumerate(u.bytes[8:]):
        g.d4[i] = b
    return g


IID_CLASSFACTORY = G("{00000001-0000-0000-C000-000000000046}")
IID_SHELLEXTINIT = G("{000214E8-0000-0000-C000-000000000046}")
IID_CONTEXTMENU = G("{000214E4-0000-0000-C000-000000000046}")
IID_DATAOBJECT = G("{0000010E-0000-0000-C000-000000000046}")
CLSID_CTX = G("{B2C4E111-7A9D-4C3E-8F21-9D4E5A6B7C8D}")

u32.CreatePopupMenu.restype = wintypes.HMENU
u32.GetSubMenu.restype = wintypes.HMENU
u32.GetMenuStringW.argtypes = [wintypes.HMENU, ctypes.c_uint, wintypes.LPWSTR,
                               ctypes.c_int, ctypes.c_uint]


def vfn(p, idx, restype, *argtypes):
    obj = ctypes.cast(p, ctypes.POINTER(ctypes.c_void_p))
    vt = ctypes.cast(obj[0], ctypes.POINTER(ctypes.c_void_p))
    return ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vt[idx])


def build_ctx(dll: Path):
    k32 = ctypes.WinDLL("kernel32")
    k32.LoadLibraryW.argtypes = [wintypes.LPCWSTR]
    k32.LoadLibraryW.restype = ctypes.c_void_p
    k32.GetProcAddress.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    k32.GetProcAddress.restype = ctypes.c_void_p
    h = k32.LoadLibraryW(str(dll))
    if not h:
        raise RuntimeError(f"LoadLibrary 失败: {ctypes.get_last_error()}")
    addr = k32.GetProcAddress(ctypes.c_void_p(h), b"DllGetClassObject")
    if not addr:
        raise RuntimeError("找不到 DllGetClassObject 导出")
    DGCO = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.POINTER(GUID), ctypes.POINTER(GUID),
                              ctypes.POINTER(ctypes.c_void_p))(addr)
    DGCO = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.POINTER(GUID), ctypes.POINTER(GUID),
                              ctypes.POINTER(ctypes.c_void_p))(addr)
    cf = ctypes.c_void_p()
    DGCO(ctypes.byref(CLSID_CTX), ctypes.byref(IID_CLASSFACTORY), ctypes.byref(cf))
    ci = vfn(cf, 3, ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(GUID),
             ctypes.POINTER(ctypes.c_void_p))
    shl = ctypes.c_void_p()
    ci(cf, None, ctypes.byref(IID_SHELLEXTINIT), ctypes.byref(shl))
    return shl


def data_object(files: list[Path]):
    shell = ctypes.WinDLL("shell32")
    shell.SHGetDesktopFolder.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
    shell.SHGetDesktopFolder.restype = ctypes.c_long
    psf = ctypes.c_void_p()
    shell.SHGetDesktopFolder(ctypes.byref(psf))
    shell.SHParseDisplayName.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p,
                                         ctypes.POINTER(ctypes.c_void_p),
                                         wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    pidls = []
    for f in files:
        p = ctypes.c_void_p()
        shell.SHParseDisplayName(str(f), None, ctypes.byref(p), 0, None)
        pidls.append(p)
    arr = (ctypes.c_void_p * len(pidls))(*[ctypes.c_void_p(p.value) for p in pidls])
    pdto = ctypes.c_void_p()
    gdof = vfn(psf, 10, ctypes.c_long, wintypes.HWND, ctypes.c_uint,
               ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(GUID),
               ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_void_p))
    gdof(psf, None, len(pidls), arr, ctypes.byref(IID_DATAOBJECT), None,
         ctypes.byref(pdto))
    return pdto


def probe(dll: Path, files: list[Path]) -> tuple[str, list[str]]:
    """建一个全新的对象，喂给定文件，返回 (菜单标题, [子项文字])。"""
    shl = build_ctx(dll)
    pdto = data_object(files)
    init = vfn(shl, 3, ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
    hr = init(shl, None, pdto, None)
    if hr != 0:
        raise RuntimeError(f"Initialize 失败 0x{hr & 0xFFFFFFFF:08X}")
    qi = vfn(shl, 0, ctypes.c_long, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))
    ctx = ctypes.c_void_p()
    qi(shl, ctypes.byref(IID_CONTEXTMENU), ctypes.byref(ctx))

    hmenu = u32.CreatePopupMenu()
    qcm = vfn(ctx, 3, ctypes.c_long, wintypes.HMENU, ctypes.c_uint, ctypes.c_uint,
              ctypes.c_uint, ctypes.c_uint)
    hr = qcm(ctx, hmenu, 0, 5000, 0x7FFF, 0)
    n = hr & 0xFFFF

    # 顶层应该只有 1 项（级联），读它的标题
    title = ""
    top = u32.GetMenuItemCount(hmenu)
    if top:
        b = ctypes.create_unicode_buffer(260)
        u32.GetMenuStringW(hmenu, 0, b, 260, 0x400)
        title = b.value
    sub = u32.GetSubMenu(hmenu, 0)
    items = []
    if sub:
        ns = u32.GetMenuItemCount(sub)
        for i in range(ns):
            b = ctypes.create_unicode_buffer(260)
            u32.GetMenuStringW(sub, i, b, 260, 0x400)
            items.append(b.value)
    u32.DestroyMenu(ctypes.c_void_p(hmenu))
    vfn(ctx, 2, ctypes.c_ulong)(ctx)
    vfn(shl, 2, ctypes.c_ulong)(shl)
    return title, items


def expected_labels(root: Path) -> list[str]:
    h = root / "native" / "verbs_gen.h"
    return [m.group(2) for m in
            re.finditer(r'\{L"([^"]+)",\s*L"([^"]+)"\}', h.read_text(encoding="utf-8"))]


def main() -> int:
    dll = Path.home() / r"AppData\Local\Programs\FileConverter\FileConvCtx.dll"
    root = Path(__file__).resolve().parents[1]
    if not dll.is_file():
        print(f"找不到 DLL: {dll}")
        return 1

    WORK.mkdir(parents=True, exist_ok=True)
    labels = expected_labels(root)

    # 扩展名 → (期望标题, 期望子项索引)
    CASES = [
        ("sample.pdf",  "转换 PDF",        [0, 2, 4, 5]),
        ("sample.docx", "转换 Word",       [1, 3]),
        ("sample.jpg",  "转换图片",         [6, 7, 8, 9, 10, 11]),
        ("sample.png",  "转换图片",         [6, 7, 8, 9, 10, 11]),
        ("sample.mp3",  "转换音频",         [12, 13]),
        ("sample.mp4",  "转换视频",         [14, 15, 16]),
        ("sample.mkv",  "转换视频",         [14, 15, 16]),
    ]

    print("=" * 74)
    print("单类型：只显示相关转换")
    print("=" * 74)
    for name, want_title, want_idx in CASES:
        f = WORK / name
        f.write_bytes(b"x")
        title, items = probe(dll, [f])
        want_items = [labels[i] for i in want_idx]
        good = (title == want_title and items == want_items)
        mark = "  [OK]  " if good else "  [FAIL]"
        print(f"{mark}{name:14s} 标题「{title}」 子项 {len(items)} 个")
        if not good:
            print(f"          期望标题「{want_title}」")
            print(f"          期望子项 {want_items}")
            print(f"          实得子项 {items}")
            FAILS.append(f"{name} 筛选不对")

    print()
    print("=" * 74)
    print("未知类型：不能变空，全列")
    print("=" * 74)
    f = WORK / "sample.txt"
    f.write_bytes(b"hello")
    title, items = probe(dll, [f])
    check(title == "转换文件格式" and len(items) == 17,
          f".txt → 标题「{title}」 子项 {len(items)} 个（应为 17）")

    print()
    print("=" * 74)
    print("混合类型：取并集")
    print("=" * 74)
    a, b = WORK / "sample.pdf", WORK / "sample.jpg"
    title, items = probe(dll, [a, b])
    # PDF 4 项 + 图片 6 项 = 10 项，顺序按 kVerbs 原顺序
    want = [labels[i] for i in [0, 2, 4, 5, 6, 7, 8, 9, 10, 11]]
    check(items == want and len(items) == 10,
          f"PDF+图片 → 子项 {len(items)} 个（应为 10）")
    if items != want:
        print(f"          期望 {want}")
        print(f"          实得 {items}")
        FAILS.append("混合类型并集不对")

    print()
    print("=" * 74)
    print(f"结果：{'全部通过 ✔' if not FAILS else f'失败 {len(FAILS)} 项'}")
    for f in FAILS:
        print(f"  - {f}")
    print("=" * 74)
    return 1 if FAILS else 0


if __name__ == "__main__":
    o32.CoInitialize(None)
    sys.exit(main())