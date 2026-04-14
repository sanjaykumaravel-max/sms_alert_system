from __future__ import annotations

import json
from typing import Any, Dict

try:
    from .app_paths import data_dir
except Exception:
    from app_paths import data_dir


DATA_DIR = data_dir()
SETTINGS_FILE = DATA_DIR / "settings.json"

DEFAULT_SETTINGS: Dict[str, Any] = {
    "sms_enabled": False,
    "auto_start_api_server": True,
    "api_server_engine": "auto",
    "ui_mode": "dark",
    "auto_machine_alerts": True,
    "status_change_alerts_only": True,
    "persist_sms_rate_limit_state": True,
    "sms_max_per_recipient_per_hour": 10,
    "sms_max_per_recipient_per_day": 50,
    "machine_alert_interval_minutes": 5,
    "machine_alert_cooldown_minutes": 360,
    "machine_reminder_days": 2,
    "machine_overdue_after_days": 2,
    "machine_trigger_incident_feed_enabled": False,
    "auto_work_order_generation": True,
    "auto_escalation_sms": True,
    "completion_sms_enabled": True,
    "completion_sms_include_supervisor": False,
    "completion_sms_include_admin": False,
    "admin_daily_summary_sms_enabled": True,
    "admin_daily_summary_hour": 20,
    "auto_spare_reorder_alerts": False,
    "auto_maintenance_followup_reminders": False,
    "maintenance_followup_days": 1,
    "checklist_missed_alerts_enabled": False,
    "checklist_missed_cutoff_hour": 18,
    "auto_operator_record_alerts": True,
    "auto_operator_record_sms": True,
    "operator_alert_renewal_days": 30,
    "operator_alert_rejection_days": 5,
    "rule_engine_enabled": False,
    "rule_engine_sms_enabled": False,
    "rule_engine_dedup_minutes": 360,
    "predictive_layer_enabled": False,
    "predictive_sms_enabled": False,
    "predictive_alert_threshold": 65,
    "predictive_dedup_minutes": 360,
    "escalation_operator_phones": "",
    "escalation_supervisor_phones": "",
    "escalation_admin_phones": "",
    "auto_report_delivery_enabled": False,
    "report_delivery_frequency": "daily",
    "report_delivery_hour": 18,
    "report_delivery_weekday": 0,
    "report_delivery_format": "pdf",
    "report_delivery_scope": "maintenance",
    "report_delivery_emails": "",
    "report_delivery_email_subject": "Mining Maintenance Report",
    "smtp_host": "",
    "smtp_port": 587,
    "smtp_username": "",
    "smtp_password": "",
    "smtp_sender_email": "",
    "smtp_use_tls": True,
}


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _as_int(value: Any, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        out = int(float(value))
    except Exception:
        out = default
    if minimum is not None:
        out = max(minimum, out)
    if maximum is not None:
        out = min(maximum, out)
    return out


def load_settings() -> Dict[str, Any]:
    if not SETTINGS_FILE.exists():
        return dict(DEFAULT_SETTINGS)

    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8")) or {}
    except Exception:
        return dict(DEFAULT_SETTINGS)

    mode = str(data.get("ui_mode", DEFAULT_SETTINGS["ui_mode"])).lower()
    if mode not in ("dark", "light", "system"):
        mode = "dark"

    report_frequency = str(data.get("report_delivery_frequency", DEFAULT_SETTINGS["report_delivery_frequency"])).strip().lower()
    if report_frequency not in {"daily", "weekly"}:
        report_frequency = DEFAULT_SETTINGS["report_delivery_frequency"]

    report_format = str(data.get("report_delivery_format", DEFAULT_SETTINGS["report_delivery_format"])).strip().lower()
    if report_format not in {"pdf", "html", "csv", "xlsx", "docx"}:
        report_format = DEFAULT_SETTINGS["report_delivery_format"]

    report_scope = str(data.get("report_delivery_scope", DEFAULT_SETTINGS["report_delivery_scope"])).strip().lower()
    if report_scope not in {"all", "maintenance", "machines", "operators", "schedules", "users", "completions"}:
        report_scope = DEFAULT_SETTINGS["report_delivery_scope"]

    merged = dict(DEFAULT_SETTINGS)
    merged.update(
        {
            "sms_enabled": _as_bool(data.get("sms_enabled", DEFAULT_SETTINGS["sms_enabled"]), DEFAULT_SETTINGS["sms_enabled"]),
            "auto_start_api_server": _as_bool(data.get("auto_start_api_server", DEFAULT_SETTINGS["auto_start_api_server"]), DEFAULT_SETTINGS["auto_start_api_server"]),
            "api_server_engine": str(data.get("api_server_engine", DEFAULT_SETTINGS["api_server_engine"])),
            "ui_mode": mode,
            "auto_machine_alerts": _as_bool(data.get("auto_machine_alerts", DEFAULT_SETTINGS["auto_machine_alerts"]), DEFAULT_SETTINGS["auto_machine_alerts"]),
            "status_change_alerts_only": _as_bool(data.get("status_change_alerts_only", DEFAULT_SETTINGS["status_change_alerts_only"]), DEFAULT_SETTINGS["status_change_alerts_only"]),
            "persist_sms_rate_limit_state": _as_bool(data.get("persist_sms_rate_limit_state", DEFAULT_SETTINGS["persist_sms_rate_limit_state"]), DEFAULT_SETTINGS["persist_sms_rate_limit_state"]),
            "sms_max_per_recipient_per_hour": _as_int(data.get("sms_max_per_recipient_per_hour"), DEFAULT_SETTINGS["sms_max_per_recipient_per_hour"], minimum=1, maximum=200),
            "sms_max_per_recipient_per_day": _as_int(data.get("sms_max_per_recipient_per_day"), DEFAULT_SETTINGS["sms_max_per_recipient_per_day"], minimum=1, maximum=2000),
            "machine_alert_interval_minutes": _as_int(data.get("machine_alert_interval_minutes"), DEFAULT_SETTINGS["machine_alert_interval_minutes"], minimum=1),
            "machine_alert_cooldown_minutes": _as_int(data.get("machine_alert_cooldown_minutes"), DEFAULT_SETTINGS["machine_alert_cooldown_minutes"], minimum=1),
            "machine_reminder_days": _as_int(data.get("machine_reminder_days"), DEFAULT_SETTINGS["machine_reminder_days"], minimum=1),
            "machine_overdue_after_days": _as_int(data.get("machine_overdue_after_days"), DEFAULT_SETTINGS["machine_overdue_after_days"], minimum=1),
            "machine_trigger_incident_feed_enabled": _as_bool(data.get("machine_trigger_incident_feed_enabled", DEFAULT_SETTINGS["machine_trigger_incident_feed_enabled"]), DEFAULT_SETTINGS["machine_trigger_incident_feed_enabled"]),
            "auto_work_order_generation": _as_bool(data.get("auto_work_order_generation", DEFAULT_SETTINGS["auto_work_order_generation"]), DEFAULT_SETTINGS["auto_work_order_generation"]),
            "auto_escalation_sms": _as_bool(data.get("auto_escalation_sms", DEFAULT_SETTINGS["auto_escalation_sms"]), DEFAULT_SETTINGS["auto_escalation_sms"]),
            "completion_sms_enabled": _as_bool(data.get("completion_sms_enabled", DEFAULT_SETTINGS["completion_sms_enabled"]), DEFAULT_SETTINGS["completion_sms_enabled"]),
            "completion_sms_include_supervisor": _as_bool(data.get("completion_sms_include_supervisor", DEFAULT_SETTINGS["completion_sms_include_supervisor"]), DEFAULT_SETTINGS["completion_sms_include_supervisor"]),
            "completion_sms_include_admin": _as_bool(data.get("completion_sms_include_admin", DEFAULT_SETTINGS["completion_sms_include_admin"]), DEFAULT_SETTINGS["completion_sms_include_admin"]),
            "admin_daily_summary_sms_enabled": _as_bool(data.get("admin_daily_summary_sms_enabled", DEFAULT_SETTINGS["admin_daily_summary_sms_enabled"]), DEFAULT_SETTINGS["admin_daily_summary_sms_enabled"]),
            "admin_daily_summary_hour": _as_int(data.get("admin_daily_summary_hour"), DEFAULT_SETTINGS["admin_daily_summary_hour"], minimum=0, maximum=23),
            "auto_spare_reorder_alerts": _as_bool(data.get("auto_spare_reorder_alerts", DEFAULT_SETTINGS["auto_spare_reorder_alerts"]), DEFAULT_SETTINGS["auto_spare_reorder_alerts"]),
            "auto_maintenance_followup_reminders": _as_bool(data.get("auto_maintenance_followup_reminders", DEFAULT_SETTINGS["auto_maintenance_followup_reminders"]), DEFAULT_SETTINGS["auto_maintenance_followup_reminders"]),
            "maintenance_followup_days": _as_int(data.get("maintenance_followup_days"), DEFAULT_SETTINGS["maintenance_followup_days"], minimum=1),
            "checklist_missed_alerts_enabled": _as_bool(data.get("checklist_missed_alerts_enabled", DEFAULT_SETTINGS["checklist_missed_alerts_enabled"]), DEFAULT_SETTINGS["checklist_missed_alerts_enabled"]),
            "checklist_missed_cutoff_hour": _as_int(data.get("checklist_missed_cutoff_hour"), DEFAULT_SETTINGS["checklist_missed_cutoff_hour"], minimum=0, maximum=23),
            "auto_operator_record_alerts": _as_bool(data.get("auto_operator_record_alerts", DEFAULT_SETTINGS["auto_operator_record_alerts"]), DEFAULT_SETTINGS["auto_operator_record_alerts"]),
            "auto_operator_record_sms": _as_bool(data.get("auto_operator_record_sms", DEFAULT_SETTINGS["auto_operator_record_sms"]), DEFAULT_SETTINGS["auto_operator_record_sms"]),
            "operator_alert_renewal_days": _as_int(data.get("operator_alert_renewal_days"), DEFAULT_SETTINGS["operator_alert_renewal_days"], minimum=7, maximum=120),
            "operator_alert_rejection_days": _as_int(data.get("operator_alert_rejection_days"), DEFAULT_SETTINGS["operator_alert_rejection_days"], minimum=1, maximum=30),
            "rule_engine_enabled": _as_bool(data.get("rule_engine_enabled", DEFAULT_SETTINGS["rule_engine_enabled"]), DEFAULT_SETTINGS["rule_engine_enabled"]),
            "rule_engine_sms_enabled": _as_bool(data.get("rule_engine_sms_enabled", DEFAULT_SETTINGS["rule_engine_sms_enabled"]), DEFAULT_SETTINGS["rule_engine_sms_enabled"]),
            "rule_engine_dedup_minutes": _as_int(data.get("rule_engine_dedup_minutes"), DEFAULT_SETTINGS["rule_engine_dedup_minutes"], minimum=30),
            "predictive_layer_enabled": _as_bool(data.get("predictive_layer_enabled", DEFAULT_SETTINGS["predictive_layer_enabled"]), DEFAULT_SETTINGS["predictive_layer_enabled"]),
            "predictive_sms_enabled": _as_bool(data.get("predictive_sms_enabled", DEFAULT_SETTINGS["predictive_sms_enabled"]), DEFAULT_SETTINGS["predictive_sms_enabled"]),
            "predictive_alert_threshold": _as_int(data.get("predictive_alert_threshold"), DEFAULT_SETTINGS["predictive_alert_threshold"], minimum=40, maximum=95),
            "predictive_dedup_minutes": _as_int(data.get("predictive_dedup_minutes"), DEFAULT_SETTINGS["predictive_dedup_minutes"], minimum=30),
            "escalation_operator_phones": str(data.get("escalation_operator_phones", DEFAULT_SETTINGS["escalation_operator_phones"]) or ""),
            "escalation_supervisor_phones": str(data.get("escalation_supervisor_phones", DEFAULT_SETTINGS["escalation_supervisor_phones"]) or ""),
            "escalation_admin_phones": str(data.get("escalation_admin_phones", DEFAULT_SETTINGS["escalation_admin_phones"]) or ""),
            "auto_report_delivery_enabled": _as_bool(data.get("auto_report_delivery_enabled", DEFAULT_SETTINGS["auto_report_delivery_enabled"]), DEFAULT_SETTINGS["auto_report_delivery_enabled"]),
            "report_delivery_frequency": report_frequency,
            "report_delivery_hour": _as_int(data.get("report_delivery_hour"), DEFAULT_SETTINGS["report_delivery_hour"], minimum=0, maximum=23),
            "report_delivery_weekday": _as_int(data.get("report_delivery_weekday"), DEFAULT_SETTINGS["report_delivery_weekday"], minimum=0, maximum=6),
            "report_delivery_format": report_format,
            "report_delivery_scope": report_scope,
            "report_delivery_emails": str(data.get("report_delivery_emails", DEFAULT_SETTINGS["report_delivery_emails"]) or ""),
            "report_delivery_email_subject": str(data.get("report_delivery_email_subject", DEFAULT_SETTINGS["report_delivery_email_subject"]) or ""),
            "smtp_host": str(data.get("smtp_host", DEFAULT_SETTINGS["smtp_host"]) or ""),
            "smtp_port": _as_int(data.get("smtp_port"), DEFAULT_SETTINGS["smtp_port"], minimum=1, maximum=65535),
            "smtp_username": str(data.get("smtp_username", DEFAULT_SETTINGS["smtp_username"]) or ""),
            "smtp_password": str(data.get("smtp_password", DEFAULT_SETTINGS["smtp_password"]) or ""),
            "smtp_sender_email": str(data.get("smtp_sender_email", DEFAULT_SETTINGS["smtp_sender_email"]) or ""),
            "smtp_use_tls": _as_bool(data.get("smtp_use_tls", DEFAULT_SETTINGS["smtp_use_tls"]), DEFAULT_SETTINGS["smtp_use_tls"]),
        }
    )
    return merged


def save_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(DEFAULT_SETTINGS)
    merged.update(settings or {})
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    return merged
