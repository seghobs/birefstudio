@echo off
setlocal
cd /d "%~dp0"
title BiRef Studio
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" launcher.py
    goto finished
)
if exist ".tools\python\python.exe" (
    ".tools\python\python.exe" launcher.py
    goto finished
)
where py >nul 2>nul
if errorlevel 1 goto fallback
py -3.12 -c "import sys" >nul 2>nul
if errorlevel 1 goto python313
py -3.12 launcher.py
goto finished
:python313
py -3.13 -c "import sys" >nul 2>nul
if errorlevel 1 goto fallback
py -3.13 launcher.py
goto finished
:fallback
where python >nul 2>nul
if errorlevel 1 (
    echo Python bulunamadi. Python 3.12 kurun ve PATH secenegini isaretleyin.
    echo https://www.python.org/downloads/
    pause
    exit /b 1
)
python launcher.py
:finished
if errorlevel 1 (
    echo.
    echo Baslatma tamamlanamadi. Hata mesajini kontrol edin.
    pause
    exit /b 1
)
endlocal
