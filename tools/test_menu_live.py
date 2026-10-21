# -*- coding: utf-8 -*-
"""真实右键一次，把弹出的菜单窗口枚举出来，确认级联子菜单渲染成功。

为什么需要它：`FolderItem.Verbs()` 只枚举带命令 ID 的菜单项，
级联 popup（MF_POPUP）没有命令 ID，**必然被跳过** —— 用它验证级联 = 假阴性。

做法：
    1. 打开一个资源管理器窗口到测试目录
    2. Ctrl+A 全选 → Shift+F10 唤出完整右键菜单
    3. 等 #32768 菜单窗口出现，SendMessage(MN_GETHMENU) 拿到 HMENU
    4. 逐项读标题，找到【转换文件格式】后展开它的子菜单并列出全部子项
    5. 关掉菜单和窗口

⚠️ 会真的弹出一个资源管理器窗口和菜单，跑的时候别抢鼠标。
"""

from __future__ import annotations

import ctypes
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

u32 = ctypes.WinDLL("user32", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)

MN_GETHMENU = 0x01E1
WM_CLOSE = 0x0010
WM_COMMAND = 0x0111
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
VK_CONTROL = 0x11
VK_SHIFT = 0x10
VK_F10 = 0x79
SW_RESTORE = 9
MF_BYPOSITION = 0x400
MF_POPUP = 0x10

u32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
u32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
u32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND,
                                               wintypes.LPARAM), wintypes.LPARAM]
u32.GetMenuStringW.argtypes = [wintypes.HMENU, ctypes.c_uint, wintypes.LPWSTR,
                               ctypes.c_int, ctypes.c_uint]
u32.GetSubMenu.restype = wintypes.HMENU
u32.GetSubMenu.argtypes = [wintypes.HMENU, ctypes.c_int]
u32.GetMenuItemID.argtypes = [wintypes.HMENU, ctypes.c_int]


def find_windows(class_name: str) -> list[int]:
    out: list[int] = []
    cb = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(
        lambda h, _l: (out.append(h), True)[1])
    u32.EnumWindows(cb, 0)
    res = []
    for h in out:
        buf = ctypes.create_unicode_buffer(256)
        if u32.GetClassNameW(h, buf, 256) and buf.value == class_name:
            res.append(h)
    return res


def title_of(h: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    u32.GetWindowTextW(h, buf, 256)
    return buf.value


def find_window_by_class_and_title(cn: str, needle: str) -> int | None:
    for h in find_windows(cn):
        if needle.lower() in title_of(h).lower():
            return h
    return None


def tap(vk: int, down: bool) -> None:
    u32.keybd_event(ctypes.c_ubyte(vk), ctypes.c_ubyte(0),
                    0 if down else 0x0002, 0)
    time.sleep(0.05)


def chord(mod: int, vk: int) -> None:
    tap(mod, True)
    tap(vk, True)
    tap(vk, False)
    tap(mod, False)
    time.sleep(0.25)


FAILS: list[str] = []


def expected_verbs(root: Path) -> list[tuple[str, str]]:
    """从 native/verbs_gen.h 解析期望的 (动词, 菜单文字)。"""
    import re

    h = root / "native" / "verbs_gen.h"
    return [(m.group(1), m.group(2)) for m in
            re.finditer(r'\{L"([^"]+)",\s*L"([^"]+)"\}', h.read_text(encoding="utf-8"))]


def expected_labels(root: Path) -> list[str]:
    return [lbl for _v, lbl in expected_verbs(root)]


def running_cmds() -> set[str]:
    import subprocess

    ps = ('Get-CimInstance Win32_Process -Filter "Name=\'FileConverter.exe\'" '
          "| Select-Object -ExpandProperty CommandLine")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                            "-Command", ps], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30)
        return {ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()}
    except Exception:
        return set()


