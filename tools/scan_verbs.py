# -*- coding: utf-8 -*-
"""扫描文件右键菜单上的「静态菜单动词」（*\\shell\\<verb>），补齐 scan_handlers.py 的盲区。

ContextMenuHandlers 扫不到的一类就是它们 —— Bandizip、QQ、WPS 视频等都是走这条路。
只读，不改任何东西。
"""
import winreg

ROOTS = [
    (winreg.HKEY_CLASSES_ROOT, r"*\shell"),
    (winreg.HKEY_CLASSES_ROOT, r"AllFilesystemObjects\shell"),
    (winreg.HKEY_CLASSES_ROOT, r"Directory\shell"),
    (winreg.HKEY_CLASSES_ROOT, r"Directory\Background\shell"),
]

SYS_DLLS = ("shell32", "shlwapi", "ntshrui", "cscui", "imageres", "shellfolder")
SYS_BIN = r"system32"
SYS_EXE = ("explorer.exe", "open", "print")


def read(hive, path, name=""):
    try:
        with winreg.OpenKey(hive, path) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return None


def enum_keys(hive, path):
    out = []
    try:
        with winreg.OpenKey(hive, path) as k:
            i = 0
            while True:
                try:
                    out.append(winreg.EnumKey(k, i))
                    i += 1
                except OSError:
                    break
    except OSError:
        pass
    return out


def is_system_ish(cmd: str) -> bool:
    c = (cmd or "").lower()
    if any(s in c for s in SYS_DLLS) or SYS_BIN in c:
        return True
    if c.startswith("shell:") or "windows\\" in c:
        return True
    return False


print("=" * 104)
print("静态菜单动词（shell\\<verb>）—— 标了 [第三方] 的是非系统项")
print("=" * 104)

rows = []
for hive, base in ROOTS:
    for verb in enum_keys(hive, base):
        label = read(hive, rf"{base}\{verb}") or read(hive, rf"{base}\{verb}", "MUIVerb") or ""
        cmd = read(hive, rf"{base}\{verb}\command") or ""
        third = not is_system_ish(cmd)
        if not (third or label):
            continue
        rows.append((base, verb, label, cmd, third))

seen = set()
n = 0
for base, verb, label, cmd, third in sorted(rows):
    if (base, verb) in seen:
        continue
    seen.add((base, verb))
    n += 1
    tag = " [第三方]" if third else ""
    print(f"\n{n:2d}. {verb}{tag}")
    print(f"    位置   : {base}\\shell")
    print(f"    显示   : {label or '(取默认)'}")
    if cmd:
        print(f"    命令   : {cmd[:150]}")

print("\n" + "=" * 104)
print(f"共 {n} 个静态动词")