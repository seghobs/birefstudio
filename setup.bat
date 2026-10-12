@echo off
setlocal
cd /d "%~dp0"
title BiRef Studio - Otomatik Kurulum
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
exit /b %errorlevel%
