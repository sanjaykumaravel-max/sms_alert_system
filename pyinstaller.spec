# -*- mode: python -*-
block_cipher = None

APP_BASENAME = "MiningMaintenanceSystem"
ICON_FILE = "assets/icons/OIP.ico"
VERSION_FILE = "installer/windows_version_info.txt"

a = Analysis([
    'src/main.py',
],
    pathex=['src', '.'],
    binaries=[],
    datas=[
        ('src/data', 'data'),
        ('assets', 'assets'),
        ('.env.example', '.'),
    ],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name=APP_BASENAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=ICON_FILE,
    version=VERSION_FILE,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_BASENAME,
)
