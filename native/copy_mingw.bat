@echo off
rem 把 MinGW 工具链复制到纯 ASCII 路径（C:\mgw），因为原路径含中文会让 ld 找不到库
set "SRC=%LOCALAPPDATA%\Microsoft\WinGet\Packages\BrechtSanders.WinLibs.POSIX.UCRT_Microsoft.Winget.Source_8wekyb3d8bbwe\mingw64"
if not exist "%SRC%\bin\x86_64-w64-mingw32-gcc.exe" (
    echo [ERROR] MinGW not found: %SRC%
    exit /b 1
)
robocopy "%SRC%" C:\mgw /E /NFL /NDL /NJH /NJS /MT:16 /R:1 /W:1 >nul
if exist C:\mgw\bin\x86_64-w64-mingw32-gcc.exe (
    echo [OK] copied to C:\mgw
) else (
    echo [ERROR] copy failed
    exit /b 1
)
