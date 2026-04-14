import pandas as pd
import hashlib
from pathlib import Path
import sqlite3
import os
from typing import Optional, Dict
from typing import Optional, Dict, List

try:
    from .app_paths import app_data_root
except Exception:
    from app_paths import app_data_root

def hash_password(password: str) -> str:
    """Return SHA-256 hash of a password"""
    return hashlib.sha256(password.encode()).hexdigest()

PROJECT_ROOT = app_data_root()


def get_users_file() -> Path:
    return PROJECT_ROOT / "data" / "users.xlsx"

# Default credentials (can be overridden via environment variables)
DEFAULT_USERNAME = os.getenv("SMS_DEFAULT_USERNAME", "admin")
DEFAULT_PASSWORD = os.getenv("SMS_DEFAULT_PASSWORD", "admin")

def load_users():
    # If users file doesn't exist, create a default admin user automatically
    users_file = get_users_file()
    if not users_file.exists():
        try:
            users_file.parent.mkdir(parents=True, exist_ok=True)
            def h(pw): return hashlib.sha256(pw.encode()).hexdigest()
            df = pd.DataFrame([{'username': DEFAULT_USERNAME, 'password_hash': h(DEFAULT_PASSWORD), 'role': 'admin', 'name': 'Administrator'}])
            df.to_excel(users_file, sheet_name='Users', index=False)
            return df
        except Exception as exc:
            raise RuntimeError(f"Failed to create default users file at {users_file}: {exc}") from exc
    try:
        return pd.read_excel(users_file, sheet_name="Users")
    except Exception as exc:
        raise RuntimeError(f"Failed to read users file {users_file}: {exc}") from exc

def authenticate(username: str, password: str) -> Optional[Dict]:
    """Authenticate against the single default user."""
    if username == DEFAULT_USERNAME and password == DEFAULT_PASSWORD:
        return {"username": DEFAULT_USERNAME, "role": "admin", "name": "Administrator"}
    
    users_df = load_users()

    hashed_input = hash_password(password)

    user = users_df[
        (users_df["username"] == username) &
        (users_df["password_hash"] == hashed_input)
    ]

    if user.empty:
        return None

    return {
        "username": user.iloc[0]["username"],
        "role": user.iloc[0]["role"],
        "name": user.iloc[0]["name"]
    }

def list_users():
    """Return list of usernames in the users file (used by the login UI)."""
    try:
        users_df = load_users()
        return users_df["username"].astype(str).tolist()
    except Exception:
        return [DEFAULT_USERNAME]


def update_user_password(username: str, new_password: str) -> bool:
    """Update the password_hash for a given username in the users.xlsx file.
    Returns True on success, False if the user was not found or on error.
    """
    if username == DEFAULT_USERNAME:
        # Default credentials come from env and cannot be updated via file
        return False
    try:
        users_df = load_users()
    except Exception:
        return False

    mask = users_df["username"] == username
    if not mask.any():
        return False

    users_df.loc[mask, "password_hash"] = hash_password(new_password)
    try:
        users_df.to_excel(get_users_file(), sheet_name="Users", index=False)
        return True
    except Exception:
        return False


def update_username(old_username: str, new_username: str) -> bool:
    """Change the username in the users.xlsx file. Returns True on success."""
    if old_username == DEFAULT_USERNAME:
        return False
    try:
        users_df = load_users()
    except Exception:
        return False

    mask = users_df["username"] == old_username
    if not mask.any():
        return False

    # ensure new_username not already used
    if new_username in users_df["username"].tolist():
        return False

    users_df.loc[mask, "username"] = new_username
    try:
        users_df.to_excel(get_users_file(), sheet_name="Users", index=False)
        return True
    except Exception:
        return False
