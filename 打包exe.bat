@echo off
chcp 936 >nul
cd /d "%~dp0"
title 打包为单个 exe

echo.
echo   文件格式转换工具 —— 打包成单个 exe
echo   ========================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo   [错误] 没有找到 python，请先把 Python 加进 PATH。
    pause
    exit /b 1
)

echo   [1/4] 检查依赖...
python -c "import PyInstaller" >nul 2>nul
if errorlevel 1 (
    echo         正在安装打包依赖 PyInstaller...
    python -m pip install -q --disable-pip-version-check pyinstaller
)
python -c "import PIL, pdf2docx, docx, fitz" >nul 2>nul
if errorlevel 1 (
    echo         正在安装运行依赖（Pillow / pdf2docx / python-docx / PyMuPDF）...
    python -m pip install -q --disable-pip-version-check -r requirements.txt
)

echo   [2/4] 生成程序图标与 COM 菜单项表...
python "%~dp0tools\make_icon.py"
python "%~dp0native\gen_verbs.py"

echo   [3/4] 编译 COM 外壳扩展（一级右键菜单，需要 MinGW gcc）...
if exist "%~dp0native\build_native.bat" (
    call "%~dp0native\build_native.bat"
) else (
    echo         跳过：没有 native\build_native.bat
)

echo   [4/4] 打包 exe，请稍候（约 1-3 分钟）...
python -m PyInstaller --noconfirm --clean "%~dp0build.spec"

if exist "%~dp0native\FileConvMenu.dll" (
    copy /y "%~dp0native\FileConvMenu.dll" "%~dp0dist\FileConvMenu.dll" >nul
    echo         已附带 FileConvMenu.dll（一级菜单的 COM 扩展）
)
if exist "%~dp0AppxManifest.xml" (
    copy /y "%~dp0AppxManifest.xml" "%~dp0dist\AppxManifest.xml" >nul
    xcopy /y /q /i "%~dp0Assets" "%~dp0dist\Assets" >nul
    echo         已附带 AppxManifest.xml + Assets（Windows 11 现代菜单用）
)

echo.
if exist "%~dp0dist\FileConverter.exe" (
    echo   完成：%~dp0dist\FileConverter.exe
    for %%A in ("%~dp0dist\FileConverter.exe") do echo   大小：%%~zA 字节
    echo   发布时请把 dist 下的 exe + dll 两个文件一起带上。
) else (
    echo   [失败] 没有生成 exe，请看上面的错误信息。
)
echo.
pause
