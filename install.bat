@echo off
chcp 936 >nul
cd /d "%~dp0"
title 安装右键菜单 - 转换文件格式

echo.
echo   文件格式转换工具 —— 安装右键菜单
echo   ========================================
echo.

rem 优先用与本脚本同目录的 exe（安装版），其次用 dist\ 下的（源码/打包目录）
set "EXE=%~dp0FileConverter.exe"
if exist "%EXE%" goto HAS_EXE
set "EXE=%~dp0dist\FileConverter.exe"
if exist "%EXE%" goto HAS_EXE

echo   没有找到 FileConverter.exe，改用 Python 源码模式安装。
echo.
where python >nul 2>nul
if errorlevel 1 (
    echo   [错误] 既没有打包好的 exe，系统里也没有 python。
    echo.
    echo   请先做其中一件：
    echo     1〕双击 打包exe.bat 生成 dist\FileConverter.exe 后再运行本脚本；
    echo     2〕或安装 Python 3.9+ 并 pip install -r requirements.txt。
    echo.
    pause
    exit /b 1
)
echo   [1/2] 写入右键菜单（COM 外壳扩展，直接进一级菜单）...
python "%~dp0src\converter.py" install
goto RESTART

:HAS_EXE
echo   [1/2] 写入右键菜单（COM 外壳扩展，直接进一级菜单）...
"%EXE%" install

:RESTART
echo   [2/2] 重启资源管理器，让菜单立刻生效...
taskkill /f /im explorer.exe >nul 2>nul
start "" explorer.exe

echo.
echo   完成！现在右键任意文件或文件夹，一级菜单里就有【转换文件格式】。
echo.
echo   卸载：uninstall.bat
echo.
pause
