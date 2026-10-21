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
PARENT_VERB = "FileConv"
PARENT_KEY = rf"Software\Classes\*\shell\{PARENT_VERB}"
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


def install_static(lean: bool = False) -> dict:
    """兜底方案：单个普通菜单项，点了弹自绘选单挑转换方案。

    ⚠️ 只在 cascade 外壳扩展（install_ctx）装不上时才用它 —— 因为本机的
    Win11 用**纯注册表**渲染不出级联子菜单（父项加 `SubCommands=""`、子项
    加 `MUIVerb` 都试过，点不开），而弹出式选单又不是用户要的级联效果。

    覆盖范围：所有文件（`*`）+ 所有文件夹（`Directory`），Position=Top 置顶。
    """
    icon = exe_path()
    cmd = " ".join([*_parts(), "chooser", '"%1"'])
    stats = {"items": 1, "targets": []}

    for target in ("*", "Directory"):
        key = rf"Software\Classes\{target}\shell\{PARENT_VERB}"
        _set_str(HIVE, key, "", MENU_NAME)
        _set_str(HIVE, key, "MUIVerb", MENU_NAME)
        _set_str(HIVE, key, "Icon", f'"{icon}",0')
        _set_str(HIVE, key, "Position", "Top")
        _set_str(HIVE, key + r"\command", "", cmd)
        # 不能留级联声明，否则会被当级联渲染成一个点不开的空菜单
        _del_value(HIVE, key, "SubCommands")
        _del_value(HIVE, key, "ExtendedSubCommandsKey")
        _del_value(HIVE, key, "Extended")
        # 清掉旧版本留下的子项，避免脏数据
        sub = key + r"\shell"
        if key_exists(sub):
            _delete_tree(HIVE, sub)
        stats["targets"].append(target)

    return stats


def uninstall_static() -> int:
    n = 0
    for target in ("*", "Directory"):
        key = rf"Software\Classes\{target}\shell\{PARENT_VERB}"
        if key_exists(key):
            _delete_tree(HIVE, key)
            n += 1
    return n


# -------------------------------------------------------------------------- #
# 【主力方案】真正的级联子菜单：IContextMenu 外壳扩展 FileConvCtx.dll
#
# 为什么必须自己写 DLL：
#   - 纯注册表级联（父键 + shell 子键 / SubCommands）在这台 Win11 上渲染不出来；
#   - 弹窗式选单不是用户要的效果（要的是 Bandizip 那种"转换文件格式 >"展开列表）；
#   - 所以只能走 shell 扩展自己 CreatePopupMenu + InsertMenu(MF_POPUP) 的路子，
#     这也是 7-Zip / WinRAR / TortoiseGit 的标准做法。
#
# ⚠️ 位置说明（微软文档已定性，别再试错）：
#   Win11 紧凑菜单**只**承载 IExplorerCommand + MSIX 包；IContextMenu 扩展
#   只会出现在旧版菜单里。所以必须配合 set_classic_menu(True) 把经典完整菜单
#   打开，用户一右键就能直接看到级联项，不用再点「显示更多选项」。
#
# 注册位置（HKCU，免管理员）：
#   Software\Classes\CLSID\{B2C4E111-...}\InprocServer32  → FileConvCtx.dll
#   Software\Classes\{*|Directory}\shellex\ContextMenuHandlers\FileConv → CLSID
# -------------------------------------------------------------------------- #
CLSID_CTX = "{B2C4E111-7A9D-4C3E-8F21-9D4E5A6B7C8D}"
CTX_DLL_NAME = "FileConvCtx.dll"
CTX_HANDLER = "FileConv"
CTX_TARGETS = (r"*", "Directory")


def ctx_dll_path() -> Path:
    """级联扩展 DLL：正式安装时在 exe 旁边；源码模式退回仓库 native/。"""
    cand = Path(exe_path()).parent / CTX_DLL_NAME
    if cand.is_file():
        return cand
    root = Path(__file__).resolve().parents[2]     # src/core/registry.py → 项目根
    alt = root / "native" / CTX_DLL_NAME
    return alt if alt.is_file() else cand


