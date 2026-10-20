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

echo   [1/3] 检查依赖...
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

echo   [2/3] 生成程序图标...
python "%~dp0tools\make_icon.py"

echo   [3/3] 打包中，请稍候（约 1-3 分钟）...
python -m PyInstaller --noconfirm --clean "%~dp0build.spec"

echo.
if exist "%~dp0dist\FileConverter.exe" (
    echo   完成：%~dp0dist\FileConverter.exe
    for %%A in ("%~dp0dist\FileConverter.exe") do echo   大小：%%~zA 字节
) else (
    echo   [失败] 没有生成 exe，请看上面的错误信息。
)
echo.
pause
