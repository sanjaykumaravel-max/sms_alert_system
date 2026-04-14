from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Optional

try:
    from .app_paths import data_path
except Exception:
    from app_paths import data_path


def normalize_sms_phone(raw_phone: Any) -> Optional[str]:
    value = str(raw_phone or "").strip()
    if not value:
        return None

    digits = re.sub(r"\D", "", value)
    if not digits:
        return None

    if len(digits) == 10:
        return f"+91{digits}"
    if len(digits) == 12 and digits.startswith("91"):
        return f"+{digits}"
    if value.startswith("+") and len(digits) >= 11:
        return f"+{digits}"
    if len(digits) >= 11:
        return f"+{digits}"
    return None


def is_placeholder_sms_phone(phone: str) -> bool:
    digits = re.sub(r"\D", "", str(phone or ""))
    if not digits:
        return True
    return digits.startswith("555") or digits in {"0000000000", "1111111111", "1234567890"}


def _candidate_name(candidate: Dict[str, Any], default_name: str = "Operator") -> str:
    return (
        str(candidate.get("name") or candidate.get("username") or candidate.get("email") or default_name).strip()
        or default_name
    )


def collect_sms_recipients(candidates: Iterable[Dict[str, Any]], *, source: str, default_name: str = "Operator") -> List[Dict[str, str]]:
    recipients_by_phone: Dict[str, Dict[str, str]] = {}
    for candidate in candidates or []:
        if not isinstance(candidate, dict):
            continue
        phone = normalize_sms_phone(candidate.get("phone") or candidate.get("operator_phone") or candidate.get("operator"))
        if not phone or is_placeholder_sms_phone(phone):
            continue
        if phone in recipients_by_phone:
            continue
        recipients_by_phone[phone] = {
            "name": _candidate_name(candidate, default_name=default_name),
            "phone": phone,
            "source": source,
        }
    return list(recipients_by_phone.values())


def parse_phone_csv(value: Any, *, source: str, default_name: str = "Contact") -> List[Dict[str, str]]:
    parts = re.split(r"[,\n;]+", str(value or "").strip())
    candidates = [{"name": default_name, "phone": item.strip()} for item in parts if str(item or "").strip()]
    return collect_sms_recipients(candidates, source=source, default_name=default_name)


def merge_recipients(*groups: Iterable[Dict[str, Any]]) -> List[Dict[str, str]]:
    merged: List[Dict[str, Any]] = []
    for group in groups:
        if not group:
            continue
        merged.extend([item for item in group if isinstance(item, dict)])
    return collect_sms_recipients(merged, source="merged")


def _role_match(row: Dict[str, Any], role: Optional[str]) -> bool:
    if not role:
        return True
    row_role = str(row.get("role") or row.get("designation") or "").strip().lower()
    return row_role == str(role).strip().lower()


def _is_operator_active(row: Dict[str, Any], *, include_inactive: bool = False) -> bool:
    if include_inactive:
        return True
    if "active" in row:
        return bool(row.get("active"))
    if "is_active" in row:
        return bool(row.get("is_active"))
    return True


def load_saved_operator_recipients(*, role: Optional[str] = None, include_inactive: bool = False) -> List[Dict[str, str]]:
    try:
        ops_file = data_path("operators.json")
        if not ops_file.exists():
            return []
        payload = json.loads(ops_file.read_text(encoding="utf-8")) or []
        if not isinstance(payload, list):
            return []
        filtered = [
            row
            for row in payload
            if isinstance(row, dict) and _role_match(row, role) and _is_operator_active(row, include_inactive=include_inactive)
        ]
        return collect_sms_recipients(filtered, source="file")
    except Exception:
        return []


def machine_primary_recipient(machine: Dict[str, Any]) -> Optional[Dict[str, str]]:
    phone = normalize_sms_phone(machine.get("operator_phone") or machine.get("operator"))
    if not phone or is_placeholder_sms_phone(phone):
        return None
    return {
        "name": str(machine.get("operator_name") or machine.get("operator") or "Machine Operator").strip() or "Machine Operator",
        "phone": phone,
        "source": "machine",
    }
