# -*- coding: utf-8 -*-
"""验证「连续 ID 映射」这个修复。

bug 背景：菜单项 ID 曾用 idCmdFirst+show[i]（show[i] 是原动词索引），
但返回值告诉 Explorer「我只占了 N 个 ID」→ Explorer 认定 ID 范围是
idCmdFirst ~ idCmdFirst+N-1，两者对不上 → 点击后 Explorer 认为不是我们的项，
InvokeCommand 永远不被调用（用户看到的就是"按了没用"）。

这个测试专门验：智能筛选后，菜单项用连续 ID，且 InvokeCommand(绝对ID)
能映射回正确的动词。对视频文件（只显示 3 项：vid2mp3/vid2mp4/vid2gif，
原索引 14/15/16）：
    InvokeCommand(5000) → 应该是 vid2mp3  (第 1 项)
    InvokeCommand(5001) → 应该是 vid2mp4  (第 2 项)  ← 旧代码会错成 docx2pdf
    InvokeCommand(5002) → 应该是 vid2gif  (第 3 项)
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_smart import (G, GUID, build_ctx, data_object,   # noqa: E402
                        vfn)

IID_ICM = G("{000214E4-0000-0000-C000-000000000046}")
FAILS: list[str] = []
WORK = Path(r"C:\mgtmp\id_test")


class CMINVOKECOMMANDINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("fMask", ctypes.c_uint),
                ("hwnd", ctypes.c_void_p), ("lpVerb", ctypes.c_void_p),
                ("lpParameters", ctypes.c_char_p), ("lpDirectory", ctypes.c_char_p),
                ("nShow", ctypes.c_int), ("dwHotKey", ctypes.c_uint),
                ("hIcon", ctypes.c_void_p)]


def running() -> dict[str, str]:
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='FileConverter.exe'\" "
          "| ForEach-Object { $_.ProcessId.ToString() + '|' + $_.CommandLine }")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                            "-Command", ps], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60)
    except Exception:
        return {}
    out = {}
    for ln in (r.stdout or "").splitlines():
        if "|" in ln:
            pid, cmd = ln.split("|", 1)
            out[pid.strip()] = cmd.strip()
    return out


def invoke_and_catch(shl, raw_id: int) -> str:
    """调 InvokeCommand，返回新进程的命令行（用于确认触发的是哪个动词）。"""
    pdto = data_object([WORK / "clip.mp4"])
    init = vfn(shl, 3, ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
    init(shl, None, pdto, None)
    qi = vfn(shl, 0, ctypes.c_long, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))
    ctx = ctypes.c_void_p()
    qi(shl, ctypes.byref(IID_ICM), ctypes.byref(ctx))

    hmenu = ctypes.WinDLL("user32").CreatePopupMenu()
    qcm = vfn(ctx, 3, ctypes.c_long, wintypes_hm := ctypes.c_void_p,
              ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint)
    # 注意：上面 wintypes_hm 只是占位，实际类型见下面重新取
    del qcm
    u32 = ctypes.WinDLL("user32")
    u32.CreatePopupMenu.restype = ctypes.c_void_p
    hmenu = u32.CreatePopupMenu()
    qcm = vfn(ctx, 3, ctypes.c_long, ctypes.c_void_p, ctypes.c_uint,
              ctypes.c_uint, ctypes.c_uint, ctypes.c_uint)
    hr = qcm(ctx, hmenu, 0, 5000, 0x7FFF, 0)
    nshow = hr & 0xFFFF

    before = set(running())
    ici = CMINVOKECOMMANDINFO()
    ici.cbSize = ctypes.sizeof(ici)
    ici.nShow = 1
    ici.lpVerb = ctypes.c_void_p(raw_id)
    inv = vfn(ctx, 4, ctypes.c_long, ctypes.POINTER(CMINVOKECOMMANDINFO))
    r = inv(ctx, ctypes.byref(ici))

    got = ""
    for _ in range(24):
        time.sleep(0.25)
        now = running()
        new = [now[p] for p in set(now) - before]
        if new:
            got = new[0]
            break
    u32.DestroyMenu(ctypes.c_void_p(hmenu))
    vfn(ctx, 2, ctypes.c_ulong)(ctx)
    return f"hr=0x{r & 0xFFFFFFFF:08X} nshow={nshow} cmd={got}"


def main() -> int:
    dll = Path.home() / r"AppData\Local\Programs\FileConverter\FileConvCtx.dll"
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "clip.mp4").write_bytes(b"x")

    shl = build_ctx(dll)

    print("=" * 78)
    print("视频文件只显示 3 项（原索引 14/15/16），菜单项 ID 必须连续编号")
    print("=" * 78)
    CASES = [(5000, "vid2mp3"), (5001, "vid2mp4"), (5002, "vid2gif")]
    for raw, want_verb in CASES:
        out = invoke_and_catch(shl, raw)
        ok = want_verb in out
        print(f"  [{'OK ' if ok else 'ERR'}] InvokeCommand({raw}) → {want_verb}")
        print(f"         {out[:130]}")
        if not ok:
            FAILS.append(f"InvokeCommand({raw}) 没触发 {want_verb}")

    print()
    print("=" * 78)
    print("越界 ID 必须被拒绝（不能误触发）")
    print("=" * 78)
    out = invoke_and_catch(shl, 5003)
    ok = "hr=0x80070057" in out
    print(f"  [{'OK ' if ok else 'ERR'}] InvokeCommand(5003) 越界 → {out[:90]}")
    if not ok:
        FAILS.append("越界 ID 没被拒绝")

    print("\n" + "=" * 78)
    if FAILS:
        print(f"结果：失败 {len(FAILS)} 项")
        for f in FAILS:
            print(f"  - {f}")
        return 1
    print("结果：全部通过 ✔ 连续 ID 映射正确，点击应该能触发对应转换了")
    return 0


if __name__ == "__main__":
    ctypes.WinDLL("ole32").CoInitialize(None)
    sys.exit(main())