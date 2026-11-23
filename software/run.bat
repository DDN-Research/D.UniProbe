@echo off
REM D.UNI Programmer launcher
cd /d "%~dp0"
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY goto nopython

if exist ".venv\Scripts\python.exe" goto run
echo First start: creating Python environment and installing libraries, please wait...
%PY% -m venv .venv
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto fail

:run
".venv\Scripts\python.exe" duni_programmer.py
if errorlevel 1 pause
exit /b 0

:nopython
echo Python not found. Install Python 3.10 or newer from https://www.python.org/downloads/
echo During installation enable the option: Add python.exe to PATH
pause
exit /b 1

:fail
echo Installation failed. Check the internet connection and try again.
echo To reinstall, delete the .venv folder.
pause
exit /b 1
