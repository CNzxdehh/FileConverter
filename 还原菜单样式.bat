@echo off
chcp 936 >nul
cd /d "%~dp0"
title 还原 Win11 默认右键菜单

echo.
echo   还原 Windows 11 默认的紧凑右键菜单
echo   ========================================
echo.
echo   还原后【转换文件格式】会回到「显示更多选项」里，功能不变。
echo.

set "EXE=%~dp0FileConverter.exe"
if exist "%EXE%" goto USE_EXE
set "EXE=%~dp0dist\FileConverter.exe"
if exist "%EXE%" goto USE_EXE

where python >nul 2>nul
if errorlevel 1 (
    echo   [错误] 没找到 exe 也没有 python。
    pause
    exit /b 1
)
python "%~dp0src\converter.py" classic off
goto RESTART

:USE_EXE
"%EXE%" classic off

:RESTART
taskkill /f /im explorer.exe >nul 2>nul
start "" explorer.exe
echo.
echo   已还原。重新打开右键即可看到 Win11 默认样式。
echo.
pause
