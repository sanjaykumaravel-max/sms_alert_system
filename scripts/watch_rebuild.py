"""
Lightweight file-watcher that rebuilds an onedir PyInstaller bundle when source
files change. Designed to be run from the project root using the project's venv
Python, e.g.

    & .\.venv\Scripts\Activate.ps1
    python .\scripts\watch_rebuild.py

The script calls `python -m PyInstaller` using the interpreter executing this
script, so activate your venv before running.
"""
import time
import subprocess
import sys
from pathlib import Path

WATCH_PATHS = [Path('src'), Path('assets')]
EXCLUDE_EXT = {'.pyc', '.pyo', '.swp'}
DEBOUNCE_SEC = 1.0
BUILD_CMD = [
    sys.executable,
    '-m', 'PyInstaller',
    '--clean',
    '--noconfirm',
    '--onedir',
    '--name', 'sms_alert_app_onedir',
    '--paths', 'src',
    '--icon', str(Path('assets/icons/OIP.ico')),
    '--add-data', '.env;.',
    '--add-data', 'src/data;data',
    '--add-data', 'assets;assets',
    '--distpath', 'C:\\temp\\dist_onedir',
    '--workpath', 'C:\\temp\\build_onedir',
    'src/main.py',
]


def scan_files(paths):
    result = {}
    for p in paths:
        if not p.exists():
            continue
        for f in p.rglob('*'):
            if f.is_file() and f.suffix not in EXCLUDE_EXT:
                try:
                    result[str(f)] = f.stat().st_mtime
                except OSError:
                    pass
    return result


def do_build():
    print('Starting onedir build:', ' '.join(BUILD_CMD))
    proc = subprocess.run(BUILD_CMD)
    print('Build finished, returncode=', proc.returncode)


if __name__ == '__main__':
    print('watch_rebuild: monitoring', ', '.join(str(p) for p in WATCH_PATHS))
    last = scan_files(WATCH_PATHS)
    while True:
        time.sleep(DEBOUNCE_SEC)
        now = scan_files(WATCH_PATHS)
        if now != last:
            print('Change detected — rebuilding...')
            do_build()
            last = now
        # else continue watching
