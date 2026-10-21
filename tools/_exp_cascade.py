# -*- coding: utf-8 -*-
"""受控实验：最小级联菜单，验证本机到底支持哪种写法。

建 3 个候选：
  FCtest1: 父键 SubCommands=""       + 子项在父键 shell\\ 下
  FCtest2: 父键 SubCommands 显式列表  + 子项在 HKCU CommandStore
  FCtest3: 父键 ExtendedSubCommandsKey + 子项在 HKCU\\Software\\Classes\\FCStore\\shell\\
然后用 probe 枚举，看哪个能出子项。
"""
import os
import subprocess
import sys
import winreg

HIVE = winreg.HKEY_CURRENT_USER
EXE = os.path.join(os.environ["LOCALAPPDATA"], "Programs", "FileConverter", "FileConverter.exe")
CS = r"Software\Microsoft\Windows\CurrentVersion\Explorer\CommandStore\shell"


def setv(key, name, val):
    with winreg.CreateKeyEx(HIVE, key, 0, winreg.KEY_ALL_ACCESS) as h:
        winreg.SetValueEx(h, name, 0, winreg.REG_SZ, val)


def deltree(key):
    try:
        with winreg.OpenKey(HIVE, key, 0, winreg.KEY_ALL_ACCESS) as h:
            while True:
                try:
                    sub = winreg.EnumKey(h, 0)
                except OSError:
                    break
                deltree(key + "\\" + sub)
        winreg.DeleteKey(HIVE, key)
    except OSError:
        pass


def main() -> int:
    for k in (r"Software\Classes\*\shell\FCtest1", r"Software\Classes\*\shell\FCtest2",
              r"Software\Classes\*\shell\FCtest3", r"Software\Classes\FCStore",
              f"{CS}\\FCt.algo1", f"{CS}\\FCt.algo2"):
        deltree(k)

    # --- 候选 1：SubCommands="" + 父键 shell 子键 ---
    p1 = r"Software\Classes\*\shell\FCtest1"
    setv(p1, "MUIVerb", "测试1-空SubCommands")
    setv(p1, "SubCommands", "")
    for n, lbl in (("a", "子项A"), ("b", "子项B")):
        base = f"{p1}\\shell\\{n}"
        setv(base, "MUIVerb", lbl)
        setv(base + r"\command", "", f'"{EXE}" util about "%1"')

    # --- 候选 2：SubCommands 显式列表 + HKCU CommandStore ---
    for n, lbl in (("FCt.algo1", "算法一"), ("FCt.algo2", "算法二")):
        setv(f"{CS}\\{n}", "MUIVerb", lbl)
        setv(f"{CS}\\{n}\\command", "", f'"{EXE}" util about "%1"')
    p2 = r"Software\Classes\*\shell\FCtest2"
    setv(p2, "MUIVerb", "测试2-CommandStore")
    setv(p2, "SubCommands", "FCt.algo1;FCt.algo2")

    # --- 候选 3：ExtendedSubCommandsKey ---
    for n, lbl in (("c", "选项C"), ("d", "选项D")):
        base = f"Software\\Classes\\FCStore\\shell\\{n}"
        setv(base, "MUIVerb", lbl)
        setv(base + r"\command", "", f'"{EXE}" util about "%1"')
    p3 = r"Software\Classes\*\shell\FCtest3"
    setv(p3, "MUIVerb", "测试3-ExtendedSubCommandsKey")
    setv(p3, "ExtendedSubCommandsKey", "FCStore")

    print("三个候选已写入，开始枚举…\n")
    r = subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "probe_menu.py")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = r.stdout or ""
    for line in out.split("\n"):
        if "测试" in line or (line.strip().startswith("·") and line.strip() != "·"):
            print(line)
        elif "子项" in line and "个" in line:
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