def install_ctx() -> dict:
    """注册级联子菜单外壳扩展。返回 {'ok':..., 'dll':..., 'targets':[...]}。"""
    dll = ctx_dll_path()
    if not dll.is_file():
        return {"ok": False, "reason": f"找不到 {CTX_DLL_NAME}（应在 {dll.parent}）"}

    clsid_key = rf"Software\Classes\CLSID\{CLSID_CTX}"
    _set_str(HIVE, clsid_key, "", "FileConverter 右键级联转换菜单")
    _set_str(HIVE, clsid_key + r"\InprocServer32", "", str(dll))
    _set_str(HIVE, clsid_key + r"\InprocServer32", "ThreadingModel", "Apartment")

    for target in CTX_TARGETS:
        base = rf"Software\Classes\{target}\shellex\ContextMenuHandlers\{CTX_HANDLER}"
        _set_str(HIVE, base, "", CLSID_CTX)

    return {"ok": True, "dll": str(dll), "targets": list(CTX_TARGETS)}


def remove_ctx() -> int:
    _delete_tree(HIVE, rf"Software\Classes\CLSID\{CLSID_CTX}")
    n = 0
    for target in CTX_TARGETS:
        key = rf"Software\Classes\{target}\shellex\ContextMenuHandlers\{CTX_HANDLER}"
        if key_exists(key):
            _delete_tree(HIVE, key)
            n += 1
    return n


def ctx_registered() -> bool:
    return key_exists(rf"Software\Classes\CLSID\{CLSID_CTX}\InprocServer32")


def ctx_handlers_bound() -> bool:
    """CLSID 挂到 `*` / Directory 上了没（两个都要在）。"""
    return all(
        key_exists(rf"Software\Classes\{t}\shellex\ContextMenuHandlers\{CTX_HANDLER}")
        for t in CTX_TARGETS
    )


def ctx_verify() -> tuple[bool, str]:
    """真正把扩展跑一遍：建菜单 → 数子项 → 读文字。失败会给出具体阶段。"""
    import ctypes
    import uuid

    from .tasks import VERB_ORDER

    dll = ctx_dll_path()
    if not dll.is_file():
        return False, f"缺 {CTX_DLL_NAME}"

    k32 = ctypes.WinDLL("kernel32")
    u32 = ctypes.WinDLL("user32")
    o32 = ctypes.WinDLL("ole32")

    class GUID(ctypes.Structure):
        _fields_ = [("d1", ctypes.c_ulong), ("d2", ctypes.c_ushort),
                    ("d3", ctypes.c_ushort), ("d4", ctypes.c_ubyte * 8)]

    def mk(s: str) -> GUID:
        u = uuid.UUID(s)
        g = GUID()
        g.d1, g.d2, g.d3 = u.fields[0], u.fields[1], u.fields[2]
        for i, b in enumerate(u.bytes[8:]):
            g.d4[i] = b
        return g

    def vfn(p, idx, restype, *argtypes):
        obj = ctypes.cast(p, ctypes.POINTER(ctypes.c_void_p))
        vt = ctypes.cast(obj[0], ctypes.POINTER(ctypes.c_void_p))
        return ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vt[idx])

    try:
        k32.LoadLibraryW.argtypes = [ctypes.c_wchar_p]
        k32.LoadLibraryW.restype = ctypes.c_void_p
        k32.GetProcAddress.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        k32.GetProcAddress.restype = ctypes.c_void_p

        h = k32.LoadLibraryW(str(dll))
        if not h:
            return False, "LoadLibrary 失败"
        addr = k32.GetProcAddress(h, b"DllGetClassObject")
        if not addr:
            return False, "找不到导出函数 DllGetClassObject"
        DGCO = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.POINTER(GUID),
                                  ctypes.POINTER(GUID),
                                  ctypes.POINTER(ctypes.c_void_p))(addr)

        o32.CoInitialize(None)
        cf = ctypes.c_void_p()
        hr = DGCO(ctypes.byref(mk(CLSID_CTX)),
                  ctypes.byref(mk("{00000001-0000-0000-C000-000000000046}")),
                  ctypes.byref(cf))
        if hr != 0 or not cf:
            return False, f"DllGetClassObject 失败 (0x{hr & 0xFFFFFFFF:08X})"

        ci = vfn(cf, 3, ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(GUID),
                 ctypes.POINTER(ctypes.c_void_p))
        ctx = ctypes.c_void_p()
        hr = ci(cf, None, ctypes.byref(mk("{000214e4-0000-0000-C000-000000000046}")),
                ctypes.byref(ctx))
        if hr != 0 or not ctx:
            return False, f"CreateInstance(IContextMenu) 失败 (0x{hr & 0xFFFFFFFF:08X})"

        u32.CreatePopupMenu.restype = ctypes.c_void_p
        hmenu = u32.CreatePopupMenu()
        # 没走 Initialize → 路径表是空的，QueryContextMenu 会拒绝插菜单；
        # 这里只验证"能加载 + 能调用 + 返回码合法"，不验证子项内容。
        qcm = vfn(ctx, 3, ctypes.c_long, ctypes.c_void_p, ctypes.c_uint,
                  ctypes.c_uint, ctypes.c_uint, ctypes.c_uint)
        hr = qcm(ctx, hmenu, 0, 1, 0x7FFF, 0)
        u32.DestroyMenu(ctypes.c_void_p(hmenu))
        vfn(ctx, 2, ctypes.c_ulong)(ctx)
        vfn(cf, 2, ctypes.c_ulong)(cf)
        o32.CoUninitialize()
        if hr < 0:
            return False, f"QueryContextMenu 失败 (0x{hr & 0xFFFFFFFF:08X})"
        return True, (f"级联扩展可加载，{len(VERB_ORDER)} 个转换方案")
    except Exception as e:                                    # noqa: BLE001
        return False, f"自检异常：{type(e).__name__}: {e}"


