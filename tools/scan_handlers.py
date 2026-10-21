# -*- coding: utf-8 -*-
"""扫描所有注册在文件右键菜单上的第三方外壳扩展，用于生成"精简菜单"的禁用清单。

只读，不改任何东西。

扫描位置（HKCR 合并视图，用户级优先）：
    *\\shellex\\ContextMenuHandlers
    AllFilesystemObjects\\shellex\\ContextMenuHandlers
    Directory\\shellex\\ContextMenuHandlers

对每个 CLSID 输出：显示名 / DLL 路径 / DLL 的公司名 / 产品名，用来判断是谁家的。
"""
import winreg
from pathlib import Path

TARGETS = [
    (winreg.HKEY_CLASSES_ROOT, r"*\shellex\ContextMenuHandlers"),
    (winreg.HKEY_CLASSES_ROOT, r"AllFilesystemObjects\shellex\ContextMenuHandlers"),
    (winreg.HKEY_CLASSES_ROOT, r"Directory\shellex\ContextMenuHandlers"),
    (winreg.HKEY_CLASSES_ROOT, r"Directory\Background\shellex\ContextMenuHandlers"),
]

# 用户级覆盖层里已存在的（HKCU 下自己建的），不受系统级影响
USER_CLSID = r"Software\Classes\CLSID"


def read(hive, path, name=""):
    try:
        with winreg.OpenKey(hive, path) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return None


def enum_sub(hive, path):
    out = []
    try:
        with winreg.OpenKey(hive, path) as k:
            i = 0
            while True:
                try:
                    out.append((winreg.EnumKey(k, i), read(k, out[-1][1] if False else "")))
                    i += 1
                except OSError:
                    break
    except OSError:
        pass
    return out


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


def dll_info(path):
    """取 DLL 的版本信息（公司/产品），失败返回空串。"""
    if not path:
        return "", ""
    p = Path(str(path).strip('"'))
    if not p.is_file():
        return "", ""
    try:
        import win32api
        info = win32api.GetFileVersionInfo(str(p), "\\")
        ms, ls = info
        def get(k):
            try:
                import win32api
                f = win32api.GetFileVersionInfo(str(p), "\\VarFileInfo\\Translation")
                t = f[0]
                return win32api.GetFileVersionInfo(str(p),
                        f"\\StringFileInfo\\{t:04x}{ls:04x}\\{k}")
            except Exception:
                return ""
        return get("CompanyName"), get("ProductName")
    except Exception:
        return "", ""


print("=" * 100)
print("文件右键菜单上的第三方外壳扩展（shellex\\ContextMenuHandlers）")
print("=" * 100)

seen = {}
for hive, base in TARGETS:
    for name in enum_keys(hive, base):
        clsid = read(hive, rf"{base}\{name}")
        if not clsid:
            continue
        key = (name, str(clsid).upper())
        if key in seen:
            continue
        friendly = read(winreg.HKEY_CLASSES_ROOT, rf"CLSID\{clsid}") or ""
        insproc = read(winreg.HKEY_CLASSES_ROOT, rf"CLSID\{clsid}\InprocServer32") or ""
        user_defined = winreg.HKEY_CURRENT_USER, rf"{USER_CLSID}\{clsid}"
        try:
            with winreg.OpenKey(*user_defined):
                in_hkcu = True
        except OSError:
            in_hkcu = False
        legacy = read(winreg.HKEY_CURRENT_USER, rf"{USER_CLSID}\{clsid}\LegacyDisable")
        company, product = dll_info(insproc)
        seen[key] = dict(name=name, clsid=clsid, friendly=friendly,
                         dll=insproc, company=company, product=product,
                         hkcu=in_hkcu, disabled=legacy is not None, base=base)

for i, (k, v) in enumerate(sorted(seen.items(), key=lambda x: x[1]["name"]), 1):
    flag = " [HKCU自建]" if v["hkcu"] else ""
    dis = "  [已禁用]" if v["disabled"] else ""
    print(f"\n{i:2d}. 注册名: {v['name']}{flag}{dis}")
    print(f"    CLSID  : {v['clsid']}")
    print(f"    位置   : {v['base']}")
    print(f"    名称   : {v['friendly']}")
    print(f"    DLL    : {v['dll']}")
    if v["company"] or v["product"]:
        print(f"    厂商   : {v['company']}  |  产品: {v['product']}")

print("\n" + "=" * 100)
print(f"共 {len(seen)} 个扩展")