def main() -> int:
    folder = Path(r"C:\mgtmp\fileconv_ctx_test")
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(2):
        f = folder / f"menu_test{i}.txt"
        f.write_text("hello\n", encoding="utf-8")

    print("[1] 打开资源管理器窗口…")
    subprocess.Popen(["explorer.exe", str(folder)])
    hwnd = None
    for _ in range(40):
        time.sleep(0.25)
        hwnd = find_window_by_class_and_title("CabinetWClass", "fileconv_ctx_test")
        if hwnd:
            break
    if not hwnd:
        print("  [FAIL] 没找到资源管理器窗口（CabinetWClass）")
        return 1
    print(f"  [OK]   窗口句柄 {hwnd}  标题「{title_of(hwnd)}」")

    print("[2] 唤出完整右键菜单")
    u32.ShowWindow(hwnd, SW_RESTORE)
    u32.BringWindowToTop(hwnd)
    time.sleep(0.8)

    # 路线 A：键盘（Ctrl+A 全选 + Shift+F10）—— 依赖抢到前台，有时会静默失败
    cur_tid = k32.GetCurrentThreadId()
    tgt_tid = u32.GetWindowThreadProcessId(hwnd, None)
    u32.AttachThreadInput(cur_tid, tgt_tid, True)
    u32.SetForegroundWindow(hwnd)
    u32.SetFocus(hwnd)
    u32.AttachThreadInput(cur_tid, tgt_tid, False)
    time.sleep(0.6)
    chord(VK_CONTROL, 0x41)                  # Ctrl + A 全选
    tap(VK_SHIFT, True)
    tap(VK_F10, True)
    tap(VK_F10, False)
    tap(VK_SHIFT, False)

    print("[3] 等待 #32768 菜单窗口…")
    menu_hwnd = None
    for _ in range(20):
        time.sleep(0.15)
        ws = find_windows("#32768")
        if ws:
            menu_hwnd = ws[0]
            break

    if not menu_hwnd:
        # 路线 B：鼠标 —— 先左键点中第一个文件，再右键它
        # ⚠️ 必须点中文件：直接右键列表空白处拿到的是「文件夹背景」菜单
        #    （查看/排序/粘贴/新建…），里面当然没有我们的项，会误判成"菜单项消失"。
        view = u32.FindWindowExW(hwnd, None, "SHELLDLL_DefView", None)
        target = view if view else hwnd
        rect = wintypes.RECT()
        u32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        u32.GetWindowRect(target, ctypes.byref(rect))
        if rect.right <= rect.left:
            print("  [FAIL] 拿不到文件列表区域")
            u32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            return 1
        # 列表视图里第一个文件大约在左上角
        fx = rect.left + 45
        fy = rect.top + 32

        # ⚠️ 必须先把窗口提到最上层：被别的程序（WorkBuddy/浏览器）挡住时，
        #    鼠标点击会打在覆盖窗口上，菜单永远弹不出来。
        #    HWND_TOPMOST = -1，HWND_NOTOPMOST = -2，SWP_NOMOVE|NOSIZE|SHOWWINDOW = 0x0043
        SWP = 0x0001 | 0x0002 | 0x0040
        u32.SetWindowPos(hwnd, ctypes.c_void_p(-1), 0, 0, 0, 0, SWP)
        time.sleep(0.5)

        print(f"  文件列表区域 {rect.left},{rect.top} → {rect.right},{rect.bottom}")
        print(f"  左键选中第一个文件 ({fx}, {fy})")
        u32.SetCursorPos(fx, fy)
        time.sleep(0.4)
        u32.mouse_event(0x0002, 0, 0, 0, 0)   # LEFTDOWN
        time.sleep(0.05)
        u32.mouse_event(0x0004, 0, 0, 0, 0)   # LEFTUP
        time.sleep(0.6)
        u32.SetCursorPos(fx, fy)
        time.sleep(0.2)
        print(f"  右键同一位置 ({fx}, {fy})")
        u32.mouse_event(0x0008, 0, 0, 0, 0)   # RIGHTDOWN
        time.sleep(0.08)
        u32.mouse_event(0x0010, 0, 0, 0, 0)   # RIGHTUP
        for _ in range(20):
            time.sleep(0.15)
            ws = find_windows("#32768")
            if ws:
                menu_hwnd = ws[0]
                break
        u32.SetWindowPos(hwnd, ctypes.c_void_p(-2), 0, 0, 0, 0, SWP)

    if not menu_hwnd:
        print("  [FAIL] 两条路线都没能弹出菜单（前台/输入注入被系统限制，属测试环境问题）")
        u32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        return 1
    print(f"  [OK]   菜单窗口 {menu_hwnd}")

    hmenu = u32.SendMessageW(menu_hwnd, MN_GETHMENU, 0, 0)
    if not hmenu:
        print("  [FAIL] MN_GETHMENU 拿不到 HMENU")
        u32.PostMessageW(menu_hwnd, WM_CLOSE, 0, 0)
        u32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        return 1

    n = u32.GetMenuItemCount(hmenu)
    print(f"\n[4] 菜单共 {n} 项，清单：")
    hit_idx = -1
    for i in range(n):
        buf = ctypes.create_unicode_buffer(260)
        u32.GetMenuStringW(hmenu, i, buf, 260, MF_BYPOSITION)
        name = buf.value.replace("&", "")
        is_pop = bool(u32.GetMenuState(hmenu, i, MF_BYPOSITION) & MF_POPUP)
        mark = " ▶(级联)" if is_pop else ""
        print(f"    {i:2d}. {name}{mark}")
        if "转换文件格式" in name:
            hit_idx = i

    print()
    if hit_idx < 0:
        print("  [FAIL] 菜单里没有【转换文件格式】")
        u32.PostMessageW(menu_hwnd, WM_CLOSE, 0, 0)
        u32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        return 1
    print(f"  [OK]   找到【转换文件格式】在第 {hit_idx} 项")

    is_pop = bool(u32.GetMenuState(hmenu, hit_idx, MF_BYPOSITION) & MF_POPUP)
    if not is_pop:
        print("  [FAIL] 它不是一个级联 popup（说明只插了个普通菜单项）")
        u32.PostMessageW(menu_hwnd, WM_CLOSE, 0, 0)
        u32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        return 1
    print("  [OK]   它确实是带箭头的级联 popup")

    sub = u32.GetSubMenu(hmenu, hit_idx)
    nsub = u32.GetMenuItemCount(sub)
    print(f"\n[5] 展开子菜单，共 {nsub} 项：")
    # ⚠️ 命令 ID 由 shell 统一分配（idCmdFirst 不是 1），只能校验"连续递增"
    base = u32.GetMenuItemID(sub, 0) if nsub else -1
    expected = expected_labels(Path(__file__).resolve().parents[1])
    ok_count = 0
    for i in range(nsub):
        buf = ctypes.create_unicode_buffer(260)
        u32.GetMenuStringW(sub, i, buf, 260, MF_BYPOSITION)
        mid = u32.GetMenuItemID(sub, i)
        id_ok = (mid == base + i) and base > 0
        lbl_ok = (i < len(expected)) and (buf.value.replace("&", "") == expected[i])
        good = id_ok and lbl_ok
        ok_count += 1 if good else 0
        print(f"    {'[OK]' if good else '[??]'} id={mid:<6} {buf.value}")
    print(f"\n  idCmdFirst = {base}（由 shell 分配，非固定 1）")
    print(f"  子项合格：{ok_count}/{nsub}")

    # --- 5.5 端到端：在真实菜单里"点"一个子项，看是否真的拉起转换 ---------
    # 这是验证 InvokeCommand 收到的到底是"相对 idCmdFirst 的偏移"还是"绝对 ID"
    # 的唯一可靠手段 —— 搞反了就会表现为"点了没反应"。
    print("\n[5.5] 模拟点击子项（Word 转 TXT），检查是否真拉起转换")
    import os

    os.environ["FILECONV_SILENT"] = "1"          # 子进程继承：不弹窗
    os.environ["FILECONV_NO_CONSOLE"] = "1"
    probe = expected_verbs(Path(__file__).resolve().parents[1])[3][0]   # docx2txt
    before = running_cmds()

    # ⚠️ 不能 PostMessage(WM_COMMAND) 给菜单窗口：菜单内部是把命令发给
    #    「所有者窗口」的，打给 #32768 本身会被忽略 —— 那样会误判成"点了没反应"。
    #    正确做法是走真实鼠标：先悬停展开级联，再点子项。
    rect = wintypes.RECT()
    u32.GetMenuItemRect.argtypes = [wintypes.HWND, wintypes.HMENU,
                                    ctypes.c_uint, ctypes.POINTER(wintypes.RECT)]
    u32.GetMenuItemRect.restype = wintypes.BOOL
    if not u32.GetMenuItemRect(menu_hwnd, hmenu, hit_idx, ctypes.byref(rect)):
        print("  [FAIL] GetMenuItemRect 取不到级联项坐标")
        FAILS.append("取不到菜单项坐标")
    else:
        u32.SetCursorPos((rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2)
        time.sleep(1.0)                          # 等鼠标悬停把级联展开
        r2 = wintypes.RECT()
        if not u32.GetMenuItemRect(menu_hwnd, sub, 3, ctypes.byref(r2)):
            print("  [FAIL] 取不到子项坐标")
            FAILS.append("取不到子项坐标")
        else:
            print(f"  悬停展开级联 → 点击第 4 项（期望触发 {probe}）")
            u32.SetCursorPos((r2.left + r2.right) // 2, (r2.top + r2.bottom) // 2)
            time.sleep(0.3)
            u32.mouse_event(0x0002, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTDOWN
            time.sleep(0.05)
            u32.mouse_event(0x0004, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTUP

    spawned: list[str] = []
    for _ in range(16):
        time.sleep(0.25)
        spawned = [c for c in running_cmds() if c not in before]
        if spawned:
            break
    if spawned:
        print(f"  [OK] 拉起进程：{spawned[0]}")
        if f"runm {probe}" in spawned[0]:
            print(f"  [OK] 命令行为 runm {probe} —— 偏移换算正确")
        else:
            print(f"  [FAIL] 命令行不对，InvokeCommand 的 ID 换算可能反了：{spawned[0]}")
            FAILS.append("InvokeCommand id 换算错误")
    else:
        print("  [FAIL] 点了没反应（InvokeCommand 没拉起进程）")
        FAILS.append("点击子项无响应")

    print("\n[6] 收尾：关掉菜单与窗口")
    u32.PostMessageW(menu_hwnd, WM_CLOSE, 0, 0)
    time.sleep(0.3)
    u32.PostMessageW(hwnd, WM_CLOSE, 0, 0)

    print("\n" + "=" * 60)
    ok_all = (nsub == 17 and ok_count == 17 and not FAILS)
    if ok_all:
        print("结果：✔ 级联子菜单在真实右键里渲染成功，点击也能正确触发（17/17）")
        return 0
    print(f"结果：✘ 有问题（子项 {ok_count}/{nsub}，其他：{FAILS or '无'}）")
    return 1


if __name__ == "__main__":
    sys.exit(main())
