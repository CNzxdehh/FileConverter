# -*- coding: utf-8 -*-
"""全面测试收尾：安装版 exe 的真实转换 + 菜单精简状态核对。"""
import subprocess
import sys
import time
from pathlib import Path

EXE = Path.home() / r"AppData\Local\Programs\FileConverter\FileConverter.exe"
SAMPLES = Path(__file__).resolve().parents[1] / "samples"
WORK = Path(r"C:\mgtmp\final_test")
FAILS: list[str] = []


def ok(m): print(f"  [OK]   {m}")
def bad(m): print(f"  [FAIL] {m}"); FAILS.append(m)
def check(c, m): (ok if c else bad)(m); return c


print("=" * 74)
print("一、安装版 exe 的真实转换（不是 dist 版，是用户实际会双击的那个）")
print("=" * 74)
print(f"  exe: {EXE}  ({EXE.stat().st_size:,} 字节)")
check(EXE.is_file(), "安装版 exe 存在")
check(EXE.stat().st_size > 150_000_000,
      f"体积正常（>150MB 说明依赖完整）: {EXE.stat().st_size:,}")

if WORK.exists():
    import shutil
    shutil.rmtree(WORK, ignore_errors=True)
WORK.mkdir(parents=True, exist_ok=True)

CASES = [
    ("pdf2txt",  "sample.pdf",   lambda f: [f.with_suffix(".txt")]),
    ("docx2txt", "sample.docx",  lambda f: [f.with_suffix(".txt")]),
    ("img2jpg",  "sample.png",   lambda f: [f.with_suffix(".jpg")]),
    ("img2webp", "sample.jpg",   lambda f: [f.with_suffix(".webp")]),
    ("aud2mp3",  "sample.wav",   lambda f: [f.with_suffix(".mp3")]),
    ("vid2mp4",  "sample.mov",   lambda f: [f.with_suffix(".mp4")]),
]

for verb, src, expect in CASES:
    s = SAMPLES / src
    if not s.is_file():
        bad(f"{verb}: 缺样本 {src}")
        continue
    dst = WORK / s.name
    dst.write_bytes(s.read_bytes())
    # 先记住转之前目录里有什么，才能精确判断"这次转出来的"是哪几个
    before = {p.name for p in WORK.iterdir()}
    r = subprocess.run([str(EXE), "runm", verb, str(dst)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=180,
                       env={**__import__("os").environ,
                            "FILECONV_SILENT": "1", "FILECONV_NO_CONSOLE": "1"})
    new = [p for p in WORK.iterdir() if p.name not in before and p.stat().st_size > 0]
    if new:
        names = "、".join(p.name for p in new)
        ok(f"{verb:9s} {src:14s} → {names}  [{sum(p.stat().st_size for p in new):,} 字节]")
    else:
        bad(f"{verb:9s} {src:14s} → 没有产出（exit={r.returncode}）")
    # 清掉上一项的产物，避免互相干扰
    for p in new:
        p.unlink(missing_ok=True)

print()
print("=" * 74)
print("二、菜单精简状态")
print("=" * 74)
import winreg

# 禁用点现在在 CLSID 上（Explorer 只认这里，挂载点上的 LegacyDisable 会被忽略）。
# 判定标准：HKCU 下带 LegacyDisable 的 CLSID，且**必须同时有 InprocServer32**
# —— 没有它就是"半截键"，会顶掉 HKLM 导致菜单构建中断。
CLSID_BASE = r"Software\Classes\CLSID"
disabled, halfbaked = [], []
try:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLSID_BASE) as k:
        i = 0
        while True:
            try:
                sub = winreg.EnumKey(k, i); i += 1
            except OSError:
                break
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"{CLSID_BASE}\{sub}") as c:
                    winreg.QueryValueEx(c, "LegacyDisable")
            except OSError:
                continue
            disabled.append(sub)
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                    rf"{CLSID_BASE}\{sub}\InprocServer32") as s:
                    dll = str(winreg.QueryValueEx(s, "")[0]).strip('"')
                if not Path(dll).is_file():
                    halfbaked.append((sub, "DLL 不存在"))
            except OSError:
                halfbaked.append((sub, "缺 InprocServer32（半截键！）"))
except OSError:
    pass

check(len(disabled) >= 5,
      f"CLSID 层面已禁用 {len(disabled)} 个: {disabled}")
check(not halfbaked,
      f"没有半截键（每个禁用项都有完整 InprocServer32）"
      + (f" —— 问题: {halfbaked}" if halfbaked else ""))

# 必须没被动过的
must_keep = ["FileConv", "7-Zip", "EPP"]
for name in must_keep:
    keepd = name not in disabled
    check(keepd, f"保留项未被误伤: {name}")

# 我们的 CLSID 不能被误伤，而且必须指向**安装目录**那份 DLL
# （selftest 收尾会用 dist 版 exe 重装，把路径改到 dist —— 那是开发路径，
#  用户一旦挪掉项目目录菜单就废了，必须改回安装目录）
OURS = "{B2C4E111-7A9D-4C3E-8F21-9D4E5A6B7C8D}"
try:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                        rf"Software\Classes\CLSID\{OURS}") as c:
        # ⚠️ InprocServer32 是**子键**不是值，必须再 OpenKey 一次
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            rf"Software\Classes\CLSID\{OURS}\InprocServer32") as s:
            ctl = str(winreg.QueryValueEx(s, "")[0]).strip('"')
        try:
            winreg.QueryValueEx(c, "LegacyDisable")
            bad("我们的 CLSID 被误加了 LegacyDisable！")
        except OSError:
            ok("我们的 CLSID 没有被误禁用")
    check(Path(ctl).is_file(), f"CLSID 指向的 DLL 存在: {Path(ctl).name}")
    check("FileConverter" in ctl and "workbuddy" not in ctl.lower(),
          f"CLSID 指向安装目录而非开发目录: {ctl}")
except OSError as e:
    bad(f"我们的 CLSID 有问题: {e}")

print()
print("=" * 74)
print("三、MSIX 扩展包已卸载")
print("=" * 74)
r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                    "Get-AppxPackage | Where-Object { $_.Name -match 'wpsappext|QQExtension' } "
                    "| Select-Object -ExpandProperty Name"],
                   capture_output=True, text=True, encoding="utf-8",
                   errors="replace", timeout=90)
left = [l.strip() for l in (r.stdout or "").splitlines() if l.strip()]
check(not left, f"wpsappext/QQExtension 已全部卸载（残留: {left or '无'}）")

print()
print("=" * 74)
print(f"结果：{'全部通过 ✔' if not FAILS else f'失败 {len(FAILS)} 项'}")
for f in FAILS:
    print(f"  - {f}")
print("=" * 74)
sys.exit(1 if FAILS else 0)