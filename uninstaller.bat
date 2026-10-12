@echo off
setlocal
cd /d "%~dp0"
title BiRef Studio - Kaldirma
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstaller.ps1" %*
exit /b %errorlevel%
