@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Wuwa Tappo Gamepad Bridge

where python >nul 2>&1
if errorlevel 1 (
    echo.
    echo   Python not found.
    echo   Install Python 3.10+ from https://www.python.org
    echo   IMPORTANT: tick "Add python.exe to PATH" during install.
    echo.
    pause
    exit /b 1
)

echo.
echo   Starting... (if it stops at the language menu, type 1, 2 or 3 then Enter)
echo.

python "%~dp0src\launcher.py" %*

echo.
echo ------------------------------------------------------------
echo   Launcher finished.
echo   If no tray icon appeared, run  debug.bat  to see the error.
echo   Errors are also written to  bridge.log
echo ------------------------------------------------------------
pause
