@echo off
REM Build the single-file portable Windows EXE
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe -m PyInstaller --clean -y --distpath dist_portable --workpath build_portable pyinstaller_portable.spec
) else (
  python -m PyInstaller --clean -y --distpath dist_portable --workpath build_portable pyinstaller_portable.spec
)
echo Portable build finished. Output is in the dist_portable folder.
pause
