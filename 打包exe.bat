@echo off
chcp 936 >nul
cd /d "%~dp0"
title 打包 FileConverter exe

echo.
echo   文件格式转换器 - 打包成 exe
echo   ========================================
echo.

REM ============================================================
REM  选 Python 解释器
REM  [禁] 不能用系统 Python：它缺 python-docx / pdf2docx，
REM        打出来的 exe 只有 51MB，一碰 Word 转换就崩。
REM  [荐] 依赖齐全的环境在托管 venv 里，优先用它。
REM        判断标准：exe 体积约 158MB 正常，约 51MB 就是缺依赖。
REM ============================================================
set "PYEXE=python"
set "VENV=C:\Users\徐颢朗\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
if exist "%VENV%" (
    set "PYEXE=%VENV%"
    echo   [0/4] 用依赖齐全的 Python
) else (
    echo   [0/4] 没找到托管 venv，退回系统 Python
    echo         （如果打出来只有 51MB，说明缺 python-docx/pdf2docx）
)
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo   [失败] 没找到 python，请先装 Python 并加进 PATH
    pause
    exit /b 1
)

echo   [1/4] 检查依赖...
"%PYEXE%" -c "import PyInstaller" >nul 2>nul
if errorlevel 1 (
    echo         在安装 PyInstaller...
    "%PYEXE%" -m pip install -q --disable-pip-version-check pyinstaller
)
"%PYEXE%" -c "import PIL, pdf2docx, docx, fitz" >nul 2>nul
if errorlevel 1 (
    echo         在安装 Pillow / pdf2docx / python-docx / PyMuPDF...
    "%PYEXE%" -m pip install -q --disable-pip-version-check -r requirements.txt
)

echo   [2/4] 生成图标 + 刷新 COM 菜单方案表...
"%PYEXE%" "%~dp0tools\make_icon.py"
"%PYEXE%" "%~dp0native\gen_verbs.py"

echo   [3/4] 编译 COM 菜单扩展（需要 MinGW gcc）...
if exist "%~dp0native\build_native.bat" (
    call "%~dp0native\build_native.bat"
) else (
    echo         跳过：没有 native\build_native.bat
)

echo   [4/4] 打 exe，请等 1-3 分钟...
"%PYEXE%" -m PyInstaller --noconfirm --clean "%~dp0build.spec"

if exist "%~dp0native\FileConvMenu.dll" (
    copy /y "%~dp0native\FileConvMenu.dll" "%~dp0dist\FileConvMenu.dll" >nul
    echo         已拷 FileConvMenu.dll 到 dist
)
if exist "%~dp0native\FileConvCtx.dll" (
    copy /y "%~dp0native\FileConvCtx.dll" "%~dp0dist\FileConvCtx.dll" >nul
    echo         已拷 FileConvCtx.dll 到 dist
)
if exist "%~dp0AppxManifest.xml" (
    copy /y "%~dp0AppxManifest.xml" "%~dp0dist\AppxManifest.xml" >nul
    xcopy /y /q /i "%~dp0Assets" "%~dp0dist\Assets" >nul
    echo         已拷 AppxManifest.xml + Assets
)

echo.
if exist "%~dp0dist\FileConverter.exe" (
    echo   完成：%~dp0dist\FileConverter.exe
    for %%A in ("%~dp0dist\FileConverter.exe") do echo   大小：%%~zA 字节
    for %%A in ("%~dp0dist\FileConverter.exe") do set /a SZMB=%%~zA/1048576
    if %SZMB% LSS 100 (
        echo   [警告] 体积只有 %SZMB%MB，偏小！
        echo           正常约 158MB。小于 100MB 说明缺 python-docx/pdf2docx，
        echo           Word 相关转换会失败，请用依赖齐全的 Python 重打。
    ) else (
        echo   体积正常（大于 100MB，依赖完整）
    )
    echo   使用时把 dist 里的 exe + dll 一起拷贝。
) else (
    echo   [失败] 没生成 exe，请看上面的报错信息
)
echo.
pause
