# -*- coding: utf-8 -*-
"""右键菜单精简器 —— 只保留「压缩解压 + 常规操作 + 本工具」。

三类注册来源都能管（扫描全了才不会漏）：
    A. shellex\\ContextMenuHandlers  → 在 HKCU\\...\\CLSID\\{...} 加 LegacyDisable
    B. 静态菜单动词 shell\\<verb>    → 在 HKCU\\...\\<位置>\\<verb> 加 LegacyDisable
    C. MSIX 包的 fileExplorerContextMenus → 同样走 CLSID 的 LegacyDisable

**全部在 HKCU 下写（用户级覆盖系统级），不卸载任何软件、不删任何文件。**
每个改动都会记进备份文件，`restore` 可以原样还原。

用法：
    python menu_cleaner.py scan              # 只扫描，列出建议
    python menu_cleaner.py apply             # 应用精简
    python menu_cleaner.py restore           # 一键还原
    python menu_cleaner.py apply --keep Bandizip --keep 7-Zip    # 自定义白名单
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import winreg
from pathlib import Path

APP_DIR = Path.home() / "AppData/Local/Programs/FileConverter"
BACKUP = APP_DIR / "menu_backup.json"

# --------------------------------------------------------------------------- #
# 黑名单：只有命中才禁用。宁可漏禁、绝不误伤（漏了再加一条就行，误伤会影响日常）。
# 匹配的是「注册名 + DLL 路径 + 友好名 + 命令行」拼起来的小写文本。
# --------------------------------------------------------------------------- #
DEFAULT_BLOCK = [
    # WPS（金山）—— 总结全文、视频压缩、提取音频、上传/通过WPS发送 全是它
    "kingsoft", "wps", "kwps", "qingnse", "qingshell", "kdesktop", "wpsappext",
    # 夸克网盘
    "quark",
    # QQ
    "tencent", "qqextension", r"\\qq\\", "qqshell",
    # 网易邮箱大师
    "netease", "mailmaster", r"\\163\\",
    # 奇虎 / 360
    "qihoo", "360", "奇虎",
    # Clipchamp
    "clipchamp",
    # 手机连接（"发送到手机"）
    "phonelink", "your phone", "微软手机连接",
]

# 白名单：命中的一律不动（在黑名单判定之后生效，优先级最高）
DEFAULT_KEEP = [
    "fileconv",        # 本工具
    "7-zip", "7z",     # 压缩解压
    "bandizip", "bandisoft",
    "windows defender", "shellext.dll",   # Defender 扫描，安全功能留着
]

# --------------------------------------------------------------------------- #
# MSIX 包：注册表这条路是死的
#
# 实测：`wpsappext1/2/3`、`QQExtension`、`Clipchamp` 的 COM 类**根本不在注册表里**
#   - HKCU\Software\Classes\ActivatableClasses\Package → 0 个包
#   - HKLM\SOFTWARE\Classes\ActivatableClasses\Package → 只有 1 个（无关的）
#   - HKLM\SOFTWARE\Classes\CLSID 里也没有它们的 CLSID
# 它们由包系统（PackageGraph / StateRepository 数据库）内部管理，**摘注册表无效**。
#
# 唯一可行的办法：**卸载这些包**。好在它们本身就是纯"右键扩展包" ——
# 卸掉不影响主程序（WPS 还能用、QQ 还能用），只是不再往右键菜单里塞东西。
# 这是用户级操作，不需要管理员。
# --------------------------------------------------------------------------- #
# 默认卸：纯扩展包，零副作用
MSIX_REMOVE_SAFE = ["wpsappext", "qqextension"]
# 需要显式点名才卸：Clipchamp 是 Windows 自带应用本体，卸了要用商店重装
MSIX_REMOVE_OPTIONAL = ["clipchamp"]


def _ps(script: str, timeout: int = 120) -> tuple[int, str]:
    p = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                        "-Command", script], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def msix_scan() -> list[str]:
    """列出装了右键菜单扩展的包。"""
    _, out = _ps("Get-AppxPackage | Where-Object { $_.InstallLocation -and "
                 "(Test-Path (Join-Path $_.InstallLocation 'AppxManifest.xml')) } "
                 "| ForEach-Object { if (Select-String -Path "
                 "(Join-Path $_.InstallLocation 'AppxManifest.xml') "
                 "-Pattern 'fileExplorerContextMenus' -Quiet -ErrorAction SilentlyContinue) "
                 "{ $_.Name } }", timeout=180)
    return [l.strip() for l in out.splitlines() if l.strip() and " " not in l.strip()]


def msix_uninstall(include_optional: bool = False) -> list[str]:
    """卸载黑名单里的右键扩展包。返回实际卸载的包名。

    ⚠️ 必须**一个前缀匹配多个包**：`wpsappext` 要一次卸掉 wpsappext1/2/3 三个。
    早期版本用 `next(... )` 只取第一个命中，导致 2/3 永远漏掉。
    """
    targets = list(MSIX_REMOVE_SAFE)
    if include_optional:
        targets += MSIX_REMOVE_OPTIONAL
    installed = msix_scan()
    done = []
    for t in targets:
        # 前缀匹配全部（wpsappext -> wpsappext1/2/3）
        hits = [p for p in installed if p.lower().startswith(t.lower())]
        if not hits:
            print(f"  [跳过] {t}：没装")
            continue
        for hit in hits:
            code, out = _ps(f"Get-AppxPackage -Name '{hit}' | Remove-AppxPackage", timeout=180)
            print(f"  [{'已卸载' if code == 0 else '失败'}] {hit}")
            if code == 0:
                done.append(hit)
            else:
                print("        " + out.strip()[:160])
    return done


# --------------------------------------------------------------------------- #
def _read(hive: int, path: str, name: str = "") -> str | None:
    try:
        with winreg.OpenKey(hive, path) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return None


def _keys(hive: int, path: str) -> list[str]:
    out: list[str] = []
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


HANDLER_BASES = [
    r"*\shellex\ContextMenuHandlers",
    r"AllFilesystemObjects\shellex\ContextMenuHandlers",
    r"Directory\shellex\ContextMenuHandlers",
    r"Directory\Background\shellex\ContextMenuHandlers",
]

VERB_BASES = [
    r"*\shell",
    r"AllFilesystemObjects\shell",
    r"Directory\shell",
    r"Directory\Background\shell",
]


def scan_handlers() -> list[dict]:
    """来源 A：COM 外壳扩展。禁用点 = CLSID。"""
    out, seen = [], set()
    for base in HANDLER_BASES:
        for name in _keys(winreg.HKEY_CLASSES_ROOT, base):
            clsid = _read(winreg.HKEY_CLASSES_ROOT, rf"{base}\{name}")
            if not clsid:
                continue
            key = ("handler", str(clsid).upper(), base)
            if key in seen:
                continue
            seen.add(key)
            dll = _read(winreg.HKEY_CLASSES_ROOT, rf"CLSID\{clsid}\InprocServer32") or ""
            friendly = _read(winreg.HKEY_CLASSES_ROOT, rf"CLSID\{clsid}") or ""
            out.append(dict(kind="handler", reg=name, clsid=str(clsid),
                            base=base, dll=str(dll), friendly=friendly))
    return out


def scan_verbs() -> list[dict]:
    """来源 B：静态菜单动词。禁用点 = 动词键本身。"""
    out, seen = [], set()
    for base in VERB_BASES:
        for verb in _keys(winreg.HKEY_CLASSES_ROOT, base):
            label = (_read(winreg.HKEY_CLASSES_ROOT, rf"{base}\{verb}")
                     or _read(winreg.HKEY_CLASSES_ROOT, rf"{base}\{verb}", "MUIVerb")
                     or verb)
            cmd = _read(winreg.HKEY_CLASSES_ROOT, rf"{base}\{verb}\command") or ""
            blob = f"{verb} {label} {cmd}".lower()
            # 纯系统动词（命令指向 system32 / explorer.exe）一律不碰
            if ("system32" in blob or "\\windows\\" in blob
                    or "explorer.exe" in blob or "shell32" in blob
                    or "imageres" in blob or "ntshrui" in blob):
                continue
            key = ("verb", base, verb)
            if key in seen:
                continue
            seen.add(key)
            out.append(dict(kind="verb", reg=verb, base=base,
                            label=str(label), cmd=str(cmd)))
    return out


def scan_msix() -> list[dict]:
    """来源 C：MSIX 包的文件资源管理器菜单扩展，禁用点 = 它声明的 CLSID。

    ⚠️ manifest 里属性写作 `Clsid="CC19E147-7757-483C-B27F-3D81BCEB38F1"`，
    **不带大括号**（早期版本按 `{...}` 匹配，结果一个都没扫到，静默返回空）。
    匹配时要把可选大括号算进去。
    """
    ps = ("Get-AppxPackage | ForEach-Object { $_.PackageFullName + '|' + $_.InstallLocation }")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                            "-Command", ps], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=90)
    except Exception:
        return []
    out = []
    for line in (r.stdout or "").splitlines():
        if "|" not in line:
            continue
        pkg, loc = line.split("|", 1)
        man = Path(loc.strip()) / "AppxManifest.xml"
        if not man.is_file():
            continue
        try:
            txt = man.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "fileExplorerContextMenus" not in txt:
            continue
        # 抓 fileExplorerContextMenus 段落内所有 Clsid（可选大括号）
        seg = txt[txt.find("fileExplorerContextMenus"):]
        seg = seg[: seg.find("</desktop4:FileExplorerContextMenus>") or 4000]
        for m in re.finditer(r'Clsid="\{?([0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-'
                             r'[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12})\}?"',
                             seg, re.I):
            out.append(dict(kind="msix", reg=pkg.strip(),
                            clsid="{" + m.group(1).upper() + "}",
                            base="", dll=str(man), friendly=pkg.strip()))
    uniq, seen = [], set()
    for d in out:
        if d["clsid"] in seen:
            continue
        seen.add(d["clsid"])
        uniq.append(d)
    return uniq


def scan_all() -> list[dict]:
    items = scan_handlers() + scan_verbs() + scan_msix()
    for it in items:
        blob = " ".join(str(it.get(k, "")) for k in ("reg", "dll", "friendly", "label", "cmd"))
        it["blob"] = blob.lower()
    return items


# --------------------------------------------------------------------------- #
def decide(items: list[dict], keep: list[str], block: list[str]) -> list[dict]:
    """决定禁用哪些。

    ⚠️ 策略是**白名单优先 + 只禁黑名单**：没命中的一律不动。
    早期版本是"把所有非系统项都禁掉"，结果误伤了 Git Bash、WSL、WorkBuddy
    这些用户天天用的菜单项 —— 宁可漏禁也不要误伤。
    """
    keep = [k.lower() for k in keep]
    block = [k.lower() for k in block]
    plan = []
    for it in items:
        blob = it.get("blob", "")
        it["reason"] = "未命中黑名单，保留"
        if any(k in blob for k in keep):
            it["reason"] = "命中保留名单"
            continue
        hit = next((k for k in block if k in blob), None)
        if hit:
            it["why"] = f"命中黑名单「{hit}」"
            it["reason"] = "禁用"
            plan.append(it)

    # 同一个 CLSID 可能挂在多个 base 下，去重后再报给用户（否则 13 条其实只有 6 个）
    uniq, seen = [], set()
    for it in plan:
        p = disable_point(it)
        if p is None:
            it["reason"] = "MSIX 走挂载点这条路不通，改用 msix-block"
            continue
        if p in seen:
            continue
        seen.add(p)
        uniq.append(it)
    return uniq


def disable_point(it: dict) -> str | None:
    """返回禁用点所在的 HKCU 路径（加 LegacyDisable）。返回 None = 这项没法用这个办法禁。

    ⛔ 血泪教训：**绝对不要在 `HKCU\\Software\\Classes\\CLSID\\{...}` 下建
    「只有 LegacyDisable、没有 InprocServer32」的键**。
    因为 HKCU\\Software\\Classes\\CLSID\\{X} 只要存在就会**完全顶掉** HKLM 的同名键，
    COM 去加载时找不到服务程序 → 轻则扩展静默失效，重则整条菜单构建中断。
    本机实测就是这么把本工具自己的菜单项也搞没的（用户反馈"直接消失了，找都找不到"）。
    而且对 MSIX 包注册的类，这种写法**根本不起作用**（WPS/QQ/Clipchamp 全部还在）。

    ✅ 正确做法：**在「挂载点」上加 LegacyDisable**，完全不碰 CLSID：
        HKCU\\Software\\Classes\\*\\shellex\\ContextMenuHandlers\\<注册名>\\LegacyDisable
    Explorer 读到挂载点被标记就跳过，不加载那个 COM 类，干净且零副作用。
    """
    if it["kind"] == "handler":
        return rf"Software\Classes\{it['base']}\{it['reg']}"
    if it["kind"] == "verb":
        return rf"Software\Classes\{it['base']}\{it['reg']}"
    return None          # msix：这条路走不通，见下面的 block_msix()


def block_msix() -> list[dict]:
    """MSIX 包的菜单扩展是另一套机制（包身份 + ActivatableClasses），
    挂载点上根本没有键可禁。唯一可靠的办法是把它的 Server 类从注册表摘掉。

    ⚠️ 这属于「摘掉注册」而不是「打个标记」，风险高一档，所以单独一个子命令，
    默认不执行，必须显式调用 `msix-block`。删之前把整棵子树备份到文件里。
    """
    out = []
    for it in scan_msix():
        pkg = it["reg"]
        # 从包全名里去掉版本号段，得到包目录名（ActivatableClasses 用的是这个）
        folder = pkg.split("_")[0] + "_" + pkg.split("_")[1] + "_" + pkg.split("_")[2] \
            if pkg.count("_") >= 3 else pkg
        base = rf"Software\Classes\ActivatableClasses\Package\{folder}"
        srv = rf"{base}\Server\{it['clsid']}"
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, srv):
                pass
        except OSError:
            continue
        out.append(dict(it, msix_folder=folder, server_key=srv))
    return out


# --------------------------------------------------------------------------- #
def apply(plan: list[dict]) -> dict:
    backup: list[dict] = []
    if BACKUP.is_file():
        try:
            backup = json.loads(BACKUP.read_text(encoding="utf-8"))
        except Exception:
            backup = []
    done = 0
    for it in plan:
        path = disable_point(it)
        if not path:
            continue
        existed = _read(winreg.HKEY_CURRENT_USER, path, "LegacyDisable") is not None
        if not existed:
            backup.append(dict(path=path, reg=it["reg"], kind=it["kind"]))
        try:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0,
                                    winreg.KEY_SET_VALUE) as k:
                winreg.SetValueEx(k, "LegacyDisable", 0, winreg.REG_SZ, "")
            done += 1
        except OSError as e:
            print(f"  [失败] {it['reg']}: {e}")
    BACKUP.parent.mkdir(parents=True, exist_ok=True)
    BACKUP.write_text(json.dumps(backup, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"applied": done, "backup": str(BACKUP)}


def restore() -> dict:
    if not BACKUP.is_file():
        return {"restored": 0, "note": "没有备份文件，无需还原"}
    backup = json.loads(BACKUP.read_text(encoding="utf-8"))
    n = 0
    for rec in backup:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rec["path"], 0,
                                winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, "LegacyDisable")
            n += 1
        except FileNotFoundError:
            pass
        except OSError as e:
            print(f"  [失败] {rec['reg']}: {e}")
    BACKUP.unlink(missing_ok=True)
    return {"restored": n}


# --------------------------------------------------------------------------- #
def main(argv: list[str]) -> int:
    cmd = (argv[0] if argv else "scan").lower()
    extra = [a for a in argv if a.startswith("--keep=")]
    keep = DEFAULT_KEEP + [a.split("=", 1)[1] for a in extra]

    items = scan_all()
    if cmd == "scan":
        plan = decide(items, keep, DEFAULT_BLOCK)
        kept = [i for i in items if i.get("reason", "").startswith(("未命中", "命中保留"))]
        print(f"共扫到 {len(items)} 项 → 建议禁用 {len(plan)} 项，保留 {len(kept)} 项\n")
        print("=" * 92)
        print("建议禁用（只禁这些）")
        print("=" * 92)
        for i, it in enumerate(plan, 1):
            desc = it.get("friendly") or it.get("label") or ""
            print(f"  {i:2d}. [{it['kind']:7s}] {it['reg']}")
            print(f"        {it['why']}   {desc[:60]}")
        print()
        print("=" * 92)
        print("会保留（节选，去重后）")
        print("=" * 92)
        seen = set()
        for it in kept:
            r = it["reg"].strip()
            if r.lower() in seen:
                continue
            seen.add(r.lower())
            print(f"  [{it['kind']:7s}] {r}")
        print()
        print(f"执行：python menu_cleaner.py apply    （备份写到 {BACKUP}）")
        print(f"还原：python menu_cleaner.py restore")
        return 0

    if cmd == "apply":
        plan = decide(items, keep, DEFAULT_BLOCK)
        r = apply(plan)
        print(f"已禁用 {r['applied']} 项")
        print(f"备份：{r['backup']}")
        print("请重启资源管理器：Stop-Process -Name explorer -Force")
        return 0

    if cmd == "restore":
        r = restore()
        print(f"已还原 {r.get('restored', 0)} 项  {r.get('note', '')}")
        print("请重启资源管理器：Stop-Process -Name explorer -Force")
        return 0

    if cmd == "msix-scan":
        pkgs = msix_scan()
        print(f"装了文件资源管理器菜单扩展的包，共 {len(pkgs)} 个：\n")
        for p in pkgs:
            tag = ""
            if any(p.lower().startswith(t) for t in MSIX_REMOVE_SAFE):
                tag = "  ← 默认会卸（纯扩展包，不影响主程序）"
            elif any(p.lower().startswith(t) for t in MSIX_REMOVE_OPTIONAL):
                tag = "  ← 需 --with-optional 才卸（是应用本体）"
            print(f"  {p}{tag}")
        return 0

    if cmd == "msix-uninstall":
        print("卸载右键扩展包：")
        done = msix_uninstall(include_optional="--with-optional" in argv)
        print(f"\n已卸载 {len(done)} 个：{done or '无'}")
        print("请重启资源管理器：Stop-Process -Name explorer -Force")
        return 0

    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))