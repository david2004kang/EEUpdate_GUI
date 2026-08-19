@echo off
cd /d "%~dp0"

net session >nul 2>&1
if %errorLevel% neq 0 (
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

set "PYW=%~dp0venv\Scripts\pythonw.exe"
if exist "%PYW%" (
    start "" "%PYW%" "%~dp0main.py"
    exit /b 0
)

where pythonw >nul 2>&1
if %errorLevel%==0 (
    start "" pythonw "%~dp0main.py"
    exit /b 0
)

where python >nul 2>&1
if %errorLevel%==0 (
    python "%~dp0main.py"
    exit /b 0
)

echo Python not found. Install Python or create a venv in this folder.
pause
