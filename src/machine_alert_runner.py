from __future__ import annotations

import json
import logging
import os
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:
    from .app_paths import data_path, logs_dir
    from .incident_store import append_incident, load_incidents
    from .machine_store import evaluate_machine_status, load_machines
    from .predictive_layer import predict_machine_risk
    from .report_delivery import maybe_deliver_scheduled_report
    from .rule_engine import evaluate_rules, load_rules, render_rule_message
    from .settings_store import load_settings
    from .sms_contacts import (
        load_saved_operator_recipients,
        machine_primary_recipient,
        merge_recipients,
        normalize_sms_phone,
        parse_phone_csv,
    )
    from .sms_service import default_sms_service
except Exception:
    from app_paths import data_path, logs_dir
    from incident_store import append_incident, load_incidents
    from machine_store import evaluate_machine_status, load_machines
    from predictive_layer import predict_machine_risk
    from report_delivery import maybe_deliver_scheduled_report
    from rule_engine import evaluate_rules, load_rules, render_rule_message
    from settings_store import load_settings
    from sms_contacts import (
        load_saved_operator_recipients,
        machine_primary_recipient,
        merge_recipients,
        normalize_sms_phone,
        parse_phone_csv,
    )
    from sms_service import default_sms_service


logger = logging.getLogger(__name__)
ALERTABLE_STATUSES = {"critical", "maintenance", "due", "overdue"}
STATE_FILE = data_path("machine_alert_state.json")
META_STATE_FILE = data_path("machine_alert_meta_state.json")
LOCK_FILE = data_path("machine_alert_runner.lock")
LOG_FILE = logs_dir() / "machine_alert_runner.log"
MAINTENANCE_TASKS_FILE = data_path("maintenance_tasks.json")
PLANT_MAINTENANCE_STATE_FILE = data_path("plant_maintenance_state.json")
PARTS_FILE = data_path("parts.json")
CHECKLISTS_FILE = data_path("checklists.json")
OPERATORS_EXTENDED_FILE = data_path("operators_extended.json")
OPERATOR_ALERT_STATE_FILE = data_path("operator_alert_state.json")


def configure_runner_logging() -> None:
    if logger.handlers:
        return
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def machine_alert_state_path() -> Path:
    return STATE_FILE


def machine_alert_meta_state_path() -> Path:
    """Keep meta-state beside alert state so test sandboxes stay isolated."""
    try:
        state_dir = Path(STATE_FILE).parent
        if state_dir:
            return state_dir / "machine_alert_meta_state.json"
    except Exception:
        pass
    return META_STATE_FILE


def operator_alert_state_path() -> Path:
    """Keep operator alert state beside machine state in test/runtime sandboxes."""
    try:
        state_dir = Path(STATE_FILE).parent
        if state_dir:
            return state_dir / "operator_alert_state.json"
    except Exception:
        pass
    return OPERATOR_ALERT_STATE_FILE


def load_machine_alert_state() -> Dict[str, Dict[str, Any]]:
    try:
        if STATE_FILE.exists():
            payload = json.loads(STATE_FILE.read_text(encoding="utf-8")) or {}
            if isinstance(payload, dict):
                return payload
    except Exception:
        logger.exception("Failed to load machine alert state")
    return {}


def save_machine_alert_state(state: Dict[str, Dict[str, Any]]) -> None:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        logger.exception("Failed to save machine alert state")


def load_machine_alert_meta_state() -> Dict[str, Any]:
    path = machine_alert_meta_state_path()
    try:
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8")) or {}
            if isinstance(payload, dict):
                return payload
    except Exception:
        logger.exception("Failed to load machine alert meta state")
    return {}


def save_machine_alert_meta_state(state: Dict[str, Any]) -> None:
    path = machine_alert_meta_state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        logger.exception("Failed to save machine alert meta state")


def load_operator_alert_state() -> Dict[str, Any]:
    path = operator_alert_state_path()
    try:
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8")) or {}
            if isinstance(payload, dict):
                return payload
    except Exception:
        logger.exception("Failed to load operator alert state")
    return {}


def save_operator_alert_state(state: Dict[str, Any]) -> None:
    path = operator_alert_state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        logger.exception("Failed to save operator alert state")


def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except Exception:
        return None


def _use_persistent_rate_limit_state(cfg: Dict[str, Any], sms_service: Any) -> bool:
    explicit = cfg.get("persist_sms_rate_limit_state")
    if explicit is not None:
        return bool(explicit)
    return sms_service is None or sms_service is default_sms_service


def _machine_status_context(machine: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    reminder_days = max(1, int(cfg.get("machine_reminder_days", 2) or 2))
    overdue_after_days = max(1, int(cfg.get("machine_overdue_after_days", 2) or 2))
    return evaluate_machine_status(
        machine,
        reminder_days=reminder_days,
        overdue_after_days=overdue_after_days,
    )


def _machine_has_due_baseline(machine: Dict[str, Any]) -> bool:
    machine_id = str(machine.get("id") or machine.get("name") or "").strip()
    if not machine_id:
        return False
    due_raw = str(machine.get("due_date") or machine.get("next_maintenance") or "").strip()
    if _parse_any_date(due_raw) is not None:
        return True
    for key in ("next_due_hours", "service_interval_hours", "hour_alert_window", "hour_overdue_after_hours"):
        raw = str(machine.get(key) or "").strip()
        if not raw:
            continue
        try:
            if float(raw) >= 0:
                return True
        except Exception:
            continue
    return False


def _role_settings_key(role: str) -> str:
    role_map = {
        "operator": "escalation_operator_phones",
        "supervisor": "escalation_supervisor_phones",
        "manager": "escalation_admin_phones",
        "admin": "escalation_admin_phones",
    }
    return role_map.get(str(role or "").strip().lower(), "")


def build_machine_alert_message(machine: Dict[str, Any], status: str, context: Optional[Dict[str, Any]] = None) -> str:
    machine_id = str(machine.get("id") or machine.get("name") or "Machine").strip()
    machine_name = str(machine.get("name") or machine.get("model") or machine.get("type") or machine_id).strip()
    due_date = str(machine.get("due_date") or machine.get("next_maintenance") or "").strip()
    ctx = dict(context or {})
    trigger = str(ctx.get("trigger") or "").strip().lower()
    current_hours = ctx.get("current_hours")
    due_hours = ctx.get("next_due_hours")
    escalation_day = ctx.get("escalation_day")
    escalation_role = str(ctx.get("escalation_role") or "").strip().lower()

    def _fmt_hours(value: Any) -> str:
        try:
            return f"{float(value):.1f}"
        except Exception:
            return str(value or "not set")

    if status == "critical":
        base = f"CRITICAL ALERT: {machine_id} ({machine_name}) needs immediate attention."
    elif trigger == "hours":
        if status == "overdue":
            base = (
                f"OVERDUE ALERT: {machine_id} ({machine_name}) has reached {_fmt_hours(current_hours)} running hours "
                f"and exceeded its maintenance due point of {_fmt_hours(due_hours)} hours."
            )
        elif status == "due":
            base = (
                f"DUE ALERT: {machine_id} ({machine_name}) has reached {_fmt_hours(current_hours)} running hours "
                f"and is now due for maintenance at {_fmt_hours(due_hours)} hours."
            )
        else:
            base = (
                f"MAINTENANCE ALERT: {machine_id} ({machine_name}) is approaching its maintenance threshold. "
                f"Current reading: {_fmt_hours(current_hours)} hours. Due at: {_fmt_hours(due_hours)} hours."
            )
    elif status == "overdue":
        base = f"OVERDUE ALERT: {machine_id} ({machine_name}) is overdue for maintenance. Due date was {due_date or 'not set'}."
    elif status == "due":
        base = f"DUE ALERT: {machine_id} ({machine_name}) is due for maintenance today."
    else:
        base = f"MAINTENANCE ALERT: {machine_id} ({machine_name}) is approaching maintenance due date {due_date or 'soon'}."

    if escalation_day is not None:
        try:
            day_num = int(escalation_day)
        except Exception:
            day_num = 0
        if day_num <= 0 and escalation_role in {"", "operator"}:
            return base
        role_text = escalation_role.title() if escalation_role else "Escalation"
        return f"ESCALATION DAY {day_num} ({role_text}): {base}"
    return base


def build_maintenance_completion_message(
    machine: Dict[str, Any],
    *,
    completed_by: str = "",
) -> str:
    machine_id = str(machine.get("id") or machine.get("name") or "Machine").strip()
    machine_name = str(machine.get("name") or machine.get("model") or machine.get("type") or machine_id).strip()
    next_due_date = str(machine.get("next_maintenance") or machine.get("due_date") or "-").strip() or "-"
    next_due_hours = str(machine.get("next_due_hours") or "-").strip() or "-"
    who = str(completed_by or machine.get("operator_name") or "Maintenance Team").strip() or "Maintenance Team"
    completed_at = (
        str(machine.get("last_maintenance_completed_at") or "").replace("T", " ").strip()
        or datetime.now().isoformat(timespec="seconds").replace("T", " ")
    )
    return (
        f"MAINTENANCE COMPLETED: {machine_id} ({machine_name}) completed by {who} at {completed_at}. "
        f"Next due date: {next_due_date}. Next due hours: {next_due_hours}."
    )


def send_maintenance_completion_sms(
    machine: Dict[str, Any],
    *,
    completed_by: str = "",
    settings: Optional[Dict[str, Any]] = None,
    sms_service: Any = None,
) -> Dict[str, Any]:
    cfg = dict(settings or load_settings())
    summary = {"sent": 0, "failures": 0, "recipients": 0, "reason": ""}
    if not bool(cfg.get("completion_sms_enabled", True)):
        summary["reason"] = "completion_sms_disabled"
        return summary
    if not bool(cfg.get("sms_enabled", False)):
        summary["reason"] = "sms_disabled"
        return summary

    persist_rate_state = _use_persistent_rate_limit_state(cfg, sms_service)
    meta_state = load_machine_alert_meta_state() if persist_rate_state else {}
    service = RateLimitedSMSService(sms_service or default_sms_service, cfg, meta_state)
    recipients: List[Dict[str, str]] = []
    primary = machine_primary_recipient(machine)
    if primary:
        recipients.append(primary)
    if bool(cfg.get("completion_sms_include_supervisor", False)):
        recipients = merge_recipients(
            recipients,
            get_machine_alert_recipients({}, role="supervisor", settings=cfg),
        )
    if bool(cfg.get("completion_sms_include_admin", False)):
        recipients = merge_recipients(
            recipients,
            get_machine_alert_recipients({}, role="admin", settings=cfg),
        )
    if not recipients:
        summary["reason"] = "no_recipients"
        return summary

    summary["recipients"] = len(recipients)
    message = build_maintenance_completion_message(machine, completed_by=completed_by)
    for recipient in recipients:
        try:
            result = service.send(recipient["phone"], message)
        except Exception as exc:
            result = {"success": False, "error": str(exc)}
        if result.get("success"):
            summary["sent"] += 1
        else:
            summary["failures"] += 1
    if persist_rate_state:
        save_machine_alert_meta_state(meta_state)
    summary["reason"] = "sent" if summary["sent"] else "send_failed"
    return summary


def get_machine_alert_recipients(
    machine: Dict[str, Any],
    *,
    fallback_recipients: Optional[Iterable[Dict[str, str]]] = None,
    role: str = "operator",
    settings: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, str]]:
    cfg = dict(settings or {})
    role_lower = str(role or "operator").strip().lower() or "operator"
    fallback_list = [dict(item) for item in (fallback_recipients or []) if isinstance(item, dict)]

    if role_lower == "operator":
        primary = machine_primary_recipient(machine)
        if primary:
            return [primary]

    role_file_recipients = load_saved_operator_recipients(role=role_lower)
    settings_key = _role_settings_key(role_lower)
    settings_recipients = parse_phone_csv(
        cfg.get(settings_key, ""),
        source=f"settings_{role_lower}",
        default_name=role_lower.title(),
    )

    recipients = merge_recipients(role_file_recipients, settings_recipients)
    if recipients:
        return recipients

    if fallback_list:
        return merge_recipients(fallback_list)
    return []


