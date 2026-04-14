@echo off
REM Fast onedir build helper for Windows (run from project root)
REM Activate your venv first (PowerShell): & .\.venv\Scripts\Activate.ps1

set PYTHON=.\.venv\Scripts\python.exe
if not exist %PYTHON% set PYTHON=python

"%PYTHON%" -m PyInstaller --clean --noconfirm --onedir --name sms_alert_app_onedir --paths src --icon "%~dp0..\assets\icons\OIP.ico" --add-data ".env;." --add-data "src/data;data" --add-data "assets;assets" --distpath C:\temp\dist_onedir --workpath C:\temp\build_onedir src\main.py
if %ERRORLEVEL% neq 0 (
  echo PyInstaller failed with exit code %ERRORLEVEL%
  exit /b %ERRORLEVEL%
)

echo Build complete. Output: C:\temp\dist_onedir\sms_alert_app_onedir\
