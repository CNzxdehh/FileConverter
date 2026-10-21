# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：单个 exe，windows 子系统（转换时才 AllocateConsole）。

用法： pyinstaller build.spec --noconfirm --clean
想要启动更快（不每次解压 ~100MB）的话改一行：
    exe = EXE(...)  →  见文件末尾注释的 onedir 写法
"""

from PyInstaller.utils.hooks import collect_all, collect_submodules

datas, binaries, hiddenimports = [], [], []
for pkg in ("pdf2docx", "docx", "PIL", "pymupdf", "fitz"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# PyMuPDF 只按需引入（collect_all 会把 pymupdf4llm / pymupdf_layout 一起拖进来，白胖几十 MB）
hiddenimports += [
    "fitz", "pymupdf", "pymupdf.mupdf",
    "core", "core.config", "core.winui", "core.ffmpegtool",
    "core.registry", "core.tasks", "core.collector", "core.chooser",
]

block_cipher = None

a = Analysis(
    ["src\\converter.py"],
    pathex=["src", "."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter", "matplotlib", "PyQt5", "PySide2", "IPython", "pytest", "unittest",
        "pymupdf4llm", "pymupdf_layout", "PIL.ImageQt", "PIL.ImageTk",
    ],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="FileConverter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,               # 右键时不闪一堆黑窗口；转换时由代码 AllocConsole
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="app.ico",
    # comctl32 v6 清单：没有它 TaskDialogIndirect（原生选择框）用不了
    manifest="app.manifest",
)

# ---- 可选：改成输出文件夹版（启动快很多，代价是 dist\FileConverter\ 一整个目录）
# from PyInstaller.utils.hooks import collect_dynamic_libs
# coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, strip=False, upx=False,
#                upx_exclude=[], name="FileConverter")
