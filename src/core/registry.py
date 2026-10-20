# -*- coding: utf-8 -*-
"""右键菜单注册表读写（HKCU，普通用户权限即可，不需要管理员）。

Windows 10 / 11 都支持的级联写法：
    HKCU\\Software\\Classes\\*\\shell\\FileConv            ← 父菜单
        MUIVerb      = 转换文件格式
        SubCommands  = FileConv.pdf2docx;FileConv.docx2pdf;...
    HKCU\\Software\\...\\Explorer\\CommandStore\\shell\\FileConv.<verb>\\command
                                                          ← 子菜单项
"""

from __future__ import annotations

import os
import sys
import winreg
from pathlib import Path

HIVE = winreg.HKEY_CURRENT_USER
PARENT_KEY = r"Software\Classes\*\shell\FileConv"
CMD_STORE = r"Software\Microsoft\Windows\CurrentVersion\Explorer\CommandStore\shell"
VERB_PREFIX = "FileConv."
MENU_NAME = "转换文件格式"
PROG_ID = "XuTools.FileConverter"

from .tasks import SPECS, UTILS, VERB_ORDER  # noqa: E402


# -------------------------------------------------------------------------- #
def _parts() -> list[str]:
    """生成命令行片段。打包后是单个 exe，源码模式则是 pythonw + converter.py。"""
    if getattr(sys, "frozen", False):
        return [f'"{sys.executable}"']
    src = Path(__file__).resolve().parent.parent          # src/core -> src
    script = src / "converter.py"
    pyw = Path(sys.executable).with_name("pythonw.exe")
    py = Path(sys.executable) if not pyw.exists() else pyw
    return [f'"{py}"', f'"{script}"']


def launcher() -> str:
    return " ".join(_parts())


def exe_path() -> str:
    if getattr(sys, "frozen", False):
        return sys.executable
    return str(Path(__file__).resolve().parent.parent / "converter.py")


def menu_items() -> list[tuple[str, str, str]]:
    """[(子菜单项内部名, 显示文字, 命令行)] —— 顺序即菜单顺序。"""
    parts = _parts()
    items: list[tuple[str, str, str]] = []
    for verb in VERB_ORDER:
        spec = SPECS[verb]
        cmd = " ".join([*parts, "run", verb, '"%1"'])
        items.append((VERB_PREFIX + verb, spec["label"], cmd))
    for name, label in UTILS.items():
        # 传 %1 只是为了把"文件夹选择框"定位到当前文件所在目录
        cmd = " ".join([*parts, "util", name, '"%1"'])
        items.append((VERB_PREFIX + name, label, cmd))
    return items


# -------------------------------------------------------------------------- #
def _delete_tree(hive: int, key: str) -> None:
    try:
        h = winreg.OpenKey(hive, key, 0, winreg.KEY_ALL_ACCESS)
    except FileNotFoundError:
        return
    while True:
        try:
            sub = winreg.EnumKey(h, 0)
        except OSError:
            break
        _delete_tree(hive, f"{key}\\{sub}")
    winreg.CloseKey(h)
    try:
        winreg.DeleteKey(hive, key)
    except OSError:
        pass


def _set_str(hive: int, key: str, name: str, value: str) -> None:
    with winreg.CreateKeyEx(hive, key, 0, winreg.KEY_SET_VALUE) as h:
        winreg.SetValueEx(h, name, 0, winreg.REG_SZ, value)


def _del_value(hive: int, key: str, name: str) -> None:
    try:
        with winreg.OpenKey(hive, key, 0, winreg.KEY_SET_VALUE) as h:
            winreg.DeleteValue(h, name)
    except OSError:
        pass


