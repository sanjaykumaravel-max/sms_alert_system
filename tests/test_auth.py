import os
from pathlib import Path
import hashlib
import pandas as pd
import pytest

from src import auth


def test_hash_password_consistent():
    h1 = auth.hash_password('password')
    h2 = hashlib.sha256('password'.encode()).hexdigest()
    assert h1 == h2


def test_load_users_creates_file(tmp_path):
    # point PROJECT_ROOT to tmp_path by monkeypatching module variable
    orig_root = auth.PROJECT_ROOT
    try:
        auth.PROJECT_ROOT = Path(tmp_path)
        users_file = auth.PROJECT_ROOT / 'data' / 'users.xlsx'
        if users_file.exists():
            users_file.unlink()
        df = auth.load_users()
        assert users_file.exists()
        assert 'username' in df.columns
    finally:
        auth.PROJECT_ROOT = orig_root


def test_authenticate_default():
    # default admin/admin should authenticate
    user = auth.authenticate(auth.DEFAULT_USERNAME, auth.DEFAULT_PASSWORD)
    assert user is not None
    assert user['username'] == auth.DEFAULT_USERNAME
