@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Wuwa Tappo Bridge - auto-start

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "LINK=%STARTUP%\WuwaTappoGamepadBridge.lnk"
set "TARGET=%~dp0tray_launcher.vbs"

if exist "%LINK%" (
    echo Auto-start: ENABLED
    choice /c YN /m "Disable"
    if errorlevel 2 goto :end
    del "%LINK%"
    echo   Removed.
    goto :end
)

echo Auto-start: DISABLED
choice /c YN /m "Enable"
if errorlevel 2 goto :end

powershell -NoProfile -Command ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%LINK%'); ^
   $s.TargetPath='%TARGET%'; $s.WorkingDirectory='%~dp0'; ^
   $s.Description='Wuwa Tappo gamepad bridge'; $s.Save()"
echo   Shortcut created.

:end
timeout /t 3
