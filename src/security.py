"""Secure storage helpers for secrets using keyring with environment fallback.

This module provides a simple wrapper around the `keyring` library to store
and retrieve secrets (API keys, tokens) in an OS-backed secure store. When
`keyring` isn't available or fails, it falls back to environment variables.

Usage:
    from security import get_secret, set_secret
    set_secret('sms_alert_app', 'SMS_API_KEY', 'abcd')
    key = get_secret('sms_alert_app', 'SMS_API_KEY')
"""
from typing import Optional
import os
import logging

LOG = logging.getLogger(__name__)

try:
    import keyring
except Exception:
    keyring = None


def get_secret(service: str, name: str) -> Optional[str]:
    """Return secret from keyring if available, else fallback to env var NAME."""
    try:
        if keyring:
            try:
                val = keyring.get_password(service, name)
                if val:
                    return val
            except Exception:
                LOG.exception('keyring get_password failed')
        # fallback to environment variable
        return os.environ.get(name)
    except Exception:
        LOG.exception('get_secret failed')
        return None


def set_secret(service: str, name: str, value: str) -> bool:
    """Store secret using keyring if available, else set environment variable (best-effort)."""
    try:
        if keyring:
            try:
                keyring.set_password(service, name, value)
                return True
            except Exception:
                LOG.exception('keyring set_password failed')
        # fallback to environment variable (best-effort only)
        try:
            os.environ[name] = value
            return True
        except Exception:
            LOG.exception('environment fallback set failed')
            return False
    except Exception:
        LOG.exception('set_secret failed')
        return False
