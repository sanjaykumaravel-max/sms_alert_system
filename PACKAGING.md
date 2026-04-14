Packaging & Server Mode
======================

Build a single-file executable (PyInstaller):

```bash
# On Linux/macOS
./scripts/build_pyinstaller.sh

# On Windows (PowerShell)
.\scripts\build_pyinstaller.bat
```

Docker (server mode):

```bash
# Build image
docker build -t sms-alert-server:latest .

# Run (set your Fast2SMS API key and optional SERVER_API_KEY)
docker run -e SMS_API_KEY=your_key -e SERVER_API_KEY=your_server_key -p 8000:8000 sms-alert-server:latest
```

The Docker image runs a minimal Flask server exposing `/send` (POST json `{to, message}`) and `/health`.