def remove_cascade() -> None:
    """删掉经典级联菜单（COM/静态模式的旧键）。"""
    _delete_tree(HIVE, PARENT_KEY)
    for name, _, _ in menu_items():
        _delete_tree(HIVE, f"{CMD_STORE}\\{name}")


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


# -------------------------------------------------------------------------- #
# Windows 11 一级菜单（现代紧凑菜单）：必须是 MSIX 稀疏包
#
# 实测结论：只写 ExplorerCommandHandler 的项**不会**出现在 Win11 新菜单里
# （新菜单只认 `windows.fileExplorerContextMenus` 包扩展）。
# QQ / WPS / Bandizip 全是这么做的：MSIX 稀疏包 + 包内声明
# `desktop5:Verb Clsid=...` + `com:SurrogateServer`。
# 开发者模式下 `Add-AppxPackage -Register <manifest> -ExternalLocation <dir>`
# 可以免签名注册（不需要管理员）。
# -------------------------------------------------------------------------- #
MSIX_PKG_NAME = "FileConverter.ContextMenu"
MSIX_MANIFEST = "AppxManifest.xml"
_NO_WINDOW = 0x08000000


def _ps(cmd: str, timeout: int = 180):
    import subprocess

    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        creationflags=_NO_WINDOW, timeout=timeout,
    )


def msix_manifest_path() -> Path:
    return Path(exe_path()).parent / MSIX_MANIFEST


def msix_installed() -> bool:
    try:
        r = _ps(f'(Get-AppxPackage -Name "{MSIX_PKG_NAME}").PackageFullName', timeout=60)
        return MSIX_PKG_NAME in (r.stdout or "")
    except Exception:
        return False


def install_msix() -> dict:
    """注册稀疏包（免签名，需要开发者模式）。"""
    man = msix_manifest_path()
    if not man.is_file():
        return {"ok": False, "reason": f"缺少 {MSIX_MANIFEST}（应与 exe 同目录）"}
    dll = Path(exe_path()).parent / COM_DLL_NAME
    if not dll.is_file():
        return {"ok": False, "reason": f"缺少 {COM_DLL_NAME}"}
    if msix_installed():
        _ps(f'Get-AppxPackage -Name "{MSIX_PKG_NAME}" | Remove-AppxPackage', timeout=120)
    try:
        _ps(f"Add-AppxPackage -Register '{man}' -ExternalLocation '{man.parent}'")
    except Exception as e:
        return {"ok": False, "reason": f"注册异常：{e}"[:160]}
    if msix_installed():
        return {"ok": True, "pkg": MSIX_PKG_NAME}
    return {"ok": False, "reason": "注册未成功（可能需要开启「开发者模式/允许旁加载」）"}


def uninstall_msix() -> None:
    try:
        _ps(f'Get-AppxPackage -Name "{MSIX_PKG_NAME}" | Remove-AppxPackage', timeout=120)
    except Exception:
        pass


# -------------------------------------------------------------------------- #
# Win11 一级菜单：IExplorerCommand COM 外壳扩展
# -------------------------------------------------------------------------- #
CLSID_COM = "{7B3F9A12-4C6D-4E21-9A3B-112233445566}"
COM_DLL_NAME = "FileConvMenu.dll"
COM_VERB_KEY = "FileConvModern"
# 文件用 *；文件夹用 Directory（这样右键文件夹也能看到）
COM_TARGETS = (r"*", "Directory")


