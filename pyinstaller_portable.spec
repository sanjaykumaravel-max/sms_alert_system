# -*- mode: python ; coding: utf-8 -*-


APP_BASENAME = "MiningMaintenanceSystem"
ICON_FILE = "assets/icons/OIP.ico"
VERSION_FILE = "installer/windows_version_info.txt"


a = Analysis(
    ["src/main.py"],
    pathex=["src", "."],
    binaries=[],
    datas=[
        ("src/data", "data"),
        ("assets", "assets"),
        (".env.example", "."),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=APP_BASENAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON_FILE,
    version=VERSION_FILE,
)
