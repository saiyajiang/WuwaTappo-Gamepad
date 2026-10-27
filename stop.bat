@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Wuwa Tappo Bridge - stop

powershell -NoProfile -Command ^
  "$p = Get-CimInstance Win32_Process -Filter \"Name='python.exe' or Name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*tray_app.py*' -or $_.CommandLine -like '*gamepad_bridge.py*' }; ^
   if ($p) { $p | ForEach-Object { Write-Host ('  killing PID ' + $_.ProcessId); Stop-Process -Id $_.ProcessId -Force } ; Write-Host '  done.' } ^
   else { Write-Host '  nothing was running.' }"

echo.
timeout /t 3
