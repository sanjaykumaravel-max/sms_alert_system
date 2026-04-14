from __future__ import annotations

import json
from datetime import datetime, date, timedelta
from typing import Any, Dict, List

try:
    from .app_paths import data_path
except Exception:
    from app_paths import data_path


MACHINES_FILE = data_path("machines.json")

DEFAULT_COLUMNS = [
    "id",
    "type",
    "model",
    "hours",
    "current_hours",
    "status",
    "registration_number",
    "company",
    "purchase_date",
    "service_date",
    "due_date",
    "maintenance_status",
    "next_maintenance",
    "name",
    "notes",
    "operator",
    "operator_phone",
    "shift",
    "service_interval_hours",
    "next_due_hours",
    "hour_alert_window",
    "hour_overdue_after_hours",
    "last_hour_entry_at",
    "last_hour_reading",
    "last_runtime_hours",
    "last_maintenance_completed_at",
    "last_maintenance_status",
    "maintenance_history",
    "engine_oil_interval",
    "hydraulic_oil_interval",
    "gearbox_oil_interval",
    "created_at",
    "last_updated",
    "archived",
    "deleted_at",
]


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _blank_machine() -> Dict[str, Any]:
    return {col: None for col in DEFAULT_COLUMNS}


def normalize_machine_record(record: Dict[str, Any]) -> Dict[str, Any]:
    machine = _blank_machine()
    machine.update(record or {})

    machine["id"] = str(machine.get("id") or "").strip()
    machine["name"] = str(machine.get("name") or machine.get("model") or machine["id"]).strip()
    machine["type"] = str(machine.get("type") or "Machine").strip()
    machine["status"] = str(machine.get("status") or "normal").strip().lower()
    if machine.get("current_hours") in (None, "", "None"):
        machine["current_hours"] = machine.get("hours")

    maintenance_status = machine.get("maintenance_status")
    if not maintenance_status:
        machine["maintenance_status"] = machine["status"]
    history = machine.get("maintenance_history")
    if isinstance(history, list):
        machine["maintenance_history"] = [item for item in history if isinstance(item, dict)]
    else:
        machine["maintenance_history"] = []

    now = _now_iso()
    if not machine.get("created_at"):
        machine["created_at"] = now
    machine["last_updated"] = now
    machine["archived"] = bool(machine.get("archived", False))
    if machine.get("deleted_at") in ("", "None"):
        machine["deleted_at"] = None
    return machine


def parse_machine_date(value: Any) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except Exception:
            continue
    try:
        return datetime.fromisoformat(raw).date()
    except Exception:
        return None


def parse_machine_hours(value: Any) -> float | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except Exception:
        return None


def machine_current_hours(machine: Dict[str, Any]) -> float | None:
    for key in ("current_hours", "hour_reading", "operating_hours", "hours", "meter"):
        current = parse_machine_hours(machine.get(key))
        if current is not None:
            return current
    return None


def machine_next_due_hours(machine: Dict[str, Any]) -> float | None:
    return parse_machine_hours(machine.get("next_due_hours"))


def machine_service_interval_hours(machine: Dict[str, Any]) -> float | None:
    for key in ("service_interval_hours", "engine_oil_interval", "hydraulic_oil_interval", "gearbox_oil_interval"):
        interval = parse_machine_hours(machine.get(key))
        if interval is not None and interval > 0:
            return interval
    return None


def machine_hour_alert_window(machine: Dict[str, Any]) -> float:
    explicit = parse_machine_hours(machine.get("hour_alert_window"))
    if explicit is not None and explicit >= 0:
        return explicit
    interval = machine_service_interval_hours(machine)
    if interval is not None:
        return max(5.0, min(interval * 0.1, 50.0))
    return 10.0


def machine_hour_overdue_after(machine: Dict[str, Any]) -> float:
    explicit = parse_machine_hours(machine.get("hour_overdue_after_hours"))
    if explicit is not None and explicit >= 0:
        return explicit
    interval = machine_service_interval_hours(machine)
    if interval is not None:
        return max(1.0, min(interval * 0.05, 24.0))
    return 2.0


