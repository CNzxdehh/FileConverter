@echo off
setlocal enabledelayedexpansion
rem 编译 COM 外壳扩展（纯 C，x64）。本机 MSVC 只有编译器、没有 C++ 头与 CRT 库，
rem 所以直接挂 UCRT + Windows SDK 的库，用 /NODEFAULTLIB 手工链接。

set "SDKROOT=C:\Program Files (x86)\Windows Kits\10"
set "SDKVER=10.0.26100.0"
set "CLDIR=C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC\14.44.35207\bin\Hostx64\x64"

if not exist "%CLDIR%\cl.exe" (
    echo [ERROR] cl.exe not found: %CLDIR%
    exit /b 1
)

cd /d "%~dp0"
set "PATH=%CLDIR%;%PATH%"
if not exist obj mkdir obj
del /q FileConvMenu.dll FileConvMenu.exp FileConvMenu.lib obj\*.obj 2>nul

cl /nologo /TC /O2 /GS- /utf-8 /LD /W3 ^
   /I"%SDKROOT%\Include\%SDKVER%\ucrt" ^
   /I"%SDKROOT%\Include\%SDKVER%\um" ^
   /I"%SDKROOT%\Include\%SDKVER%\shared" ^
   /Fo:obj\ /Fe:FileConvMenu.dll FileConvMenu.c ^
   /link /NODEFAULTLIB /DEF:FileConvMenu.def /ENTRY:DllMain ^
   /LIBPATH:"%SDKROOT%\Lib\%SDKVER%\ucrt\x64" ^
   /LIBPATH:"%SDKROOT%\Lib\%SDKVER%\um\x64" ^
   ucrt.lib kernel32.lib ole32.lib shell32.lib shlwapi.lib user32.lib
if errorlevel 1 (
    echo [ERROR] compile or link failed
    exit /b 1
)
echo [OK] FileConvMenu.dll built
dir /b FileConvMenu.dll