def install(lean: bool = False) -> dict:
    """写入右键菜单（HKCU，普通用户即可）。

    ⚠️ 实测结论（Windows 11 build 26200 上逐一验证过，见 src/selftest 的注册表用例）：
        - 父项 **不能写 SubCommands**（哪怕写成空字符串 ""）——写了整项就不显示；
        - 正确写法是：父项只写 MUIVerb + Icon，子项写在父项的 `shell\\<动词>\\command` 下，
          Explorer 会自动把它渲染成带箭头的级联菜单。
        - 把 SubCommands 写成"分号清单"更不行：那要求条目在 HKLM 的 CommandStore 里，
          HKCU 下解析不到，整个菜单项直接消失（这就是第一版完全不显示的原因）。
    """
    icon = exe_path()
    items = menu_items()

    # 1) 子菜单项：挂在父键的 shell 下
    for name, label, cmd in items:
        base = f"{PARENT_KEY}\\shell\\{name}"
        _set_str(HIVE, base, "", label)
        _set_str(HIVE, base, "Icon", f'"{icon}",0')
        _set_str(HIVE, base + r"\command", "", cmd)

    # 2) 父菜单：MUIVerb + Icon，绝不能有 SubCommands
    _set_str(HIVE, PARENT_KEY, "", MENU_NAME)
    _set_str(HIVE, PARENT_KEY, "MUIVerb", MENU_NAME)
    _set_str(HIVE, PARENT_KEY, "Icon", f'"{icon}",0')
    _del_value(HIVE, PARENT_KEY, "SubCommands")   # 兼容旧版残留，必须删掉
    _del_value(HIVE, PARENT_KEY, "Extended")

    return {"items": len(items), "target": launcher()}


def uninstall(remove_config: bool = False) -> dict:
    removed = {"menu": False, "verbs": 0}

    if key_exists(PARENT_KEY):
        _delete_tree(HIVE, PARENT_KEY)
        removed["menu"] = True

    for name, _, _ in menu_items():
        base = f"{CMD_STORE}\\{name}"
        if key_exists(base):
            _delete_tree(HIVE, base)
            removed["verbs"] += 1

    from . import collector

    collector.reset_all()

    if remove_config:
        from .config import app_dir

        try:
            import shutil as _sh

            _sh.rmtree(app_dir(), ignore_errors=True)
            removed["config"] = True  # type: ignore[assignment]
        except Exception:
            pass
    return removed


def key_exists(key: str) -> bool:
    try:
        winreg.CloseKey(winreg.OpenKey(HIVE, key))
        return True
    except OSError:
        return False


def _has_value(key: str, name: str) -> bool:
    try:
        with winreg.OpenKey(HIVE, key) as h:
            winreg.QueryValueEx(h, name)
        return True
    except OSError:
        return False


# -------------------------------------------------------------------------- #
# Windows 11「一级菜单」
#
# Win11 的紧凑右键菜单只认 IExplorerCommand 的 COM 外壳扩展（需要编译一个 DLL），
# 纯注册表做不到。所以这里用官方保留的开关：把右键菜单切回 Win10 那套完整菜单，
# 这样静态菜单项（本工具）就直接出现在一级菜单里。完全可逆。
# -------------------------------------------------------------------------- #
CLASSIC_CLSID = "{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}"
CLASSIC_KEY = rf"Software\Classes\CLSID\{CLASSIC_CLSID}\InprocServer32"


def set_classic_menu(enable: bool) -> bool:
    """开/关"经典完整右键菜单"。返回当前状态。"""
    if enable:
        _set_str(HIVE, CLASSIC_KEY, "", "")       # 空值 = 启用经典菜单
    else:
        _delete_tree(HIVE, rf"Software\Classes\CLSID\{CLASSIC_CLSID}")
    return classic_menu_on()


def classic_menu_on() -> bool:
    return key_exists(CLASSIC_KEY)


def is_installed() -> bool:
    return key_exists(PARENT_KEY)


def notify_explorer() -> None:
    """让资源管理器立刻重读菜单缓存（不重启 explorer 也能生效）。"""
    try:
        import ctypes

        SHCNE_ASSOCCHANGED = 0x08000000
        SHCNF_IDLIST = 0x0000
        SHCNF_FLUSH = 0x1000
        ctypes.windll.shell32.SHChangeNotify(
            SHCNE_ASSOCCHANGED, SHCNF_IDLIST | SHCNF_FLUSH, None, None
        )
    except Exception:
        pass
    try:
        import ctypes

        WM_SETTINGCHANGE = 0x001A
        ctypes.windll.user32.SendMessageTimeoutW(
            0xFFFF, WM_SETTINGCHANGE, 0, "Environment", 0x0002, 2000, None
        )
    except Exception:
        pass