def _resolve_escalation(last_state: Dict[str, Any], status: str, now: datetime) -> Dict[str, Any]:
    status_lower = str(status or "").strip().lower()
    if status_lower not in {"due", "overdue"}:
        return {}

    started_at: Optional[datetime] = None
    previous_status = str(last_state.get("status") or "").strip().lower()
    if previous_status in {"due", "overdue"}:
        started_at = _parse_iso_datetime(last_state.get("escalation_started_at"))
    if started_at is None:
        started_at = now

    elapsed_days = max(0, (now.date() - started_at.date()).days)
    stage_day = min(2, elapsed_days)
    role = "operator" if stage_day <= 0 else "supervisor" if stage_day == 1 else "manager"
    lifecycle = started_at.date().isoformat()
    return {
        "day": stage_day,
        "role": role,
        "started_at": started_at.isoformat(timespec="seconds"),
        "lifecycle": lifecycle,
    }


def _resolve_due_timeline_escalation(
    machine: Dict[str, Any],
    status_context: Dict[str, Any],
    now: datetime,
) -> Dict[str, Any]:
    due_raw = str(status_context.get("due_date") or machine.get("due_date") or machine.get("next_maintenance") or "").strip()
    due_date = _parse_any_date(due_raw)
    if due_date is None:
        return {}
    days_to_due = (due_date - now.date()).days
    if days_to_due > 2:
        return {}

    if days_to_due == 2:
        stage_day = 0
        role = "operator"
    elif days_to_due == 1:
        stage_day = 1
        role = "supervisor"
    else:
        stage_day = 2
        role = "manager"

    return {
        "day": stage_day,
        "role": role,
        "days_to_due": days_to_due,
        "started_at": now.isoformat(timespec="seconds"),
        "lifecycle": due_date.isoformat(),
    }


def collect_pending_machine_alerts(
    machines: List[Dict[str, Any]],
    *,
    settings: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None,
    fallback_recipients: Optional[Iterable[Dict[str, str]]] = None,
    persist_state: bool = True,
) -> List[Dict[str, Any]]:
    cfg = dict(settings or load_settings())
    cooldown_minutes = max(1, int(cfg.get("machine_alert_cooldown_minutes", 360) or 360))
    cooldown_delta = timedelta(minutes=cooldown_minutes)
    status_change_alerts_only = bool(cfg.get("status_change_alerts_only", True))
    escalation_enabled = bool(cfg.get("auto_escalation_sms", True))
    now = now or datetime.now()

    state = load_machine_alert_state()
    pending: List[Dict[str, Any]] = []
    active_machine_ids = set()
    fallback_list = list(fallback_recipients) if fallback_recipients is not None else None

    for machine in machines or []:
        if not _machine_has_due_baseline(machine):
            continue
        machine_id = str(machine.get("id") or machine.get("name") or "").strip()
        if not machine_id:
            continue
        active_machine_ids.add(machine_id)

        status_context = _machine_status_context(machine, cfg)
        status = str(status_context.get("status") or "normal").strip().lower()
        trigger = str(status_context.get("trigger") or "manual").strip().lower() or "manual"
        last = state.get(machine_id, {})
        status_key = f"{status}:{trigger}"
        by_key = dict(last.get("state_key_last_sent") or {}) if isinstance(last.get("state_key_last_sent"), dict) else {}
        last_by_key_at = _parse_iso_datetime(by_key.get(status_key))

        # Auto-stop reminders when machine is no longer in alertable state (e.g., maintenance completed).
        if status not in ALERTABLE_STATUSES:
            if isinstance(last, dict) and last:
                stopped_state = dict(last)
                stopped_state["status"] = status
                stopped_state["status_key"] = status_key
                stopped_state["last_cleared_at"] = now.isoformat(timespec="seconds")
                stopped_state.pop("last_escalation_day", None)
                stopped_state.pop("escalation_role", None)
                stopped_state.pop("escalation_started_at", None)
                stopped_state.pop("escalation_lifecycle", None)
                state[machine_id] = stopped_state
            continue

        # Cooldown per machine + status + trigger.
        if last_by_key_at and (now - last_by_key_at) < cooldown_delta:
            continue

        timeline_escalation = (
            _resolve_due_timeline_escalation(machine, status_context, now)
            if escalation_enabled and trigger == "date" and status in {"maintenance", "due", "overdue"}
            else {}
        )
        if timeline_escalation:
            last_day = -1
            try:
                last_day = int(last.get("last_escalation_day", -1))
            except Exception:
                last_day = -1
            if (
                str(last.get("escalation_lifecycle") or "") == str(timeline_escalation.get("lifecycle") or "")
                and last_day >= int(timeline_escalation.get("day", -1))
            ):
                continue

            role = str(timeline_escalation.get("role") or "operator")
            recipients = get_machine_alert_recipients(
                machine,
                fallback_recipients=None if role == "operator" else fallback_list,
                role=role,
                settings=cfg,
            )
            if not recipients:
                continue

            context = dict(status_context)
            context["escalation_day"] = int(timeline_escalation.get("day", 0))
            context["escalation_role"] = role
            context["days_to_due"] = int(timeline_escalation.get("days_to_due", 0))
            pending.append(
                {
                    "machine_id": machine_id,
                    "status": status,
                    "status_key": f"{status_key}:day{context['escalation_day']}",
                    "state_key_base": status_key,
                    "context": context,
                    "message": build_machine_alert_message(machine, status, context),
                    "recipients": recipients,
                    "escalation_day": context["escalation_day"],
                    "escalation_role": context["escalation_role"],
                    "escalation_started_at": timeline_escalation.get("started_at"),
                    "escalation_lifecycle": timeline_escalation.get("lifecycle"),
                }
            )
            continue

        if escalation_enabled and status in {"due", "overdue"}:
            escalation = _resolve_escalation(last, status, now)
            last_sent_at = _parse_iso_datetime(last.get("last_sent_at"))
            last_status_key = str(last.get("status_key") or "").strip().lower()
            last_status = str(last.get("status") or "").strip().lower()
            status_matches = (
                last_status_key == status_key
                or last_status_key == status
                or last_status == status_key
                or last_status == status
            )
            # Backward compatibility for legacy state that only had cooldown markers.
            if (
                not str(last.get("escalation_lifecycle") or "").strip()
                and status_matches
                and last_sent_at
                and (now - last_sent_at) < cooldown_delta
            ):
                continue

            last_day = -1
            try:
                last_day = int(last.get("last_escalation_day", -1))
            except Exception:
                last_day = -1
            if (
                str(last.get("escalation_lifecycle") or "") == str(escalation.get("lifecycle") or "")
                and last_day >= int(escalation.get("day", -1))
            ):
                continue

            recipients = get_machine_alert_recipients(
                machine,
                fallback_recipients=None if str(escalation.get("role") or "operator") == "operator" else fallback_list,
                role=str(escalation.get("role") or "operator"),
                settings=cfg,
            )
            if not recipients:
                continue

            context = dict(status_context)
            context["escalation_day"] = int(escalation.get("day", 0))
            context["escalation_role"] = str(escalation.get("role") or "operator")
            pending.append(
                {
                    "machine_id": machine_id,
                    "status": status,
                    "status_key": f"{status_key}:day{context['escalation_day']}",
                    "state_key_base": status_key,
                    "context": context,
                    "message": build_machine_alert_message(machine, status, context),
                    "recipients": recipients,
                    "escalation_day": context["escalation_day"],
                    "escalation_role": context["escalation_role"],
                    "escalation_started_at": escalation.get("started_at"),
                    "escalation_lifecycle": escalation.get("lifecycle"),
                }
            )
            continue

        last_status_key = str(last.get("status_key") or "").strip().lower()
        last_status = str(last.get("status") or "").strip().lower()
        last_sent_at = _parse_iso_datetime(last.get("last_sent_at"))

        # Backward compatible cooldown:
        # older state may store only plain status ("due"), while newer state stores
        # trigger-aware keys ("due:date", "due:hours").
        status_matches = (
            last_status_key == status_key
            or last_status_key == status
            or last_status == status_key
            or last_status == status
        )
        if status_matches:
            if status_change_alerts_only:
                continue
            if last_sent_at and (now - last_sent_at) < cooldown_delta:
                continue

        recipients = get_machine_alert_recipients(
            machine,
            fallback_recipients=None,
            role="operator",
            settings=cfg,
        )
        if not recipients:
            continue

        pending.append(
            {
                "machine_id": machine_id,
                "status": status,
                "status_key": status_key,
                "state_key_base": status_key,
                "context": status_context,
                "message": build_machine_alert_message(machine, status, status_context),
                "recipients": recipients,
            }
        )

    for machine_id in list(state.keys()):
        if machine_id not in active_machine_ids:
            state.pop(machine_id, None)
    if persist_state:
        save_machine_alert_state(state)
    return pending


