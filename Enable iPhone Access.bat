@echo off
setlocal
title Enable Pro Downloader iPhone Access
cd /d "%~dp0"

echo Windows Administrator permission is required to update the firewall.
echo The rule will allow TCP port 8000 from your local network only.
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "Start-Process powershell.exe -Verb RunAs -Wait -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File ""%~dp0Enable iPhone Access.ps1""'"

if errorlevel 1 (
  echo.
  echo Firewall setup was cancelled or failed.
  pause
  exit /b 1
)

echo.
echo Firewall setup completed.
pause
