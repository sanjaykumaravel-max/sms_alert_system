"""Common form validation helpers for the UI."""
import re
from typing import Optional
import tkinter as tk
from tkinter import messagebox

try:
    from ..machine_store import parse_machine_date
    from ..sms_contacts import normalize_sms_phone
except Exception:
    from machine_store import parse_machine_date
    from sms_contacts import normalize_sms_phone


PHONE_RE = re.compile(r"^\+?\d{7,15}$")


def _show_validation_error(message: str, *, show_error: bool = True) -> None:
    if not show_error:
        return
    try:
        messagebox.showerror("Validation", message)
    except Exception:
        pass


def validate_required(value: str, field_name: str, *, show_error: bool = True) -> bool:
    if value is None or str(value).strip() == "":
        _show_validation_error(f"{field_name} is required", show_error=show_error)
        return False
    return True


def normalize_phone_input(value: str) -> Optional[str]:
    normalized = normalize_sms_phone(value)
    if normalized:
        return normalized
    raw = str(value or "").strip()
    if PHONE_RE.match(raw):
        return raw if raw.startswith("+") else f"+{raw}"
    return None


def validate_phone(value: str, field_name: str = "Phone", *, show_error: bool = True) -> bool:
    if not value:
        _show_validation_error(f"{field_name} is required", show_error=show_error)
        return False
    if normalize_phone_input(value):
        return True
    _show_validation_error(
        f"{field_name} must be a valid phone number, e.g. +911234567890",
        show_error=show_error,
    )
    return False


def validate_optional_phone(value: str, field_name: str = "Phone", *, show_error: bool = True) -> bool:
    raw = str(value or "").strip()
    if not raw:
        return True
    return validate_phone(raw, field_name=field_name, show_error=show_error)


def normalize_date_input(value: str) -> Optional[str]:
    parsed = parse_machine_date(value)
    if not parsed:
        return None
    return parsed.isoformat()


def validate_date_string(
    value: str,
    field_name: str,
    *,
    required: bool = False,
    show_error: bool = True,
) -> bool:
    raw = str(value or "").strip()
    if not raw:
        if required:
            _show_validation_error(f"{field_name} is required", show_error=show_error)
            return False
        return True
    if normalize_date_input(raw):
        return True
    _show_validation_error(
        f"{field_name} must use a valid date such as YYYY-MM-DD",
        show_error=show_error,
    )
    return False


def validate_number(
    value: str,
    field_name: str,
    *,
    required: bool = False,
    minimum: Optional[float] = None,
    show_error: bool = True,
) -> bool:
    raw = str(value or "").strip()
    if not raw:
        if required:
            _show_validation_error(f"{field_name} is required", show_error=show_error)
            return False
        return True
    try:
        number = float(raw)
    except Exception:
        _show_validation_error(f"{field_name} must be a valid number", show_error=show_error)
        return False
    if minimum is not None and number < minimum:
        _show_validation_error(
            f"{field_name} must be at least {minimum}",
            show_error=show_error,
        )
        return False
    return True
