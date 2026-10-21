@echo off
chcp 936 >nul
cd /d "%~dp0"
title 卸载右键菜单 - 转换文件格式

echo.
echo   文件格式转换工具 —— 卸载右键菜单
echo   ========================================
echo.

set "OPT="
if /i "%1"=="/purge" set "OPT=--purge"
if /i "%1"=="/清除配置" set "OPT=--purge"

set "EXE=%~dp0FileConverter.exe"
if exist "%EXE%" goto HAS_EXE
set "EXE=%~dp0dist\FileConverter.exe"
if exist "%EXE%" goto HAS_EXE

where python >nul 2>nul
if errorlevel 1 (
    echo   [错误] 没找到 exe 也没有 python，无法卸载。
    echo.
    pause
    exit /b 1
)
echo   [1/2] 删除右键菜单与级联子菜单扩展...
python "%~dp0src\converter.py" uninstall %OPT%
goto RESTART

:HAS_EXE
echo   [1/2] 删除右键菜单与级联子菜单扩展...
"%EXE%" uninstall %OPT%

:RESTART
echo   [2/2] 重启资源管理器...
taskkill /f /im explorer.exe >nul 2>nul
start "" explorer.exe

echo.
echo   已清理右键菜单、级联子菜单扩展注册与临时文件，没有后台进程残留。
echo   菜单样式已还原成 Windows 11 默认。
echo   如需连配置一起删除，运行：uninstall.bat /purge
echo.
pause
