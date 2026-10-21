# -*- coding: utf-8 -*-
"""实验：HKCU 的 CommandStore + 显式 SubCommands 列表，能否被 shell 正确解析。"""
import io
import os
import subprocess
import sys
import winreg

HIVE = winreg.HKEY_CURRENT_USER
CS = r"Software\Microsoft\Windows\CurrentVersion\Explorer\CommandStore\shell"
EXE = os.path.join(os.environ["LOCALAPPDATA"], "Programs", "FileConverter", "FileConverter.exe")


def setv(key, name, val):
    with winreg.CreateKeyEx(HIVE, key, 0, winreg.KEY_ALL_ACCESS) as h:
        winreg.SetValueEx(h, name, 0, winreg.REG_SZ, val)


def main() -> int:
    # 1) 两个条目写进 CommandStore
    for verb, label in (("img2png", "图片 → PNG"), ("img2jpg", "图片 → JPG")):
        base = f"{CS}\\FileConv.{verb}"
        setv(base, "MUIVerb", label)
        setv(base, "Icon", f'"{EXE}",0')
        setv(base + r"\command", "", f'"{EXE}" run {verb} "%1"')

    # 2) 父项用显式列表
    parent = r"Software\Classes\*\shell\FileConv"
    setv(parent, "MUIVerb", "转换文件格式")
    setv(parent, "Icon", f'"{EXE}",0')
    setv(parent, "Position", "Top")
    setv(parent, "SubCommands", "FileConv.img2png;FileConv.img2jpg")

    print("已写入 CommandStore + SubCommands 列表，开始枚举…\n")
    r = subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "probe_menu.py")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = r.stdout or ""
    idx = out.find("转换文件格式")
    print(out[max(0, idx - 60): idx + 300] if idx >= 0 else out[-800:])
    return 0


if __name__ == "__main__":
    sys.exit(main())
