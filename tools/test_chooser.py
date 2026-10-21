# -*- coding: utf-8 -*-
"""验证原生选择框能否真的弹出来（不点，只看窗口是否出现）。"""
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable

code = ("import sys; sys.path.insert(0, r'%s\\src'); "
        "from core import winui; "
        "print('RET', winui.choose_one('测试指令', '测试内容', ['选项A', '选项B', '选项C']), flush=True)"
        % ROOT)

p = subprocess.Popen([PY, "-c", code], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                     text=True)
time.sleep(2.5)

found = []


@ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
def cb(hwnd, _):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, buf, 256)
    if buf.value == "转换文件格式" and user32.IsWindowVisible(hwnd):
        found.append(hwnd)
    return True


user32.EnumWindows(cb, 0)
print("找到对话框窗口:", len(found), "个")
if found:
    print("[OK] 原生选择框能正常弹出")
    # 点“取消”关闭：发送 WM_CLOSE
    for h in found:
        user32.PostMessageW(h, 0x0010, 0, 0)
    time.sleep(1)
else:
    print("[FAIL] 没看到对话框")

try:
    out = p.communicate(timeout=8)[0]
except subprocess.TimeoutExpired:
    p.kill()
    out = p.communicate()[0]
print("子进程输出:", (out or "").strip()[:200])
sys.exit(0 if found else 1)
