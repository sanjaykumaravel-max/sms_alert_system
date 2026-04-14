import os
import sys
import logging
from dotenv import load_dotenv
from pathlib import Path

try:
    from .app_paths import APP_DIR_NAME, data_path, env_file_candidates
except Exception:
    from app_paths import APP_DIR_NAME, data_path, env_file_candidates

# Load environment from the first available external config file so packaged
# builds work outside the source tree.
env_dir = None
for dotenv_path in env_file_candidates():
    if dotenv_path.exists():
        load_dotenv(dotenv_path, override=False)
        env_dir = dotenv_path.parent
        break
if env_dir is None:
    env_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent

# Read API key from environment. Do not raise at import time — warn instead so the
# application can still start (features that require an API key will raise when used).
API_KEY = os.getenv("SMS_API_KEY")
if API_KEY is not None:
    API_KEY = API_KEY.strip()
else:
    logging.getLogger(__name__).warning("SMS_API_KEY not set. Add it to .env or set environment variable.")

# ===== Application Configuration =====

APP_NAME = "Mining Maintenance System"
APP_VERSION = "1.0.0"
APP_EXECUTABLE_NAME = APP_DIR_NAME

# Excel file paths
EXCEL_MAIN_FILE = str(data_path("OpenCast_Mining_Maintenance_Excel_Templates.xlsx"))
USERS_FILE = str(data_path("users.xlsx"))

# SMS settings
SMS_ENABLED = True        # Enabled for sending alerts (set to False to disable)
# Use the API key loaded from environment/.env (may be None)
SMS_API_KEY = API_KEY
# Determine SMS sender id (what recipients see as the sender). Order of precedence:
# 1. Environment variable `SMS_SENDER_ID`
# 2. src/data/config.json -> key `SMS_DEFAULT_SENDER`
# 3. fallback default 'alert_message'
_sender = os.getenv("SMS_SENDER_ID")
if not _sender:
    try:
        cfg_path = data_path("config.json")
        if cfg_path.exists():
            import json as _json
            with open(cfg_path, "r", encoding="utf-8") as _f:
                _cfg = _json.load(_f)
            _sender = _cfg.get("SMS_DEFAULT_SENDER")
    except Exception:
        _sender = None

if not _sender:
    _sender = "alert_message"

SMS_SENDER_ID = _sender

# Provide a convenient Settings object for new code while keeping the
# module-level constants for backward compatibility.
try:
    from pydantic import BaseSettings, Field

    class Settings(BaseSettings):
        ENV: str = Field("development")
        SMS_ENABLED: bool = Field(True)
        SMS_API_KEY: str | None = Field(API_KEY, env="SMS_API_KEY")
        SMS_SENDER_ID: str | None = Field(SMS_SENDER_ID, env="SMS_SENDER_ID")
        AUTO_START_API_SERVER: bool = Field(os.getenv('AUTO_START_API_SERVER', '1') not in ('0', 'false', 'no'))
        API_HOST: str = Field(os.getenv('API_HOST', '0.0.0.0'))
        API_PORT: int = Field(int(os.getenv('API_PORT', '8000')))
        TWILIO_SID: str | None = Field(os.getenv('TWILIO_SID'))
        TWILIO_TOKEN: str | None = Field(os.getenv('TWILIO_TOKEN'))

        class Config:
            env_file = env_dir / ".env"

    settings = Settings()
except Exception:
    settings = None
