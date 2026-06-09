@echo off
setlocal
title Pro Downloader
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Setting up Pro Downloader for the first run...
  py -3 -m venv .venv
  if errorlevel 1 (
    echo.
    echo Python was not found. Install Python 3 from https://www.python.org/downloads/windows/
    pause
    exit /b 1
  )
)

echo Checking dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
  echo.
  echo Could not update pip.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo Could not install dependencies. Check your internet connection, then run this file again.
  pause
  exit /b 1
)

echo Starting Pro Downloader...
if not exist "logs" mkdir "logs"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('pythonw.exe','python.exe') -and $_.CommandLine -like '*reclip_desktop*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>nul
start "" ".venv\Scripts\pythonw.exe" -m reclip_desktop 1>>"logs\launcher.log" 2>&1
exit /b 0
