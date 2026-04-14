import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import os
import sys

try:
    from .app_paths import logs_dir
except Exception:
    from app_paths import logs_dir

LOG_DIR = logs_dir()
LOG_FILE = LOG_DIR / "app.log"


class RedactingFormatter(logging.Formatter):
    """Formatter that redacts configured secret values from the final formatted message."""

    def __init__(self, fmt: str | None = None, secrets: list | None = None):
        super().__init__(fmt)
        self.secrets = [s for s in (secrets or []) if s]

    def format(self, record: logging.LogRecord) -> str:
        out = super().format(record)
        if not self.secrets:
            return out
        for secret in self.secrets:
            if secret and secret in out:
                out = out.replace(secret, "<REDACTED>")
        return out


def configure_logging(level: str | int = logging.INFO, max_bytes: int = 10_000_00, backup_count: int = 3):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    # avoid adding handlers multiple times
    if root.handlers:
        return
    root.setLevel(level)

    fmt_str = "%(asctime)s %(levelname)s %(name)s: %(message)s"

    # collect secrets from environment that should never appear in logs
    secret_keys = ["SMS_API_KEY", "SERVER_API_KEY", "TWILIO_TOKEN", "TWILIO_SID"]
    secrets = [os.environ.get(k) for k in secret_keys if os.environ.get(k)]

    formatter = RedactingFormatter(fmt_str, secrets=secrets)

    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(formatter)
    root.addHandler(ch)

    fh = RotatingFileHandler(str(LOG_FILE), maxBytes=max_bytes, backupCount=backup_count, encoding='utf-8')
    fh.setLevel(level)
    fh.setFormatter(formatter)
    root.addHandler(fh)

    # Optional Sentry integration if DSN provided in env
    sentry_dsn = os.environ.get('SENTRY_DSN')
    if sentry_dsn:
        try:
            import sentry_sdk
            sentry_sdk.init(dsn=sentry_dsn, traces_sample_rate=0.0)
            root.info('Sentry initialized')
        except Exception:
            root.exception('Failed to initialize Sentry')


def get_logger(name: str = __name__):
    return logging.getLogger(name)


def install_thread_excepthook():
    """Install a sys.excepthook that logs unhandled exceptions from any thread."""
    def handle_exception(exc_type, exc_value, exc_traceback):
        logger = logging.getLogger()
        if exc_type is KeyboardInterrupt:
            # Let KeyboardInterrupt behave normally
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.exception('Uncaught exception', exc_info=(exc_type, exc_value, exc_traceback))
        try:
            # attempt to notify Sentry if present
            import sentry_sdk
            sentry_sdk.capture_exception(exc_value)
        except Exception:
            pass

    sys.excepthook = handle_exception
