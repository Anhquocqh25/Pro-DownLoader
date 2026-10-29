@echo off
setlocal
title Pro Downloader PWA Server
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Setting up Pro Downloader for the first run...
  py -3 -m venv .venv 2>nul
  if errorlevel 1 (
    python -m venv .venv
  )
  if errorlevel 1 (
    echo.
    echo Python was not found. Install Python 3 from https://www.python.org/downloads/windows/
    pause
    exit /b 1
  )
)

echo Checking dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo Could not install dependencies. Check your internet connection, then run this file again.
  pause
  exit /b 1
)

if "%PRO_DOWNLOADER_API_KEY%"=="" (
  set "PRO_DOWNLOADER_API_KEY=change-me"
)

set "FIREWALL_RULE=Pro Downloader PWA - LAN TCP 8000"
powershell.exe -NoProfile -Command "if (Get-NetFirewallRule -DisplayName '%FIREWALL_RULE%' -ErrorAction SilentlyContinue | Where-Object { $_.Enabled -eq 'True' -and $_.Action -eq 'Allow' }) { exit 0 } else { exit 1 }"
if errorlevel 1 (
  echo.
  echo iPhone access needs a one-time Windows Firewall setup.
  call "Enable iPhone Access.bat"
)

for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "$ip = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue ^| Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' -and $_.InterfaceAlias -notmatch 'Loopback|vEthernet' } ^| Sort-Object InterfaceMetric ^| Select-Object -First 1 -ExpandProperty IPAddress; if ($ip) { $ip } else { 'YOUR_PC_IP' }"`) do set "LAN_IP=%%I"

echo Starting Pro Downloader PWA...
echo PC URL:     http://127.0.0.1:8000
echo iPhone URL: http://%LAN_IP%:8000
echo API key: %PRO_DOWNLOADER_API_KEY%
echo.
echo Keep this window open while using the app.
echo If Windows Firewall asks, allow access on Private networks.
echo.

start "" powershell.exe -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8000'"
".venv\Scripts\python.exe" -m pro_downloader_server
pause