def machine_due_date(machine: Dict[str, Any]) -> date | None:
    return parse_machine_date(machine.get("due_date")) or parse_machine_date(machine.get("next_maintenance"))


def machine_history(machine: Dict[str, Any]) -> List[Dict[str, Any]]:
    history = machine.get("maintenance_history")
    if not isinstance(history, list):
        return []
    rows = [item for item in history if isinstance(item, dict)]
    return sorted(rows, key=lambda item: str(item.get("completed_at") or ""), reverse=True)


def _maintenance_cycle_days(machine: Dict[str, Any], *, default_days: int = 30) -> int:
    due = machine_due_date(machine)
    service_date = (
        parse_machine_date(machine.get("service_date"))
        or parse_machine_date(machine.get("purchase_date"))
    )
    if due is not None and service_date is not None:
        delta = (due - service_date).days
        if delta > 0:
            return delta
    return max(1, int(default_days))


def evaluate_machine_status(machine: Dict[str, Any], *, reminder_days: int = 3, overdue_after_days: int = 2) -> Dict[str, Any]:
    manual_status = str(machine.get("status") or "normal").strip().lower()
    if manual_status == "critical":
        return {"status": "critical", "trigger": "manual", "source": "manual"}

    ranking = {"normal": 0, "maintenance": 1, "due": 2, "overdue": 3, "critical": 4}
    candidates: List[Dict[str, Any]] = [{"status": manual_status or "normal", "trigger": "manual", "source": "manual"}]

    due = machine_due_date(machine)
    if due:
        today = datetime.now().date()
        if today >= due + timedelta(days=max(1, overdue_after_days)):
            candidates.append({"status": "overdue", "trigger": "date", "source": "date", "due_date": due.isoformat()})
        elif today >= due:
            candidates.append({"status": "due", "trigger": "date", "source": "date", "due_date": due.isoformat()})
        elif today >= due - timedelta(days=max(1, reminder_days)):
            candidates.append({"status": "maintenance", "trigger": "date", "source": "date", "due_date": due.isoformat()})

    current_hours = machine_current_hours(machine)
    due_hours = machine_next_due_hours(machine)
    if current_hours is not None and due_hours is not None:
        overdue_after_hours = machine_hour_overdue_after(machine)
        alert_window = machine_hour_alert_window(machine)
        if current_hours >= due_hours + overdue_after_hours:
            candidates.append(
                {
                    "status": "overdue",
                    "trigger": "hours",
                    "source": "hours",
                    "current_hours": current_hours,
                    "next_due_hours": due_hours,
                }
            )
        elif current_hours >= due_hours:
            candidates.append(
                {
                    "status": "due",
                    "trigger": "hours",
                    "source": "hours",
                    "current_hours": current_hours,
                    "next_due_hours": due_hours,
                }
            )
        elif current_hours >= max(0.0, due_hours - alert_window):
            candidates.append(
                {
                    "status": "maintenance",
                    "trigger": "hours",
                    "source": "hours",
                    "current_hours": current_hours,
                    "next_due_hours": due_hours,
                }
            )

    best = max(candidates, key=lambda item: ranking.get(str(item.get("status") or "normal"), 0))
    if "current_hours" not in best and current_hours is not None:
        best["current_hours"] = current_hours
    if "next_due_hours" not in best and due_hours is not None:
        best["next_due_hours"] = due_hours
    if "due_date" not in best and due is not None:
        best["due_date"] = due.isoformat()
    return best


def effective_machine_status(machine: Dict[str, Any], *, reminder_days: int = 3, overdue_after_days: int = 2) -> str:
    return str(
        evaluate_machine_status(
            machine,
            reminder_days=reminder_days,
            overdue_after_days=overdue_after_days,
        ).get("status")
        or "normal"
    )