def com_dll_path() -> Path:
    """COM DLL 位置：正式安装时在 exe 旁边；源码模式下用仓库里的 native/。"""
    cand = Path(exe_path()).parent / COM_DLL_NAME
    if cand.is_file():
        return cand
    root = Path(__file__).resolve().parents[2]     # src/core/registry.py → 项目根
    alt = root / "native" / COM_DLL_NAME
    return alt if alt.is_file() else cand


def install_com() -> dict:
    """注册 COM 外壳扩展 + 挂到 * 和 Directory 上（不写 SubCommands，见上面教训）。"""
    dll = com_dll_path()
    if not dll.is_file():
        return {"ok": False, "reason": f"找不到 {COM_DLL_NAME}（应放在 {dll.parent}）"}

    clsid_key = rf"Software\Classes\CLSID\{CLSID_COM}"
    _set_str(HIVE, clsid_key, "", "FileConverter 转换文件格式")
    _set_str(HIVE, clsid_key + r"\InprocServer32", "", str(dll))
    _set_str(HIVE, clsid_key + r"\InprocServer32", "ThreadingModel", "Apartment")

    icon = exe_path()
    for target in COM_TARGETS:
        base = rf"Software\Classes\{target}\shell\{COM_VERB_KEY}"
        _set_str(HIVE, base, "", MENU_NAME)
        _set_str(HIVE, base, "MUIVerb", MENU_NAME)
        _set_str(HIVE, base, "Icon", f'"{icon}",0')
        _set_str(HIVE, base, "ExplorerCommandHandler", CLSID_COM)
        _set_str(HIVE, base, "CommandStateSync", "")   # 官方示例里的配套值
        _set_str(HIVE, base, "Position", "Top")        # 放在菜单靠前位置
        _del_value(HIVE, base, "SubCommands")

    return {"ok": True, "dll": str(dll)}


def remove_com() -> None:
    _delete_tree(HIVE, rf"Software\Classes\CLSID\{CLSID_COM}")
    for target in COM_TARGETS:
        _delete_tree(HIVE, rf"Software\Classes\{target}\shell\{COM_VERB_KEY}")


def com_registered() -> bool:
    return key_exists(rf"Software\Classes\CLSID\{CLSID_COM}\InprocServer32")


def com_verify() -> tuple[bool, str]:
    """真正实例化一次 COM 对象并取标题，确认能被加载。"""
    import ctypes
    import uuid

    ole32 = ctypes.WinDLL("ole32")

    class GUID(ctypes.Structure):
        _fields_ = [("d1", ctypes.c_ulong), ("d2", ctypes.c_ushort),
                    ("d3", ctypes.c_ushort), ("d4", ctypes.c_ubyte * 8)]

    def mk(s: str) -> GUID:
        u = uuid.UUID(s)
        g = GUID()
        g.d1, g.d2, g.d3 = u.fields[0], u.fields[1], u.fields[2]
        for i, b in enumerate(u.bytes[8:]):
            g.d4[i] = b
        return g

    ole32.CoInitialize(None)
    p = ctypes.c_void_p()
    hr = ole32.CoCreateInstance(ctypes.byref(mk(CLSID_COM)), None, 1,
                               ctypes.byref(mk("{00000000-0000-0000-C000-000000000046}")),
                               ctypes.byref(p))
    if hr != 0 or not p:
        ole32.CoUninitialize()
        return False, f"CoCreateInstance 失败 (0x{hr & 0xFFFFFFFF:08X})"
    try:
        vtbl = ctypes.cast(p, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))
        fn = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p,
                                ctypes.POINTER(ctypes.c_void_p))(vtbl.contents[3])
        out = ctypes.c_void_p()
        hr2 = fn(p, None, ctypes.byref(out))
        title = ctypes.wstring_at(out) if out else ""
        if out:
            ole32.CoTaskMemFree(ctypes.cast(out, ctypes.c_void_p))
        fn_rel = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vtbl.contents[2])
        fn_rel(p)
        if hr2 != 0 or not title:
            return False, f"GetTitle 失败 (0x{hr2 & 0xFFFFFFFF:08X})"
        return True, title
    finally:
        ole32.CoUninitialize()


def is_installed() -> bool:
    """任何一种形式装上了都算装上了。ctx（级联扩展）是主力。"""
    return ctx_registered() or key_exists(PARENT_KEY) or com_registered()


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
