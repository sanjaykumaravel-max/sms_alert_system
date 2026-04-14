@echo off
setlocal enabledelayedexpansion

echo Ensuring required packages are installed...
python -m pip install --upgrade pip
pip install -r requirements-prod.txt
pip install pyinstaller

rem Build settings
set "BUILD_DIST=C:\temp\dist"
set "BUILD_WORK=C:\temp\build"
set "RELEASES_DIR=%~dp0..\releases"

rem Resolve icon path relative to repo root
set "SCRIPT_DIR=%~dp0"
set "ICON_PATH=%SCRIPT_DIR%..\assets\icons\OIP.ico"

echo Removing any stale spec files to avoid incorrect icon references...
if exist %~dp0sms_alert_app.spec del /f /q %~dp0sms_alert_app.spec

echo Cleaning previous build artifacts (may require admin if locked)...
Remove-Item -Recurse -Force "%BUILD_WORK%" -ErrorAction SilentlyContinue >nul 2>&1
Remove-Item -Recurse -Force "%BUILD_DIST%" -ErrorAction SilentlyContinue >nul 2>&1
Remove-Item -Recurse -Force "%RELEASES_DIR%" -ErrorAction SilentlyContinue >nul 2>&1

echo Building one-file EXE to %BUILD_DIST% (debug log to console)...
python -m PyInstaller --clean --noconfirm --onefile --name sms_alert_app --icon "%ICON_PATH%" --add-data ".env;." --add-data "src/data;data" --add-data "assets;assets" --distpath "%BUILD_DIST%" --workpath "%BUILD_WORK%" --log-level=DEBUG --noupx src\main.py

if not exist "%BUILD_DIST%\sms_alert_app.exe" (
  echo Build failed: %BUILD_DIST%\sms_alert_app.exe not found
  exit /b 1
)

echo Preparing releases folder and zipping EXE...
if not exist "%RELEASES_DIR%" mkdir "%RELEASES_DIR%"

powershell -Command "Compress-Archive -Force -Path '%BUILD_DIST%\\sms_alert_app.exe' -DestinationPath '%RELEASES_DIR%\\sms_alert_app_v%date:~10,4%-%date:~4,2%-%date:~7,2%.zip'"

echo Release created in %RELEASES_DIR%\ directory.
endlocal
