@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -m pip install --upgrade -r requirements.txt
pause
