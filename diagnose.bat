@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Wuwa Tappo Bridge - diagnose

where python >nul 2>&1
if errorlevel 1 (
    echo Python not on PATH.
    pause
    exit /b 1
)

python "%~dp0src\diagnose.py"
echo.
pause

python "%~dp0src\diagnose.py" --test
echo.
pause