def complete_machine_maintenance(
    machine: Dict[str, Any],
    *,
    completed_at: datetime | None = None,
    default_cycle_days: int = 30,
    completed_by: str | None = None,
    completion_notes: str | None = None,
) -> Dict[str, Any]:
    completed_at = completed_at or datetime.now()
    row = normalize_machine_record(machine)
    current_hours = machine_current_hours(row)
    interval_hours = machine_service_interval_hours(row)
    cycle_days = _maintenance_cycle_days(row, default_days=default_cycle_days)
    completed_date = completed_at.date().isoformat()
    previous_service_date = row.get("service_date") or ""
    previous_due_date = machine_due_date(row)
    previous_next_due_hours = machine_next_due_hours(row)
    previous_status = str(row.get("status") or "normal").strip().lower()
    status_context = evaluate_machine_status(row)

    row["last_maintenance_completed_at"] = completed_at.isoformat(timespec="seconds")
    row["last_maintenance_status"] = previous_status
    row["service_date"] = completed_date
    row["status"] = "normal"
    row["maintenance_status"] = "normal"
    next_date = None

    if machine_due_date(row) is not None or row.get("due_date") or row.get("next_maintenance"):
        next_date = (completed_at.date() + timedelta(days=cycle_days)).isoformat()
        row["due_date"] = next_date
        row["next_maintenance"] = next_date

    rolled_next_due_hours = None
    if interval_hours is not None and current_hours is not None:
        rolled_next_due_hours = round(current_hours + interval_hours, 2)
        row["next_due_hours"] = rolled_next_due_hours
        row["hours"] = round(current_hours, 2)
        row["current_hours"] = round(current_hours, 2)

    history = machine_history(row)
    history.insert(
        0,
        {
            "event_id": completed_at.strftime("%Y%m%d%H%M%S"),
            "completed_at": completed_at.isoformat(timespec="seconds"),
            "machine_id": row.get("id") or "",
            "machine_name": row.get("name") or row.get("model") or row.get("id") or "",
            "completed_by": str(completed_by or "").strip(),
            "completion_notes": str(completion_notes or "").strip(),
            "previous_status": previous_status,
            "trigger": status_context.get("trigger") or "",
            "source": status_context.get("source") or "",
            "service_date_before": previous_service_date,
            "due_date_before": previous_due_date.isoformat() if previous_due_date else "",
            "next_due_hours_before": previous_next_due_hours,
            "current_hours": current_hours,
            "service_interval_hours": interval_hours,
            "rolled_due_date": next_date or "",
            "rolled_next_due_hours": rolled_next_due_hours,
        },
    )
    row["maintenance_history"] = history[:200]

    row["last_updated"] = completed_at.isoformat(timespec="seconds")
    return normalize_machine_record(row)


def load_machines(*, include_archived: bool = False) -> List[Dict[str, Any]]:
    try:
        if not MACHINES_FILE.exists():
            return []
        payload = json.loads(MACHINES_FILE.read_text(encoding="utf-8")) or []
        if not isinstance(payload, list):
            return []
        rows = [normalize_machine_record(item) for item in payload if isinstance(item, dict)]
        if include_archived:
            return rows
        return [row for row in rows if not row.get("archived") and not row.get("deleted_at")]
    except Exception:
        return []


def save_machines(rows: List[Dict[str, Any]]) -> None:
    MACHINES_FILE.parent.mkdir(parents=True, exist_ok=True)
    normalized = [normalize_machine_record(row) for row in (rows or []) if isinstance(row, dict)]
    MACHINES_FILE.write_text(json.dumps(normalized, indent=2), encoding="utf-8")


def upsert_machine(record: Dict[str, Any]) -> Dict[str, Any]:
    row = normalize_machine_record(record)
    rows = load_machines(include_archived=True)
    replaced = False
    for idx, existing in enumerate(rows):
        if str(existing.get("id") or "").strip() == row["id"]:
            created_at = existing.get("created_at") or row.get("created_at")
            row["created_at"] = created_at
            rows[idx] = row
            replaced = True
            break
    if not replaced:
        rows.append(row)
    save_machines(rows)
    return row