def _load_maintenance_tasks() -> List[Dict[str, Any]]:
    try:
        if MAINTENANCE_TASKS_FILE.exists():
            payload = json.loads(MAINTENANCE_TASKS_FILE.read_text(encoding="utf-8")) or []
            if isinstance(payload, list):
                return [dict(item) for item in payload if isinstance(item, dict)]
    except Exception:
        logger.exception("Failed to read maintenance tasks")
    return []


def _save_maintenance_tasks(tasks: List[Dict[str, Any]]) -> None:
    try:
        MAINTENANCE_TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
        MAINTENANCE_TASKS_FILE.write_text(json.dumps(tasks, indent=2), encoding="utf-8")
    except Exception:
        logger.exception("Failed to save maintenance tasks")


def _task_is_open(task: Dict[str, Any]) -> bool:
    status = str(task.get("status") or "").strip().lower()
    return status not in {"completed", "closed", "done", "resolved", "cancelled", "canceled"}


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).strip())
    except Exception:
        return float(default)


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).strip()))
    except Exception:
        return int(default)


class RateLimitedSMSService:
    """Adapter that enforces recipient-level SMS rate limits over hour/day windows."""

    def __init__(self, inner: Any, settings: Dict[str, Any], meta_state: Dict[str, Any]):
        self.inner = inner
        self.settings = dict(settings or {})
        self.meta_state = meta_state if isinstance(meta_state, dict) else {}
        if not isinstance(self.meta_state.get("sms_rate_limit"), dict):
            self.meta_state["sms_rate_limit"] = {}

    def _phone_key(self, phone: Any) -> str:
        raw = str(phone or "").strip()
        digits = "".join(ch for ch in raw if ch.isdigit())
        return digits or raw or "unknown"

    def _limits(self) -> tuple[int, int]:
        per_hour = max(1, _to_int(self.settings.get("sms_max_per_recipient_per_hour"), 10))
        per_day = max(per_hour, _to_int(self.settings.get("sms_max_per_recipient_per_day"), 50))
        return per_hour, per_day

    def send(self, phone: str, message: str) -> Dict[str, Any]:
        now = datetime.now()
        per_hour, per_day = self._limits()
        bucket_hour = now.strftime("%Y%m%d%H")
        bucket_day = now.strftime("%Y%m%d")

        rate_map = self.meta_state.setdefault("sms_rate_limit", {})
        key = self._phone_key(phone)
        row = dict(rate_map.get(key) or {})
        if str(row.get("hour_bucket") or "") != bucket_hour:
            row["hour_bucket"] = bucket_hour
            row["hour_count"] = 0
        if str(row.get("day_bucket") or "") != bucket_day:
            row["day_bucket"] = bucket_day
            row["day_count"] = 0
        row["hour_count"] = max(0, _to_int(row.get("hour_count"), 0))
        row["day_count"] = max(0, _to_int(row.get("day_count"), 0))

        if row["hour_count"] >= per_hour:
            rate_map[key] = row
            return {
                "success": False,
                "rate_limited": True,
                "error": f"Recipient hourly SMS limit reached ({per_hour}/hour)",
            }
        if row["day_count"] >= per_day:
            rate_map[key] = row
            return {
                "success": False,
                "rate_limited": True,
                "error": f"Recipient daily SMS limit reached ({per_day}/day)",
            }

        result = self.inner.send(phone, message)
        if bool(result.get("success")):
            row["hour_count"] = int(row.get("hour_count", 0)) + 1
            row["day_count"] = int(row.get("day_count", 0)) + 1
            row["last_sent_at"] = now.isoformat(timespec="seconds")
        rate_map[key] = row
        return result

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


def _parse_any_datetime(value: Any) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt)
        except Exception:
            continue
    try:
        return datetime.fromisoformat(raw.replace(" ", "T"))
    except Exception:
        return None


def _parse_any_date(value: Any) -> Optional[date]:
    dt = _parse_any_datetime(value)
    if dt is not None:
        return dt.date()
    return None


def _add_years_safe(base_date: date, years: int) -> date:
    try:
        return base_date.replace(year=base_date.year + years)
    except ValueError:
        # Leap-year fallback for Feb-29 anniversaries.
        return base_date.replace(month=2, day=28, year=base_date.year + years)


def _load_operator_records() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    try:
        if OPERATORS_EXTENDED_FILE.exists():
            payload = json.loads(OPERATORS_EXTENDED_FILE.read_text(encoding="utf-8")) or []
            if isinstance(payload, list):
                rows = [dict(item) for item in payload if isinstance(item, dict)]
    except Exception:
        logger.exception("Failed to read operator records")
    return rows


def _operator_record_key(row: Dict[str, Any], index: int) -> str:
    rid = str(row.get("id") or row.get("_id") or "").strip()
    if rid:
        return rid
    phone = normalize_sms_phone(row.get("phone"))
    if phone:
        return f"op_phone_{phone.replace('+', '')}"
    name = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(row.get("name") or "").strip()).strip("_")
    if name:
        return f"op_name_{name}"
    return f"op_idx_{index + 1}"


def _operator_doc_expiry_fields(row: Dict[str, Any]) -> List[Dict[str, str]]:
    return [
        {
            "code": "license",
            "label": "Driving Licence",
            "expiry_raw": str(
                row.get("license_expiry")
                or row.get("licence_expiry")
                or row.get("driving_license_expiry")
                or ""
            ).strip(),
        },
        {
            "code": "medical",
            "label": "Medical Certificate",
            "expiry_raw": str(
                row.get("medical_certificate_end_date")
                or row.get("medical_expiry")
                or row.get("fitness_expiry")
                or ""
            ).strip(),
        },
    ]


def _operator_service_start_date(row: Dict[str, Any]) -> Optional[date]:
    return _parse_any_date(
        row.get("company_start_date")
        or row.get("experience_start_date")
        or row.get("joining_date")
        or row.get("experience_start")
    )


def _incident_severity_for_status(status: str) -> str:
    status_lower = str(status or "").strip().lower()
    if status_lower in {"critical", "overdue"}:
        return "critical"
    if status_lower in {"due", "maintenance"}:
        return "warning"
    return "info"


def _load_parts_rows() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    try:
        if PARTS_FILE.exists():
            payload = json.loads(PARTS_FILE.read_text(encoding="utf-8")) or []
            if isinstance(payload, list):
                for item in payload:
                    if not isinstance(item, dict):
                        continue
                    rows.append(
                        {
                            "source": "parts",
                            "part_name": str(item.get("name") or item.get("part") or "").strip(),
                            "machine_id": str(item.get("machine_id") or item.get("equipment_id") or "").strip(),
                            "stock": _to_float(item.get("quantity_on_hand", item.get("stock", 0))),
                            "min_level": _to_float(item.get("min_level", item.get("min_stock_level", item.get("reorder_level", 1)))),
                        }
                    )
    except Exception:
        logger.exception("Failed to read parts store")

    try:
        if PLANT_MAINTENANCE_STATE_FILE.exists():
            payload = json.loads(PLANT_MAINTENANCE_STATE_FILE.read_text(encoding="utf-8")) or {}
            if isinstance(payload, dict):
                for item in (payload.get("spares") or []):
                    if not isinstance(item, dict):
                        continue
                    rows.append(
                        {
                            "source": "plant_spares",
                            "part_name": str(item.get("part") or item.get("name") or "").strip(),
                            "machine_id": str(item.get("equipment_id") or item.get("machine_id") or "").strip(),
                            "stock": _to_float(item.get("stock", 0)),
                            "min_level": _to_float(item.get("min_level", 1)),
                        }
                    )
    except Exception:
        logger.exception("Failed to read plant spares")
    return rows


