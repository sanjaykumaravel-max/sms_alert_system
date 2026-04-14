@echo off
set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"

if not exist "%ISCC%" (
  echo Inno Setup compiler not found.
  echo Install Inno Setup 6 and run this script again.
  exit /b 1
)

"%ISCC%" installer\MiningMaintenanceSystem.iss
echo Installer build finished. Check the releases folder.
pause
