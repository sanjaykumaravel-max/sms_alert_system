Environment & quick usage

- Copy `.env.example` -> `.env` and set values:
  - `SMS_API_KEY` - Fast2SMS API key (or leave blank to use mock)
  - `SMS_PROVIDER` - `fast2sms`, `twilio`, or `mock`
  - `TWILIO_SID`, `TWILIO_TOKEN` - required for Twilio fallback
  - `API_HOST`, `API_PORT` - API server host/port
  - `GOOGLE_LOGIN_ENABLED` - `true` to enable Google login
  - `GOOGLE_CLIENT_ID` - OAuth client ID from Google Cloud Console
  - `GOOGLE_CLIENT_SECRET` - optional for desktop PKCE flow, but recommended
  - `GOOGLE_ALLOWED_DOMAINS` - optional comma-separated domain allowlist
  - `GOOGLE_ADMIN_EMAILS` - optional comma-separated emails that should be admin
  - `GOOGLE_DEFAULT_ROLE` - role assigned to Google users (default `operator`)

Run tests (only unit tests in `tests/` are collected):

```bash
.venv/Scripts/activate
python -m pytest -q
```

To run the GUI locally (requires Tk/Tcl):

```bash
.venv/Scripts/activate
python -m src.main
```

Notes:
- The app now uses a lightweight SQLite DB at `data/app.db` by default.
- SMS sends are audited to the `sms_audit` table; use `src.db.migrate_json_to_db(...)` to import legacy JSON if needed.

Google OAuth setup:
- In Google Cloud Console create an OAuth client of type Desktop app.
- Add your generated `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` to `.env`.
- Start the app and click `Continue with Google` on the login screen.
