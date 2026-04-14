Packaging and Installer Guidance

This document describes recommended steps to build and distribute the desktop application for Windows (PyInstaller + Inno Setup) and notes about cross-platform options.

1) Build a distributable with PyInstaller (Windows)

- Create a virtualenv and install requirements (from project root):

```bash
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt
```

- Create a single-folder or single-file build using the existing spec files (examples in repo):

```bash
# one-folder
pyinstaller --clean --noconfirm sms_alert_app.spec
# or one-file (adjust spec)
pyinstaller --onefile src/main.py
```

- Test the generated exe in `dist/` thoroughly.

2) Create an installer (Inno Setup)

- Use the `installer/sms_alert_installer.iss` as a starting template.
- Compile using Inno Setup Compiler (ISCC) on Windows. Example:

```powershell
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\sms_alert_installer.iss
```

- Sign the installer using your code signing certificate (SignTool or other):

```powershell
signtool sign /fd SHA256 /a /f path\to\cert.pfx /p <password> output_installer.exe
```

3) Alternative: Briefcase

- For cross-platform native installers, consider `briefcase` (BeeWare) to build platform-specific bundles.

4) CI Notes

- Add a Windows runner that builds the wheel or PyInstaller artifact, then runs Inno Setup.
- Keep signing credentials in secure secrets and sign on a build agent.

5) Sentry and Release Tracking

- If using Sentry, set `SENTRY_DSN` in build/runtime environment.
- Optionally include `release` and `dist` metadata when initializing Sentry in the app.

6) Testing & Linting

- Run tests with `pytest` and static checks with `ruff` and `mypy` before packaging:

```bash
pytest -q
ruff check .
mypy src
```

7) Post-build verification

- Smoke test the installer on a clean VM, verify the app runs, settings persist, and background services start as expected.

---

If you want, I can add a GitHub Actions workflow skeleton to automate builds and signing (requires secrets). Tell me which CI provider and target platforms to include.