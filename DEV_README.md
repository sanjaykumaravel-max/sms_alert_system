Developer quick-start and build commands

Overview
- Use the project venv for development and packaging.
- Prefer running from source for fast iteration; use `onedir` builds during testing and `onefile` for final releases.

Run from source (fast)
```powershell
& .\.venv\Scripts\Activate.ps1
python .\src\main.py
```

Fast onedir build (quick packaging during development)
```powershell
# from project root
scripts\build_onedir.bat
# or (without batch)
& .\.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm --onedir --name sms_alert_app_onedir --paths src --icon "assets\icons\OIP.ico" --add-data ".env;." --add-data "src/data;data" --add-data "assets;assets" --distpath C:\temp\dist_onedir --workpath C:\temp\build_onedir src\main.py
```

Auto-rebuild watcher (rebuilds onedir when files change)
```powershell
& .\.venv\Scripts\Activate.ps1
python .\scripts\watch_rebuild.py
# then run the produced exe:
C:\temp\dist_onedir\sms_alert_app_onedir\sms_alert_app.exe
```

Final release (one-file EXE)
```powershell
& .\.venv\Scripts\Activate.ps1
& .\.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm --onefile --name sms_alert_app --paths src --icon "assets\icons\OIP.ico" --add-data ".env;." --add-data "src/data;data" --add-data "assets;assets" --distpath C:\temp\dist --workpath C:\temp\build src\main.py
```

Notes on `.env` and API keys
- Do NOT include production API keys in public releases. Use `.env.example` for example.
- To run the packaged EXE with your SMS API key, create a `.env` file next to the EXE with:
```
SMS_API_KEY=your_real_api_key_here
```
- Changing `.env` does not require rebuilding the EXE.

Troubleshooting
- "No module named 'ui'": build with `--paths src` (already used in scripts). 
- "Could not load PyInstaller's embedded PKG archive": do not unzip the one-file EXE; run it directly.
- If resources (icons, data) are missing, ensure `--add-data` includes `assets` and `src/data`.

Packaging tips
- Develop by running source or using `onedir` builds.
- Build `onefile` only for final distribution. Use CI to automate reproducible builds and checksums.
