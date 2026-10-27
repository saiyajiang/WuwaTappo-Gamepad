@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Wuwa Tappo Bridge - log viewer

echo ============================================================
echo   bridge.log  -  last 60 lines
echo ============================================================
echo.
echo   This is where everything goes when running in the
echo   background. If the tray icon is missing, look here.
echo.

powershell -NoProfile -Command ^
  "$f='%~dp0bridge.log'; ^
   if (Test-Path $f) { Get-Content $f -Tail 60 -Encoding UTF8 } ^
   else { Write-Host '  bridge.log does not exist yet.'; ^
          Write-Host '  Run launch.bat first.' }"

echo.
echo ------------------------------------------------------------
echo   Full file: %~dp0bridge.log
echo ------------------------------------------------------------
echo.
pause
