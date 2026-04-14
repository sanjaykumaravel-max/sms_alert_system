@echo off
REM Build the branded Windows desktop app (folder-based)
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe -m PyInstaller --clean -y pyinstaller.spec
) else (
  python -m PyInstaller --clean -y pyinstaller.spec
)
echo Build finished. Output is in the dist\MiningMaintenanceSystem folder.
pause
