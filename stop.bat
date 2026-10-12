@echo off
setlocal
set "STUDIO_STOP_SCRIPT=%~dp0stop.ps1"
start "" /b powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "%STUDIO_STOP_SCRIPT%"
exit /b