def _open_maintenance_tasks(tasks: List[Dict[str, Any]], now: datetime) -> List[Dict[str, Any]]:
    open_rows: List[Dict[str, Any]] = []
    for task in tasks or []:
        if not isinstance(task, dict):
            continue
        if not _task_is_open(task):
            continue
        ref = (
            _parse_any_datetime(task.get("due_date"))
            or _parse_any_datetime(task.get("scheduled_at"))
            or _parse_any_datetime(task.get("created_at"))
        )
        if ref is None:
            continue
        row = dict(task)
        row["_reference_dt"] = ref
        row["_days_open"] = max(0, (now.date() - ref.date()).days)
        open_rows.append(row)
    return open_rows


def auto_log_machine_trigger_incidents(
    machines: List[Dict[str, Any]],
    *,
    settings: Dict[str, Any],
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    current = now or datetime.now()
    cooldown_minutes = max(30, int(settings.get("machine_alert_cooldown_minutes", 360) or 360))
    created = 0
    by_trigger: Dict[str, int] = {"hours": 0, "date": 0, "manual": 0}

    for machine in machines or []:
        if not _machine_has_due_baseline(machine):
            continue
        machine_id = str(machine.get("id") or machine.get("name") or "").strip()
        if not machine_id:
            continue
        ctx = _machine_status_context(machine, settings)
        status = str(ctx.get("status") or "normal").strip().lower()
        if status not in ALERTABLE_STATUSES:
            continue
        trigger = str(ctx.get("trigger") or "manual").strip().lower() or "manual"
        machine_name = str(machine.get("name") or machine.get("model") or machine_id).strip()
        due_date = str(ctx.get("due_date") or machine.get("due_date") or machine.get("next_maintenance") or "").strip()
        message = (
            f"{machine_id} ({machine_name}) is {status.upper()} via {trigger.upper()} trigger."
            + (f" Due: {due_date}." if due_date else "")
        )
        incident_created, _ = append_incident(
            category="machine_status",
            severity=_incident_severity_for_status(status),
            title=f"Machine {status.title()} ({trigger.title()} trigger)",
            message=message,
            trigger=trigger,
            source="automation",
            machine_id=machine_id,
            dedup_key=f"machine_trigger:{machine_id}:{status}:{trigger}",
            dedup_window_minutes=cooldown_minutes,
            extra={
                "status": status,
                "trigger": trigger,
                "due_date": due_date,
                "current_hours": ctx.get("current_hours"),
                "next_due_hours": ctx.get("next_due_hours"),
                "captured_at": current.isoformat(timespec="seconds"),
            },
        )
        if incident_created:
            created += 1
            by_trigger[trigger] = by_trigger.get(trigger, 0) + 1
    return {"created": created, "by_trigger": by_trigger}


def auto_generate_operator_record_alerts(
    *,
    settings: Dict[str, Any],
    sms_service: Any,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    summary = {"created": 0, "sms_sent": 0, "alerts_by_type": {"renewal": 0, "rejection": 0, "service_10y": 0}}
    if not bool(settings.get("auto_operator_record_alerts", True)):
        return summary

    current = now or datetime.now()
    today = current.date()
    renewal_days = max(7, _to_int(settings.get("operator_alert_renewal_days"), 30))
    rejection_days = max(1, min(renewal_days, _to_int(settings.get("operator_alert_rejection_days"), 5)))
    sms_enabled = bool(settings.get("sms_enabled", False)) and bool(settings.get("auto_operator_record_sms", True))

    state = load_operator_alert_state()
    sent_map = dict(state.get("sent") or {}) if isinstance(state.get("sent"), dict) else {}
    # Keep state file compact by pruning old entries.
    prune_before = current - timedelta(days=730)
    sent_map = {
        str(key): str(value)
        for key, value in sent_map.items()
        if (_parse_iso_datetime(value) or current) >= prune_before
    }
    changed = False

    rows = _load_operator_records()
    for idx, row in enumerate(rows):
        operator_key = _operator_record_key(row, idx)
        operator_name = str(row.get("name") or f"Operator {idx + 1}").strip() or f"Operator {idx + 1}"
        phone = normalize_sms_phone(row.get("phone"))

        for doc in _operator_doc_expiry_fields(row):
            expiry = _parse_any_date(doc.get("expiry_raw"))
            if expiry is None:
                continue
            days_left = (expiry - today).days
            if days_left < 0:
                continue

            alert_type = ""
            severity = "warning"
            title = ""
            if days_left <= rejection_days:
                alert_type = "rejection"
                severity = "critical"
                title = f"Operator Document Rejection Risk ({doc['label']})"
            elif days_left <= renewal_days:
                alert_type = "renewal"
                title = f"Operator Document Renewal Due ({doc['label']})"
            if not alert_type:
                continue

            state_key = f"{operator_key}:{doc['code']}:{alert_type}:{expiry.isoformat()}"
            if state_key in sent_map:
                continue

            message = (
                f"{operator_name} - {doc['label']} expires on {expiry.isoformat()} "
                f"({days_left} day(s) left)."
            )
            created, _ = append_incident(
                category="operator_records",
                severity=severity,
                title=title,
                message=message,
                trigger=f"operator_{alert_type}",
                source="automation",
                machine_id="",
                dedup_key=f"operator_records:{state_key}",
                dedup_window_minutes=max(180, _to_int(settings.get("machine_alert_cooldown_minutes"), 360)),
                extra={
                    "operator_name": operator_name,
                    "operator_phone": phone or "",
                    "document": doc["label"],
                    "document_code": doc["code"],
                    "expiry_date": expiry.isoformat(),
                    "days_left": days_left,
                },
            )
            if not created:
                continue

            summary["created"] += 1
            summary["alerts_by_type"][alert_type] = summary["alerts_by_type"].get(alert_type, 0) + 1
            sent_map[state_key] = current.isoformat(timespec="seconds")
            changed = True

            if sms_enabled and phone:
                sms_message = (
                    f"ALERT: {doc['label']} renewal for {operator_name}. "
                    f"Expiry: {expiry.isoformat()} ({days_left} day(s) left)."
                    if alert_type == "renewal"
                    else f"URGENT: {doc['label']} for {operator_name} expires in {days_left} day(s) "
                    f"on {expiry.isoformat()}. Immediate action required."
                )
                try:
                    result = sms_service.send(phone, sms_message)
                except Exception as exc:
                    result = {"success": False, "error": str(exc)}
                if result.get("success"):
                    summary["sms_sent"] += 1

        service_start = _operator_service_start_date(row)
        if service_start is None:
            continue
        milestone = _add_years_safe(service_start, 10)
        if today < milestone:
            continue

        milestone_key = f"{operator_key}:service_10y:{milestone.isoformat()}"
        if milestone_key in sent_map:
            continue

        years_completed = max(10, today.year - service_start.year)
        message = (
            f"{operator_name} completed {years_completed} year(s) of company service. "
            f"10-year milestone reached on {milestone.isoformat()}."
        )
        created, _ = append_incident(
            category="operator_records",
            severity="info",
            title="Operator 10-Year Service Milestone",
            message=message,
            trigger="operator_service_milestone",
            source="automation",
            dedup_key=f"operator_records:{milestone_key}",
            dedup_window_minutes=24 * 60,
            extra={
                "operator_name": operator_name,
                "operator_phone": phone or "",
                "service_start_date": service_start.isoformat(),
                "milestone_date": milestone.isoformat(),
                "years_completed": years_completed,
            },
        )
        if not created:
            continue

        summary["created"] += 1
        summary["alerts_by_type"]["service_10y"] = summary["alerts_by_type"].get("service_10y", 0) + 1
        sent_map[milestone_key] = current.isoformat(timespec="seconds")
        changed = True

        if sms_enabled and phone:
            sms_message = (
                f"CONGRATULATIONS: {operator_name}, you have completed 10 years with the company. "
                f"Milestone date: {milestone.isoformat()}."
            )
            try:
                result = sms_service.send(phone, sms_message)
            except Exception as exc:
                result = {"success": False, "error": str(exc)}
            if result.get("success"):
                summary["sms_sent"] += 1

    if changed:
        state["sent"] = sent_map
        state["updated_at"] = current.isoformat(timespec="seconds")
        save_operator_alert_state(state)
    return summary


def _machine_open_task_days(tasks: List[Dict[str, Any]]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for task in tasks or []:
        machine_id = str(task.get("machine_id") or "").strip()
        if not machine_id:
            continue
        days_open = _to_int(task.get("_days_open"), 0)
        out[machine_id] = max(days_open, out.get(machine_id, 0))
    return out


def _recent_incident_counts(days: int = 7) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    if days <= 0:
        return counts
    since = datetime.now() - timedelta(days=days)
    for row in load_incidents(limit=1200):
        machine_id = str(row.get("machine_id") or "").strip()
        if not machine_id:
            continue
        stamp = _parse_any_datetime(row.get("created_at"))
        if stamp is None or stamp < since:
            continue
        counts[machine_id] = counts.get(machine_id, 0) + 1
    return counts


def _rule_context_for_machine(
    machine: Dict[str, Any],
    status_ctx: Dict[str, Any],
    prediction: Dict[str, Any],
) -> Dict[str, Any]:
    machine_id = str(machine.get("id") or machine.get("name") or "").strip()
    machine_name = str(machine.get("name") or machine.get("model") or machine_id).strip()
    return {
        "machine_id": machine_id,
        "machine_name": machine_name,
        "machine_type": str(machine.get("type") or "").strip().lower(),
        "company": str(machine.get("company") or "").strip().lower(),
        "status": str(status_ctx.get("status") or "normal").strip().lower(),
        "trigger": str(status_ctx.get("trigger") or "manual").strip().lower(),
        "due_date": str(status_ctx.get("due_date") or machine.get("due_date") or machine.get("next_maintenance") or "").strip(),
        "current_hours": prediction.get("current_hours"),
        "next_due_hours": prediction.get("next_due_hours"),
        "hours_to_due": prediction.get("hours_to_due"),
        "days_to_due": prediction.get("days_to_due"),
        "risk_score": int(prediction.get("risk_score") or 0),
        "risk_level": str(prediction.get("risk_level") or "normal").strip().lower(),
    }


def auto_run_rule_engine(
    machines: List[Dict[str, Any]],
    *,
    settings: Dict[str, Any],
    open_tasks: Optional[List[Dict[str, Any]]] = None,
    sms_service: Any,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    summary = {"created": 0, "sms_sent": 0, "matched_rules": {}}
    if not bool(settings.get("rule_engine_enabled", True)):
        return summary

    rules = load_rules()
    if not rules:
        return summary

    current = now or datetime.now()
    reminder_days = max(1, int(settings.get("machine_reminder_days", 2) or 2))
    overdue_after_days = max(1, int(settings.get("machine_overdue_after_days", 2) or 2))
    open_task_days = _machine_open_task_days(open_tasks or [])
    incidents_7d = _recent_incident_counts(days=7)
    created_ids: List[str] = []

    for machine in machines or []:
        if not _machine_has_due_baseline(machine):
            continue
        machine_id = str(machine.get("id") or machine.get("name") or "").strip()
        if not machine_id:
            continue
        status_ctx = _machine_status_context(machine, settings)
        prediction = predict_machine_risk(
            machine,
            now=current,
            reminder_days=reminder_days,
            overdue_after_days=overdue_after_days,
            status_context=status_ctx,
            extras={
                "open_task_days": open_task_days.get(machine_id, 0),
                "incidents_7d": incidents_7d.get(machine_id, 0),
            },
        )
        context = _rule_context_for_machine(machine, status_ctx, prediction)
        matches = evaluate_rules(context, rules=rules)
        if not matches:
            continue

        for rule in matches:
            severity = str(rule.get("severity") or "warning").strip().lower()
            rule_id = str(rule.get("id") or "").strip()
            if not rule_id:
                continue
            message = render_rule_message(rule, context)
            created, _ = append_incident(
                category="rule_engine",
                severity=severity,
                title=f"Rule Matched: {rule.get('name') or rule_id}",
                message=message,
                trigger=str(rule.get("trigger") or "rule_engine"),
                source="automation",
                machine_id=machine_id,
                dedup_key=f"rule_engine:{rule_id}:{machine_id}",
                dedup_window_minutes=max(
                    30,
                    _to_int(
                        rule.get("dedup_window_minutes"),
                        _to_int(settings.get("rule_engine_dedup_minutes"), 360),
                    ),
                ),
                extra={
                    "rule_id": rule_id,
                    "rule_name": str(rule.get("name") or "").strip(),
                    "status": context.get("status"),
                    "trigger": context.get("trigger"),
                    "risk_score": context.get("risk_score"),
                    "risk_level": context.get("risk_level"),
                },
            )
            if created:
                summary["created"] += 1
                summary["matched_rules"][rule_id] = summary["matched_rules"].get(rule_id, 0) + 1
                created_ids.append(machine_id)

    if created_ids and bool(settings.get("sms_enabled", False)) and bool(settings.get("rule_engine_sms_enabled", False)):
        recipients = merge_recipients(
            get_machine_alert_recipients({}, role="supervisor", settings=settings),
            get_machine_alert_recipients({}, role="admin", settings=settings),
        )
        if recipients:
            unique_ids = sorted(set(created_ids))
            preview = ", ".join(unique_ids[:4]) + ("..." if len(unique_ids) > 4 else "")
            message = (
                f"RULE ENGINE ALERT: {summary['created']} rule match(es) detected across {len(unique_ids)} machine(s). "
                f"Machines: {preview}"
            )
            for recipient in recipients:
                try:
                    result = sms_service.send(recipient["phone"], message)
                except Exception as exc:
                    result = {"success": False, "error": str(exc)}
                if result.get("success"):
                    summary["sms_sent"] += 1
    return summary


def auto_generate_predictive_alerts(
    machines: List[Dict[str, Any]],
    *,
    settings: Dict[str, Any],
    open_tasks: Optional[List[Dict[str, Any]]] = None,
    sms_service: Any,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    summary = {"created": 0, "sms_sent": 0, "high_risk_count": 0, "top_risk_score": 0}
    if not bool(settings.get("predictive_layer_enabled", True)):
        return summary

    current = now or datetime.now()
    reminder_days = max(1, int(settings.get("machine_reminder_days", 2) or 2))
    overdue_after_days = max(1, int(settings.get("machine_overdue_after_days", 2) or 2))
    threshold = max(40, min(95, _to_int(settings.get("predictive_alert_threshold"), 65)))
    dedup_minutes = max(30, _to_int(settings.get("predictive_dedup_minutes"), 360))
    open_task_days = _machine_open_task_days(open_tasks or [])
    incidents_7d = _recent_incident_counts(days=7)
    created_rows: List[Dict[str, Any]] = []

    for machine in machines or []:
        if not _machine_has_due_baseline(machine):
            continue
        machine_id = str(machine.get("id") or machine.get("name") or "").strip()
        if not machine_id:
            continue
        status_ctx = _machine_status_context(machine, settings)
        prediction = predict_machine_risk(
            machine,
            now=current,
            reminder_days=reminder_days,
            overdue_after_days=overdue_after_days,
            status_context=status_ctx,
            extras={
                "open_task_days": open_task_days.get(machine_id, 0),
                "incidents_7d": incidents_7d.get(machine_id, 0),
            },
        )
        risk_score = int(prediction.get("risk_score") or 0)
        risk_level = str(prediction.get("risk_level") or "normal").strip().lower()
        if risk_score >= 65:
            summary["high_risk_count"] += 1
        summary["top_risk_score"] = max(summary["top_risk_score"], risk_score)
        if risk_score < threshold:
            continue

        machine_name = str(machine.get("name") or machine.get("model") or machine_id).strip()
        reasons = prediction.get("reasons") or []
        reason_text = "; ".join(str(item) for item in reasons[:3]) if reasons else "Risk factors accumulating."
        severity = "critical" if risk_level == "critical" else "warning" if risk_level in {"high", "watch"} else "info"
        message = (
            f"Predictive risk score {risk_score}/100 for {machine_id} ({machine_name}) [{risk_level.upper()}]. "
            f"{reason_text}"
        )
        created, _ = append_incident(
            category="predictive",
            severity=severity,
            title=f"Predictive Risk: {machine_id}",
            message=message,
            trigger="predictive_risk",
            source="automation",
            machine_id=machine_id,
            dedup_key=f"predictive:{machine_id}:{risk_level}",
            dedup_window_minutes=dedup_minutes,
            extra={
                "risk_score": risk_score,
                "risk_level": risk_level,
                "status": prediction.get("status"),
                "trigger": prediction.get("trigger"),
                "days_to_due": prediction.get("days_to_due"),
                "hours_to_due": prediction.get("hours_to_due"),
                "reasons": reasons[:8],
            },
        )
        if created:
            summary["created"] += 1
            created_rows.append({"machine_id": machine_id, "risk_score": risk_score, "risk_level": risk_level})

    if created_rows and bool(settings.get("sms_enabled", False)) and bool(settings.get("predictive_sms_enabled", False)):
        recipients = merge_recipients(
            get_machine_alert_recipients({}, role="supervisor", settings=settings),
            get_machine_alert_recipients({}, role="admin", settings=settings),
        )
        if recipients:
            top = max(created_rows, key=lambda row: int(row.get("risk_score") or 0))
            message = (
                f"PREDICTIVE ALERT: {len(created_rows)} machine(s) crossed risk threshold. "
                f"Top risk {top.get('machine_id')} score {top.get('risk_score')}."
            )
            for recipient in recipients:
                try:
                    result = sms_service.send(recipient["phone"], message)
                except Exception as exc:
                    result = {"success": False, "error": str(exc)}
                if result.get("success"):
                    summary["sms_sent"] += 1
    return summary


def auto_generate_spare_reorder_alerts(
    *,
    settings: Dict[str, Any],
    tasks: List[Dict[str, Any]],
    sms_service: Any,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    current = now or datetime.now()
    summary = {"created": 0, "sms_sent": 0}
    if not bool(settings.get("auto_spare_reorder_alerts", True)):
        return summary

    parts_rows = _load_parts_rows()
    low_stock_rows = []
    for row in parts_rows:
        part_name = str(row.get("part_name") or "").strip()
        if not part_name:
            continue
        stock = _to_float(row.get("stock"), 0)
        min_level = _to_float(row.get("min_level"), 1)
        if stock <= min_level:
            low_stock_rows.append(dict(row))

    if not low_stock_rows:
        return summary

    open_rows = _open_maintenance_tasks(tasks, current)
    planned = [row for row in open_rows if str(row.get("condition_status") or "").strip().lower() in {"maintenance", "due", "overdue"}]
    if not planned:
        planned = [row for row in open_rows if row.get("_days_open", 0) <= 7]

    for row in low_stock_rows:
        part_name = str(row.get("part_name") or "").strip()
        machine_id = str(row.get("machine_id") or "").strip()
        stock = _to_float(row.get("stock"), 0)
        min_level = _to_float(row.get("min_level"), 1)
        linked_planned = planned
        if machine_id:
            linked_planned = [task for task in planned if str(task.get("machine_id") or "").strip() == machine_id] or planned
        title = "Spare Reorder Alert"
        message = (
            f"Part '{part_name}' stock {stock:.0f} is at/below minimum {min_level:.0f}. "
            f"Planned maintenance tasks open: {len(linked_planned)}."
        )
        created, _ = append_incident(
            category="spare_reorder",
            severity="warning",
            title=title,
            message=message,
            trigger="planned_maintenance",
            source="automation",
            machine_id=machine_id,
            dedup_key=f"spare_reorder:{row.get('source')}:{machine_id}:{part_name}:{int(min_level)}",
            dedup_window_minutes=720,
            extra={
                "part_name": part_name,
                "stock": stock,
                "min_level": min_level,
                "planned_task_count": len(linked_planned),
            },
        )
        if created:
            summary["created"] += 1

    if summary["created"] and bool(settings.get("sms_enabled", False)):
        recipients = merge_recipients(
            get_machine_alert_recipients({}, role="supervisor", settings=settings),
            get_machine_alert_recipients({}, role="admin", settings=settings),
        )
        message = (
            f"REORDER ALERT: {summary['created']} spare item(s) are at/below min stock with planned maintenance pending. "
            f"Please review inventory now."
        )
        for recipient in recipients:
            try:
                result = sms_service.send(recipient["phone"], message)
            except Exception as exc:
                result = {"success": False, "error": str(exc)}
            if result.get("success"):
                summary["sms_sent"] += 1
    return summary


def auto_generate_maintenance_followup_reminders(
    *,
    settings: Dict[str, Any],
    tasks: List[Dict[str, Any]],
    sms_service: Any,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    current = now or datetime.now()
    summary = {"created": 0, "sms_sent": 0}
    if not bool(settings.get("auto_maintenance_followup_reminders", True)):
        return summary

    followup_days = max(1, int(settings.get("maintenance_followup_days", 1) or 1))
    open_rows = _open_maintenance_tasks(tasks, current)
    if not open_rows:
        return summary

    created_rows: List[Dict[str, Any]] = []
    for task in open_rows:
        days_open = int(task.get("_days_open", 0))
        if days_open < followup_days:
            continue
        task_id = str(task.get("id") or task.get("task_id") or task.get("subject") or "").strip()
        if not task_id:
            continue
        severity = "critical" if days_open >= followup_days + 1 else "warning"
        title = "Maintenance Not Closed Follow-up"
        subject = str(task.get("subject") or "Maintenance task").strip()
        machine_id = str(task.get("machine_id") or "").strip()
        message = f"{subject} has remained open for {days_open} day(s). Please close or update status."
        created, incident = append_incident(
            category="maintenance_followup",
            severity=severity,
            title=title,
            message=message,
            trigger="maintenance_not_closed",
            source="automation",
            machine_id=machine_id,
            task_id=task_id,
            dedup_key=f"maintenance_followup:{task_id}:day{days_open}",
            dedup_window_minutes=1440,
            extra={
                "task_id": task_id,
                "subject": subject,
                "days_open": days_open,
                "status": task.get("status"),
                "due_date": task.get("due_date"),
            },
        )
        if created:
            summary["created"] += 1
            created_rows.append(incident)

    if created_rows and bool(settings.get("sms_enabled", False)):
        max_days = max(int((row.get("extra") or {}).get("days_open") or 0) for row in created_rows)
        if max_days >= followup_days + 1:
            recipients = merge_recipients(
                get_machine_alert_recipients({}, role="supervisor", settings=settings),
                get_machine_alert_recipients({}, role="admin", settings=settings),
            )
        else:
            recipients = get_machine_alert_recipients({}, role="supervisor", settings=settings)
        message = f"FOLLOW-UP ALERT: {summary['created']} maintenance task(s) are not closed. Review work orders."
        for recipient in recipients:
            try:
                result = sms_service.send(recipient["phone"], message)
            except Exception as exc:
                result = {"success": False, "error": str(exc)}
            if result.get("success"):
                summary["sms_sent"] += 1
    return summary


def _latest_checklist_entry_datetime() -> Optional[datetime]:
    try:
        if not CHECKLISTS_FILE.exists():
            return None
        payload = json.loads(CHECKLISTS_FILE.read_text(encoding="utf-8")) or {}
        entries: List[Dict[str, Any]] = []
        if isinstance(payload, dict):
            entries = [item for item in (payload.get("entries") or []) if isinstance(item, dict)]
        elif isinstance(payload, list):
            entries = [item for item in payload if isinstance(item, dict)]

        latest: Optional[datetime] = None
        for entry in entries:
            stamp = _parse_any_datetime(entry.get("saved_at") or entry.get("timestamp") or entry.get("created_at"))
            if stamp is None:
                continue
            if latest is None or stamp > latest:
                latest = stamp
        if latest is not None:
            return latest

        # If no entries exist, checklist has not been completed yet.
        if not entries:
            return None

        # Legacy payload may include entries without timestamps; fallback to file write time.
        return datetime.fromtimestamp(CHECKLISTS_FILE.stat().st_mtime)
    except Exception:
        logger.exception("Failed to inspect checklist entries")
        return None


def auto_generate_missed_checklist_alert(
    *,
    settings: Dict[str, Any],
    sms_service: Any,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    current = now or datetime.now()
    summary = {"created": 0, "sms_sent": 0, "reason": ""}
    if not bool(settings.get("checklist_missed_alerts_enabled", True)):
        summary["reason"] = "disabled"
        return summary

    cutoff_hour = _to_int(settings.get("checklist_missed_cutoff_hour"), 18)
    cutoff_hour = max(0, min(23, cutoff_hour))
    if current.hour < cutoff_hour:
        summary["reason"] = "before_cutoff"
        return summary

    last_entry = _latest_checklist_entry_datetime()
    today = current.date()
    if last_entry is not None and last_entry.date() >= today:
        summary["reason"] = "checklist_completed_today"
        return summary

    missed_days = 1 if last_entry is None else max(1, (today - last_entry.date()).days)
    severity = "critical" if missed_days >= 2 else "warning"
    msg_tail = "No checklist entries found." if last_entry is None else f"Last checklist: {last_entry.strftime('%Y-%m-%d %H:%M:%S')}."
    created, _ = append_incident(
        category="checklist",
        severity=severity,
        title="Missed Checklist Alert",
        message=f"Daily checklist has not been closed for today. {msg_tail}",
        trigger="missed_checklist",
        source="automation",
        dedup_key=f"missed_checklist:{today.isoformat()}",
        dedup_window_minutes=1440,
        extra={"missed_days": missed_days, "cutoff_hour": cutoff_hour},
    )
    if not created:
        summary["reason"] = "already_recorded"
        return summary

    summary["created"] = 1
    summary["reason"] = "created"
    if bool(settings.get("sms_enabled", False)):
        recipients = merge_recipients(
            get_machine_alert_recipients({}, role="supervisor", settings=settings),
            get_machine_alert_recipients({}, role="admin", settings=settings),
        )
        message = "CHECKLIST ALERT: Daily checklist is not closed after cutoff. Please complete and save checklist now."
        for recipient in recipients:
            try:
                result = sms_service.send(recipient["phone"], message)
            except Exception as exc:
                result = {"success": False, "error": str(exc)}
            if result.get("success"):
                summary["sms_sent"] += 1
    return summary


def _append_plant_work_orders(entries: List[Dict[str, Any]], now: datetime) -> int:
    if not entries:
        return 0
    try:
        if not PLANT_MAINTENANCE_STATE_FILE.exists():
            return 0
        payload = json.loads(PLANT_MAINTENANCE_STATE_FILE.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            return 0
        work_orders = payload.setdefault("work_orders", [])
        if not isinstance(work_orders, list):
            payload["work_orders"] = []
            work_orders = payload["work_orders"]

        open_keys = {
            (str(item.get("equipment_id") or "").strip(), str(item.get("task") or "").strip())
            for item in work_orders
            if isinstance(item, dict) and str(item.get("status") or "").strip().lower() != "closed"
        }

        max_idx = 0
        for item in work_orders:
            if not isinstance(item, dict):
                continue
            raw_id = str(item.get("wo_id") or "")
            if "-" in raw_id:
                try:
                    max_idx = max(max_idx, int(raw_id.rsplit("-", 1)[-1]))
                except Exception:
                    continue

        added = 0
        for entry in entries:
            machine_id = str(entry.get("machine_id") or "").strip()
            subject = str(entry.get("subject") or "").strip()
            if not machine_id or not subject:
                continue
            key = (machine_id, subject)
            if key in open_keys:
                continue
            max_idx += 1
            work_orders.append(
                {
                    "wo_id": f"WO-{max_idx:03d}",
                    "equipment_id": machine_id,
                    "task": subject,
                    "priority": "High" if str(entry.get("priority") or "").lower() == "high" else "Medium",
                    "due_date": str(entry.get("due_date") or now.date().isoformat()),
                    "status": "Open",
                    "assigned_to": entry.get("assigned_to") or "Maintenance Team",
                    "estimated_cost": "0",
                    "source": "auto_machine_due_scan",
                }
            )
            open_keys.add(key)
            added += 1

        if added:
            PLANT_MAINTENANCE_STATE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return added
    except Exception:
        logger.exception("Failed to sync plant-maintenance work orders")
        return 0


def auto_generate_due_work_orders(
    machines: List[Dict[str, Any]],
    *,
    settings: Dict[str, Any],
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    current = now or datetime.now()
    summary = {"created": 0, "plant_work_orders_created": 0}
    if not bool(settings.get("auto_work_order_generation", True)):
        return summary

    tasks = _load_maintenance_tasks()
    open_auto_keys = set()
    for task in tasks:
        if not _task_is_open(task):
            continue
        machine_id = str(task.get("machine_id") or "").strip()
        if not machine_id:
            continue
        if not bool(task.get("auto_generated", False)):
            continue
        trigger = str(task.get("trigger") or "").strip().lower()
        condition_status = str(task.get("condition_status") or "").strip().lower()
        open_auto_keys.add((machine_id, trigger, condition_status))

    created_entries: List[Dict[str, Any]] = []
    for machine in machines or []:
        machine_id = str(machine.get("id") or machine.get("name") or "").strip()
        if not machine_id:
            continue
        status_context = _machine_status_context(machine, settings)
        status = str(status_context.get("status") or "normal").strip().lower()
        if status not in {"due", "overdue"}:
            continue
        trigger = str(status_context.get("trigger") or "manual").strip().lower()
        key = (machine_id, trigger, status)
        if key in open_auto_keys:
            continue

        machine_name = str(machine.get("name") or machine.get("model") or machine_id).strip()
        due_date = str(status_context.get("due_date") or machine.get("due_date") or machine.get("next_maintenance") or "").strip()
        current_hours = status_context.get("current_hours") or machine.get("current_hours") or machine.get("hours")
        next_due_hours = status_context.get("next_due_hours") or machine.get("next_due_hours")
        task = {
            "id": f"auto_wo_{machine_id}_{int(current.timestamp())}_{len(tasks) + len(created_entries) + 1}",
            "subject": f"{status.upper()} maintenance - {machine_name} ({machine_id})",
            "machine_id": machine_id,
            "scheduled_at": current.isoformat(timespec="seconds"),
            "status": "pending",
            "priority": "high" if status == "overdue" else "medium",
            "due_date": due_date,
            "due_at_hours": next_due_hours if trigger == "hours" else None,
            "trigger": trigger,
            "condition_status": status,
            "auto_generated": True,
            "source": "machine_alert_runner",
            "assigned_to": "Maintenance Team",
            "notes": (
                f"Auto-generated when machine became {status}. "
                f"Trigger={trigger}; current_hours={current_hours}; next_due_hours={next_due_hours}; due_date={due_date or '-'}"
            ),
            "created_at": current.isoformat(timespec="seconds"),
        }
        tasks.append(task)
        created_entries.append(task)
        open_auto_keys.add(key)

    if created_entries:
        _save_maintenance_tasks(tasks)
        summary["created"] = len(created_entries)
        summary["plant_work_orders_created"] = _append_plant_work_orders(created_entries, current)
    return summary


@contextmanager
def scan_lock(*, stale_after_minutes: int = 60):
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    lock_handle = None
    acquired = False
    try:
        if LOCK_FILE.exists():
            age_seconds = max(0.0, time.time() - LOCK_FILE.stat().st_mtime)
            if age_seconds > stale_after_minutes * 60:
                try:
                    LOCK_FILE.unlink()
                except Exception:
                    pass

        lock_handle = os.open(str(LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(lock_handle, str(os.getpid()).encode("utf-8"))
        acquired = True
        yield True
    except FileExistsError:
        yield False
    finally:
        try:
            if lock_handle is not None:
                os.close(lock_handle)
            if acquired and LOCK_FILE.exists():
                LOCK_FILE.unlink()
        except Exception:
            pass


def auto_send_admin_daily_summary_sms(
    *,
    machines: List[Dict[str, Any]],
    scan_summary: Dict[str, Any],
    settings: Dict[str, Any],
    sms_service: Any,
    now: Optional[datetime] = None,
    meta_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    current = now or datetime.now()
    out = {"sent": 0, "recipients": 0, "reason": ""}
    if not bool(settings.get("admin_daily_summary_sms_enabled", True)):
        out["reason"] = "disabled"
        return out
    if not bool(settings.get("sms_enabled", False)):
        out["reason"] = "sms_disabled"
        return out

    send_hour = max(0, min(23, _to_int(settings.get("admin_daily_summary_hour"), 20)))
    if current.hour < send_hour:
        out["reason"] = "before_send_hour"
        return out

    state = meta_state if isinstance(meta_state, dict) else load_machine_alert_meta_state()
    persist = not isinstance(meta_state, dict)
    today_key = current.date().isoformat()
    if str(state.get("admin_daily_summary_last_date") or "") == today_key:
        out["reason"] = "already_sent_today"
        return out

    recipients = get_machine_alert_recipients({}, role="admin", settings=settings)
    if not recipients:
        out["reason"] = "no_admin_recipients"
        return out
    out["recipients"] = len(recipients)

    status_counts = {"normal": 0, "maintenance": 0, "due": 0, "overdue": 0, "critical": 0}
    for machine in machines or []:
        ctx = _machine_status_context(machine, settings)
        status = str(ctx.get("status") or "normal").strip().lower()
        if status not in status_counts:
            status = "normal"
        status_counts[status] += 1

    message = (
        f"DAILY SUMMARY {today_key}: Total {len(machines)} | Normal {status_counts['normal']} | "
        f"Maint {status_counts['maintenance']} | Due {status_counts['due']} | Overdue {status_counts['overdue']} | "
        f"Critical {status_counts['critical']} | SMS {int(scan_summary.get('sms_sent', 0) or 0)} sent, "
        f"{int(scan_summary.get('failures', 0) or 0)} failed | WO {int(scan_summary.get('work_orders_created', 0) or 0)}."
    )

    for recipient in recipients:
        try:
            result = sms_service.send(recipient["phone"], message)
        except Exception as exc:
            result = {"success": False, "error": str(exc)}
        if result.get("success"):
            out["sent"] += 1

    if out["sent"]:
        state["admin_daily_summary_last_date"] = today_key
        state["admin_daily_summary_last_at"] = current.isoformat(timespec="seconds")
        if persist:
            save_machine_alert_meta_state(state)
        out["reason"] = "sent"
    else:
        out["reason"] = "send_failed"
    return out


def run_machine_alert_scan(
    *,
    machines: Optional[List[Dict[str, Any]]] = None,
    sms_service: Any = None,
    settings: Optional[Dict[str, Any]] = None,
    fallback_recipients: Optional[Iterable[Dict[str, str]]] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    configure_runner_logging()
    cfg = dict(settings or load_settings())
    summary = {
        "success": True,
        "skipped": False,
        "reason": "",
        "machine_sent": 0,
        "sms_sent": 0,
        "failures": 0,
        "pending": 0,
        "work_orders_created": 0,
        "plant_work_orders_created": 0,
        "spare_reorder_alerts_created": 0,
        "spare_reorder_sms_sent": 0,
        "maintenance_followup_alerts_created": 0,
        "maintenance_followup_sms_sent": 0,
        "missed_checklist_alerts_created": 0,
        "missed_checklist_sms_sent": 0,
        "machine_trigger_incidents_created": 0,
        "machine_trigger_incidents_by_trigger": {},
        "operator_alerts_created": 0,
        "operator_alerts_by_type": {},
        "operator_sms_sent": 0,
        "rule_engine_alerts_created": 0,
        "rule_engine_sms_sent": 0,
        "rule_engine_matches_by_rule": {},
        "predictive_alerts_created": 0,
        "predictive_sms_sent": 0,
        "predictive_high_risk_count": 0,
        "predictive_top_risk_score": 0,
        "report_scheduled": False,
        "report_email_sent": False,
        "report_reason": "",
        "report_file": None,
        "daily_summary_sms_sent": 0,
        "daily_summary_reason": "",
    }

    with scan_lock() as acquired:
        if not acquired:
            summary["skipped"] = True
            summary["reason"] = "scan_locked"
            return summary

        current = now or datetime.now()
        machine_rows = machines if machines is not None else (load_machines() or [])
        scoped_machine_rows = [dict(row) for row in machine_rows if isinstance(row, dict) and _machine_has_due_baseline(row)]
        summary["machine_scope_count"] = len(scoped_machine_rows)
        persist_rate_state = _use_persistent_rate_limit_state(cfg, sms_service)
        meta_state = load_machine_alert_meta_state()
        rate_state = meta_state if persist_rate_state else dict(meta_state)
        if not persist_rate_state:
            rate_state["sms_rate_limit"] = {}
        service = RateLimitedSMSService(sms_service or default_sms_service, cfg, rate_state)

        open_tasks: List[Dict[str, Any]] = []
        if scoped_machine_rows:
            # 1) Auto work-order generation (independent from SMS switch).
            wo = auto_generate_due_work_orders(scoped_machine_rows, settings=cfg)
            summary["work_orders_created"] = int(wo.get("created", 0) or 0)
            summary["plant_work_orders_created"] = int(wo.get("plant_work_orders_created", 0) or 0)

            # 2) Optional incident stream from machine triggers (disabled by default for machine-first workflow).
            if bool(cfg.get("machine_trigger_incident_feed_enabled", False)):
                incident_summary = auto_log_machine_trigger_incidents(scoped_machine_rows, settings=cfg)
                summary["machine_trigger_incidents_created"] = int(incident_summary.get("created", 0) or 0)
                summary["machine_trigger_incidents_by_trigger"] = dict(incident_summary.get("by_trigger") or {})

            # 3) Auto spare reorder alerts from low stock + planned maintenance.
            tasks = _load_maintenance_tasks()
            open_tasks = _open_maintenance_tasks(tasks, datetime.now())
            spare_summary = auto_generate_spare_reorder_alerts(settings=cfg, tasks=tasks, sms_service=service)
            summary["spare_reorder_alerts_created"] = int(spare_summary.get("created", 0) or 0)
            summary["spare_reorder_sms_sent"] = int(spare_summary.get("sms_sent", 0) or 0)

            # 4) Auto maintenance-not-closed follow-up reminders.
            followup_summary = auto_generate_maintenance_followup_reminders(settings=cfg, tasks=tasks, sms_service=service)
            summary["maintenance_followup_alerts_created"] = int(followup_summary.get("created", 0) or 0)
            summary["maintenance_followup_sms_sent"] = int(followup_summary.get("sms_sent", 0) or 0)

            # 5) Auto missed-checklist reminder.
            checklist_summary = auto_generate_missed_checklist_alert(settings=cfg, sms_service=service)
            summary["missed_checklist_alerts_created"] = int(checklist_summary.get("created", 0) or 0)
            summary["missed_checklist_sms_sent"] = int(checklist_summary.get("sms_sent", 0) or 0)

            # 6) Auto operator record expiry + milestone alerts.
            operator_summary = auto_generate_operator_record_alerts(settings=cfg, sms_service=service, now=current)
            summary["operator_alerts_created"] = int(operator_summary.get("created", 0) or 0)
            summary["operator_sms_sent"] = int(operator_summary.get("sms_sent", 0) or 0)
            summary["operator_alerts_by_type"] = dict(operator_summary.get("alerts_by_type") or {})
            summary["sms_sent"] += summary["operator_sms_sent"]

            # 7) Rule engine matching on machine + predictive context.
            rule_summary = auto_run_rule_engine(
                scoped_machine_rows,
                settings=cfg,
                open_tasks=open_tasks,
                sms_service=service,
            )
            summary["rule_engine_alerts_created"] = int(rule_summary.get("created", 0) or 0)
            summary["rule_engine_sms_sent"] = int(rule_summary.get("sms_sent", 0) or 0)
            summary["rule_engine_matches_by_rule"] = dict(rule_summary.get("matched_rules") or {})

            # 8) Predictive layer (risk-scored incidents + optional SMS).
            predictive_summary = auto_generate_predictive_alerts(
                scoped_machine_rows,
                settings=cfg,
                open_tasks=open_tasks,
                sms_service=service,
            )
            summary["predictive_alerts_created"] = int(predictive_summary.get("created", 0) or 0)
            summary["predictive_sms_sent"] = int(predictive_summary.get("sms_sent", 0) or 0)
            summary["predictive_high_risk_count"] = int(predictive_summary.get("high_risk_count", 0) or 0)
            summary["predictive_top_risk_score"] = int(predictive_summary.get("top_risk_score", 0) or 0)

        # 9) Scheduled report generation + email delivery (independent from SMS switch).
        report_run = maybe_deliver_scheduled_report(settings=cfg)
        summary["report_scheduled"] = bool(report_run.get("scheduled"))
        summary["report_email_sent"] = bool(report_run.get("email_sent"))
        summary["report_reason"] = str(report_run.get("reason") or "")
        summary["report_file"] = report_run.get("report_file")

        # 10) SMS engine for machine due/overdue alerts can be disabled independently.
        if not scoped_machine_rows:
            summary["skipped"] = True
            summary["reason"] = "no_machine_details"
            save_machine_alert_state({})
        elif not bool(cfg.get("sms_enabled", False)):
            summary["skipped"] = True
            summary["reason"] = "sms_disabled"
        elif not bool(cfg.get("auto_machine_alerts", True)):
            summary["skipped"] = True
            summary["reason"] = "auto_alerts_disabled"
        else:
            pending = collect_pending_machine_alerts(
                scoped_machine_rows,
                settings=cfg,
                now=current,
                fallback_recipients=fallback_recipients,
            )
            summary["pending"] = len(pending)

            if pending:
                state = load_machine_alert_state()

                for alert in pending:
                    delivered_any = False
                    for recipient in alert["recipients"]:
                        try:
                            result = service.send(recipient["phone"], alert["message"])
                        except Exception as exc:
                            result = {"success": False, "error": str(exc)}

                        if result.get("success"):
                            summary["sms_sent"] += 1
                            delivered_any = True
                        else:
                            summary["failures"] += 1
                            logger.warning(
                                "Machine alert send failed for %s to %s: %s",
                                alert["machine_id"],
                                recipient.get("phone"),
                                result.get("error") or result.get("response_text") or result,
                            )

                    if delivered_any:
                        machine_state = dict(state.get(alert["machine_id"], {}))
                        state_key_base = str(alert.get("state_key_base") or alert.get("status_key") or alert["status"]).strip().lower()
                        by_key = dict(machine_state.get("state_key_last_sent") or {}) if isinstance(machine_state.get("state_key_last_sent"), dict) else {}
                        by_key[state_key_base] = current.isoformat(timespec="seconds")
                        machine_state["state_key_last_sent"] = by_key
                        machine_state.update(
                            {
                                "status": alert["status"],
                                "status_key": alert.get("status_key") or alert["status"],
                                "last_sent_at": current.isoformat(timespec="seconds"),
                                "recipient_count": len(alert["recipients"]),
                                "message": alert["message"],
                                "trigger": str((alert.get("context") or {}).get("trigger") or ""),
                            }
                        )

                        if "escalation_day" in alert:
                            machine_state["last_escalation_day"] = int(alert.get("escalation_day", 0))
                            machine_state["escalation_role"] = str(alert.get("escalation_role") or "")
                            machine_state["escalation_started_at"] = str(alert.get("escalation_started_at") or "")
                            machine_state["escalation_lifecycle"] = str(alert.get("escalation_lifecycle") or "")
                        elif str(alert.get("status") or "").strip().lower() not in {"due", "overdue"}:
                            machine_state.pop("last_escalation_day", None)
                            machine_state.pop("escalation_role", None)
                            machine_state.pop("escalation_started_at", None)
                            machine_state.pop("escalation_lifecycle", None)

                        state[alert["machine_id"]] = machine_state
                        summary["machine_sent"] += 1

                save_machine_alert_state(state)

        if scoped_machine_rows:
            daily_summary = auto_send_admin_daily_summary_sms(
                machines=scoped_machine_rows,
                scan_summary=summary,
                settings=cfg,
                sms_service=service,
                now=current,
                meta_state=meta_state,
            )
            summary["daily_summary_sms_sent"] = int(daily_summary.get("sent", 0) or 0)
            summary["daily_summary_reason"] = str(daily_summary.get("reason") or "")
        else:
            summary["daily_summary_sms_sent"] = 0
            summary["daily_summary_reason"] = "no_machine_details"
        save_machine_alert_meta_state(meta_state if not persist_rate_state else rate_state)
        if (
            summary["machine_sent"]
            or summary["failures"]
            or summary["work_orders_created"]
            or summary["report_scheduled"]
            or summary["spare_reorder_alerts_created"]
            or summary["maintenance_followup_alerts_created"]
            or summary["missed_checklist_alerts_created"]
            or summary["machine_trigger_incidents_created"]
            or summary["operator_alerts_created"]
            or summary["rule_engine_alerts_created"]
            or summary["predictive_alerts_created"]
        ):
            logger.info(
                "Machine alert scan completed: machines=%s sms=%s failures=%s work_orders=%s spare=%s followup=%s checklist=%s incidents=%s operator=%s rules=%s predictive=%s report=%s",
                summary["machine_sent"],
                summary["sms_sent"],
                summary["failures"],
                summary["work_orders_created"],
                summary["spare_reorder_alerts_created"],
                summary["maintenance_followup_alerts_created"],
                summary["missed_checklist_alerts_created"],
                summary["machine_trigger_incidents_created"],
                summary["operator_alerts_created"],
                summary["rule_engine_alerts_created"],
                summary["predictive_alerts_created"],
                summary["report_reason"] or ("scheduled" if summary["report_scheduled"] else "not_due"),
            )
        return summary


def run_machine_alert_loop(*, interval_minutes: Optional[float] = None) -> None:
    configure_runner_logging()
    logger.info("Starting machine alert loop")
    while True:
        cfg = load_settings()
        interval = max(1.0, float(interval_minutes or cfg.get("machine_alert_interval_minutes", 5) or 5))
        run_machine_alert_scan(settings=cfg)
        time.sleep(int(interval * 60))
