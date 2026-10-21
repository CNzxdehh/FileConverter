# -*- coding: utf-8 -*-
"""把新的级联子菜单 DLL（FileConvCtx.dll）接进打包 / 安装 / 卸载脚本。

⚠️ .bat 铁律：存 GBK、行尾 CRLF，改完必须校验没有裸 LF。
"""
import io
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(p: Path) -> str:
    """读 GBK，统一成 \\n 便于替换。"""
    return io.open(p, encoding="gbk").read().replace("\r\n", "\n")


def save(p: Path, s: str) -> None:
    io.open(p, "w", encoding="gbk", newline="").write("\r\n".join(s.split("\n")))
    b = open(p, "rb").read()
    if b.count(b"\r\n") != b.count(b"\n"):
        raise SystemExit(f"[错误] {p.name} 存在裸 LF，会闪退！")


def sub(s: str, old: str, new: str, tag: str) -> str:
    if old not in s:
        raise SystemExit(f"[错误] 在 {tag} 里找不到锚点：{old[:60]!r}")
    return s.replace(old, new, 1)


# --------------------------------------------------------------------------- #
# 1) 打包exe.bat：多复制一个 FileConvCtx.dll 到 dist
pack = ROOT / "打包exe.bat"
s = load(pack)
anchor = 'if exist "%~dp0AppxManifest.xml" ('
ctx_block = (
    'if exist "%~dp0native\\FileConvCtx.dll" (\n'
    '    copy /y "%~dp0native\\FileConvCtx.dll" "%~dp0dist\\FileConvCtx.dll" >nul\n'
    '    echo         已复制 FileConvCtx.dll（级联子菜单外壳扩展）\n'
    ')\n'
)
s = sub(s, anchor, ctx_block + anchor, "打包exe.bat")
save(pack, s)
print(f"[OK] {pack.name} 已加入 FileConvCtx.dll 复制")

# --------------------------------------------------------------------------- #
# 2) install.bat：改说辞（原来是"COM 外壳扩展，直接进一级菜单"）
ins = ROOT / "install.bat"
s = load(ins)
s = s.replace("写入右键菜单（COM 外壳扩展，直接进一级菜单）",
              "写入右键菜单（级联子菜单：转换文件格式）")
s = sub(s,
        "echo   完成！现在右键任意文件或文件夹，一级菜单里就有【转换文件格式】。",
        "echo   完成！现在右键任意文件或文件夹，菜单里直接就有\n"
        "echo   【转换文件格式】，鼠标移上去即展开全部转换项。",
        "install.bat")
save(ins, s)
print(f"[OK] {ins.name} 说辞已更新")

# --------------------------------------------------------------------------- #
# 3) uninstall.bat
uni = ROOT / "uninstall.bat"
s = load(uni)
s = s.replace("删除右键菜单与 COM 扩展", "删除右键菜单与级联子菜单扩展")
s = sub(s,
        "echo   已清理右键菜单、COM 注册与临时文件，没有后台进程残留。",
        "echo   已清理右键菜单、级联子菜单扩展注册与临时文件，没有后台进程残留。",
        "uninstall.bat")
save(uni, s)
print(f"[OK] {uni.name} 说辞已更新")