def update_maintenance_history_entry(
    machine_id: str,
    event_id: str,
    updates: Dict[str, Any],
) -> Dict[str, Any] | None:
    rows = load_machines(include_archived=True)
    machine_key = str(machine_id or "").strip()
    event_key = str(event_id or "").strip()
    for idx, machine in enumerate(rows):
        if str(machine.get("id") or "").strip() != machine_key:
            continue
        normalized = normalize_machine_record(machine)
        history = machine_history(normalized)
        changed = False
        for item in history:
            item_key = str(item.get("event_id") or item.get("completed_at") or "").strip()
            if item_key != event_key:
                continue
            for key, value in (updates or {}).items():
                item[key] = value
            changed = True
            break
        if not changed:
            return None
        normalized["maintenance_history"] = history
        normalized["last_updated"] = _now_iso()
        rows[idx] = normalize_machine_record(normalized)
        save_machines(rows)
        return rows[idx]
    return None


def delete_maintenance_history_entry(machine_id: str, event_id: str) -> Dict[str, Any] | None:
    rows = load_machines(include_archived=True)
    machine_key = str(machine_id or "").strip()
    event_key = str(event_id or "").strip()
    for idx, machine in enumerate(rows):
        if str(machine.get("id") or "").strip() != machine_key:
            continue
        normalized = normalize_machine_record(machine)
        history = machine_history(normalized)
        filtered = [
            item for item in history
            if str(item.get("event_id") or item.get("completed_at") or "").strip() != event_key
        ]
        if len(filtered) == len(history):
            return None
        normalized["maintenance_history"] = filtered
        normalized["last_updated"] = _now_iso()
        rows[idx] = normalize_machine_record(normalized)
        save_machines(rows)
        return rows[idx]
    return None


def rollback_maintenance_history_entry(machine_id: str, event_id: str) -> Dict[str, Any] | None:
    rows = load_machines(include_archived=True)
    machine_key = str(machine_id or "").strip()
    event_key = str(event_id or "").strip()
    for idx, machine in enumerate(rows):
        if str(machine.get("id") or "").strip() != machine_key:
            continue
        normalized = normalize_machine_record(machine)
        history = machine_history(normalized)
        if not history:
            return None
        latest = history[0]
        latest_key = str(latest.get("event_id") or latest.get("completed_at") or "").strip()
        if latest_key != event_key:
            return None

        previous_status = str(latest.get("previous_status") or "normal").strip().lower() or "normal"
        normalized["status"] = previous_status
        normalized["maintenance_status"] = previous_status
        normalized["service_date"] = latest.get("service_date_before") or None

        due_before = latest.get("due_date_before")
        normalized["due_date"] = due_before or None
        normalized["next_maintenance"] = due_before or None

        next_due_hours_before = latest.get("next_due_hours_before")
        normalized["next_due_hours"] = next_due_hours_before if next_due_hours_before not in ("", "None") else None

        remaining = history[1:]
        normalized["maintenance_history"] = remaining
        if remaining:
            normalized["last_maintenance_completed_at"] = remaining[0].get("completed_at") or None
            normalized["last_maintenance_status"] = remaining[0].get("previous_status") or None
        else:
            normalized["last_maintenance_completed_at"] = None
            normalized["last_maintenance_status"] = None
        normalized["last_updated"] = _now_iso()
        rows[idx] = normalize_machine_record(normalized)
        save_machines(rows)
        return rows[idx]
    return None


def archive_machine(machine_id: str) -> bool:
    rows = load_machines(include_archived=True)
    updated = False
    for row in rows:
        if str(row.get("id") or "").strip() == str(machine_id or "").strip():
            row["archived"] = True
            row["deleted_at"] = _now_iso()
            row["last_updated"] = _now_iso()
            updated = True
            break
    if updated:
        save_machines(rows)
    return updated


def clear_all_machines() -> None:
    save_machines([])
