import zipfile
import hashlib
import os
from pathlib import Path
from datetime import datetime

repo = Path.cwd()
release_dir = repo / 'releases'
release_dir.mkdir(exist_ok=True)
exe_path = Path('C:/temp/dist/sms_alert_app.exe')
if not exe_path.exists():
    print('ERROR: EXE not found at', exe_path)
    raise SystemExit(1)

ts = datetime.now().strftime('%Y%m%d_%H%M')
zip_name = release_dir / f'sms_alert_app_release_{ts}.zip'
with zipfile.ZipFile(zip_name, 'w', compression=zipfile.ZIP_DEFLATED) as z:
    # Add exe
    z.write(exe_path, arcname='sms_alert_app.exe')
    # Add example env
    z.writestr('.env.example', 'SMS_API_KEY=your_api_key_here')
    # Add README
    readme = (
        'README for sms_alert_app release\n\n'
        'Contents:\n- sms_alert_app.exe  (one-file Windows EXE)\n- .env.example       (example; fill SMS_API_KEY)\n\n'
        'Usage:\n1) Extract the ZIP to a folder.\n2) Create a file named .env in the same folder as the EXE with:\n   SMS_API_KEY=your_real_api_key_here\n3) Run sms_alert_app.exe (do NOT unzip the EXE).\n\n'
        'Do NOT commit or distribute your real API key.\n'
    )
    z.writestr('README.txt', readme)

# compute sha256
h = hashlib.sha256()
with open(zip_name, 'rb') as f:
    for chunk in iter(lambda: f.read(8192), b''):
        h.update(chunk)
print('Created:', zip_name)
print('SHA256:', h.hexdigest())
# list releases
for p in release_dir.iterdir():
    print(p.name, p.stat().st_size)
