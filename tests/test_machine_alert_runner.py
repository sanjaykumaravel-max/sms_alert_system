from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from src import incident_store
from src import machine_alert_runner as runner
from src import rule_engine


class FakeSMSService:
    def __init__(self):
        self.sent = []

    def send(self, phone: str, message: str):
        self.sent.append((phone, message))
        return {"success": True}


def _date_str(delta_days: int) -> str:
    return (datetime.now().date() + timedelta(days=delta_days)).isoformat()


def _sandbox_dir() -> Path:
    base = Path("tests") / ".runtime_tmp" / f"machine_alert_runner_{uuid4().hex}"
    base.mkdir(parents=True, exist_ok=True)
    return base


def test_collect_pending_machine_alerts_respects_cooldown(monkeypatch):
    sandbox = _sandbox_dir()
    monkeypatch.setattr(runner, "STATE_FILE", sandbox / "machine_alert_state.json")
    monkeypatch.setattr(runner, "LOCK_FILE", sandbox / "machine_alert_runner.lock")
    monkeypatch.setattr(runner, "configure_runner_logging", lambda: None)

    machine = {
        "id": "JC-01",
        "name": "Jaw Crusher",
        "due_date": _date_str(2),
        "operator_phone": "6381528758",
        "status": "normal",
    }
    settings = {
        "sms_enabled": True,
        "auto_machine_alerts": True,
        "machine_alert_cooldown_minutes": 360,
        "machine_reminder_days": 3,
        "machine_overdue_after_days": 2,
    }

    pending = runner.collect_pending_machine_alerts([machine], settings=settings, now=datetime.now())
    assert len(pending) == 1
    assert pending[0]["status"] == "maintenance"
    assert pending[0]["recipients"][0]["phone"] == "+916381528758"

    runner.STATE_FILE.write_text(
        json.dumps(
            {
                "JC-01": {
                    "status": "maintenance",
                    "status_key": "maintenance:date",
                    "last_sent_at": datetime.now().isoformat(timespec="seconds"),
                    "state_key_last_sent": {"maintenance:date": datetime.now().isoformat(timespec="seconds")},
                }
            }
        ),
        encoding="utf-8",
    )

    pending_again = runner.collect_pending_machine_alerts([machine], settings=settings, now=datetime.now())
    assert pending_again == []


def test_run_machine_alert_scan_uses_fallback_recipients_and_updates_state(monkeypatch):
    sandbox = _sandbox_dir()
    monkeypatch.setattr(runner, "STATE_FILE", sandbox / "machine_alert_state.json")
    monkeypatch.setattr(runner, "LOCK_FILE", sandbox / "machine_alert_runner.lock")
    monkeypatch.setattr(runner, "configure_runner_logging", lambda: None)

    sms_service = FakeSMSService()
    machine = {
        "id": "CC-02",
        "name": "Cone Crusher",
        "due_date": _date_str(-2),
        "status": "normal",
    }
    settings = {
        "sms_enabled": True,
        "auto_machine_alerts": True,
        "machine_alert_cooldown_minutes": 60,
        "machine_reminder_days": 3,
        "machine_overdue_after_days": 2,
    }
    fallback_recipients = [{"name": "Supervisor", "phone": "+916381528758", "source": "file"}]

    summary = runner.run_machine_alert_scan(
        machines=[machine],
        sms_service=sms_service,
        settings=settings,
        fallback_recipients=fallback_recipients,
    )

    assert summary["success"] is True
    assert summary["machine_sent"] == 1
    assert summary["sms_sent"] == 1
    assert summary["failures"] == 0
    assert sms_service.sent[0][0] == "+916381528758"

    state = json.loads(runner.STATE_FILE.read_text(encoding="utf-8"))
    assert state["CC-02"]["status"] == "overdue"


def test_run_machine_alert_scan_sends_hour_based_due_message(monkeypatch):
    sandbox = _sandbox_dir()
    monkeypatch.setattr(runner, "STATE_FILE", sandbox / "machine_alert_state.json")
    monkeypatch.setattr(runner, "LOCK_FILE", sandbox / "machine_alert_runner.lock")
    monkeypatch.setattr(runner, "configure_runner_logging", lambda: None)

    sms_service = FakeSMSService()
    machine = {
        "id": "EX-01",
        "name": "Excavator",
        "hours": "1000",
        "next_due_hours": "1000",
        "operator_phone": "6381528758",
        "status": "normal",
    }
    settings = {
        "sms_enabled": True,
        "auto_machine_alerts": True,
        "machine_alert_cooldown_minutes": 60,
        "machine_reminder_days": 3,
        "machine_overdue_after_days": 2,
    }

    summary = runner.run_machine_alert_scan(
        machines=[machine],
        sms_service=sms_service,
        settings=settings,
    )

    assert summary["machine_sent"] == 1
    assert "running hours" in sms_service.sent[0][1]


def test_collect_pending_machine_alerts_escalates_to_supervisor_on_day_minus_one(monkeypatch):
    sandbox = _sandbox_dir()
    monkeypatch.setattr(runner, "STATE_FILE", sandbox / "machine_alert_state.json")
    monkeypatch.setattr(runner, "LOCK_FILE", sandbox / "machine_alert_runner.lock")
    monkeypatch.setattr(runner, "configure_runner_logging", lambda: None)

    machine = {
        "id": "JC-77",
        "name": "Jaw Crusher",
        "due_date": _date_str(1),
        "status": "normal",
    }
    settings = {
        "sms_enabled": True,
        "auto_machine_alerts": True,
        "auto_escalation_sms": True,
        "machine_alert_cooldown_minutes": 360,
        "machine_reminder_days": 3,
        "machine_overdue_after_days": 2,
        "escalation_supervisor_phones": "+916381528758",
    }

    pending = runner.collect_pending_machine_alerts([machine], settings=settings, now=datetime.now())
    assert len(pending) == 1
    assert pending[0]["escalation_day"] == 1
    assert pending[0]["escalation_role"] == "supervisor"
    assert pending[0]["recipients"][0]["phone"] == "+916381528758"


def test_run_machine_alert_scan_generates_work_order_when_sms_disabled(monkeypatch):
    sandbox = _sandbox_dir()
    monkeypatch.setattr(runner, "STATE_FILE", sandbox / "machine_alert_state.json")
    monkeypatch.setattr(runner, "LOCK_FILE", sandbox / "machine_alert_runner.lock")
    monkeypatch.setattr(runner, "MAINTENANCE_TASKS_FILE", sandbox / "maintenance_tasks.json")
    monkeypatch.setattr(runner, "PLANT_MAINTENANCE_STATE_FILE", sandbox / "plant_maintenance_state.json")
    monkeypatch.setattr(runner, "configure_runner_logging", lambda: None)
    monkeypatch.setattr(
        runner,
        "maybe_deliver_scheduled_report",
        lambda settings=None: {"scheduled": False, "email_sent": False, "reason": "report_delivery_disabled", "report_file": None},
    )

    machine = {
        "id": "CC-09",
        "name": "Cone Crusher",
        "due_date": _date_str(-2),
        "status": "normal",
    }
    settings = {
        "sms_enabled": False,
        "auto_machine_alerts": True,
        "auto_work_order_generation": True,
        "machine_reminder_days": 3,
        "machine_overdue_after_days": 2,
    }

    summary = runner.run_machine_alert_scan(machines=[machine], settings=settings)
    assert summary["skipped"] is True
    assert summary["reason"] == "sms_disabled"
    assert summary["work_orders_created"] == 1

    tasks = json.loads((sandbox / "maintenance_tasks.json").read_text(encoding="utf-8"))
    assert len(tasks) == 1
    assert tasks[0]["machine_id"] == "CC-09"
    assert tasks[0]["auto_generated"] is True


def test_run_machine_alert_scan_exposes_report_scheduler_summary(monkeypatch):
    sandbox = _sandbox_dir()
    monkeypatch.setattr(runner, "STATE_FILE", sandbox / "machine_alert_state.json")
    monkeypatch.setattr(runner, "LOCK_FILE", sandbox / "machine_alert_runner.lock")
    monkeypatch.setattr(runner, "MAINTENANCE_TASKS_FILE", sandbox / "maintenance_tasks.json")
    monkeypatch.setattr(runner, "PLANT_MAINTENANCE_STATE_FILE", sandbox / "plant_maintenance_state.json")
    monkeypatch.setattr(runner, "configure_runner_logging", lambda: None)
    monkeypatch.setattr(
        runner,
        "maybe_deliver_scheduled_report",
        lambda settings=None: {
            "scheduled": True,
            "email_sent": True,
            "reason": "sent",
            "report_file": str(sandbox / "auto_report.pdf"),
        },
    )

    summary = runner.run_machine_alert_scan(
        machines=[],
        settings={"sms_enabled": False, "auto_machine_alerts": True, "auto_work_order_generation": False},
    )
    assert summary["report_scheduled"] is True
    assert summary["report_email_sent"] is True
    assert summary["report_reason"] == "sent"


def test_spare_reorder_alert_created_from_min_stock_and_planned_maintenance(monkeypatch):
    sandbox = _sandbox_dir()
    monkeypatch.setattr(runner, "STATE_FILE", sandbox / "machine_alert_state.json")
    monkeypatch.setattr(runner, "LOCK_FILE", sandbox / "machine_alert_runner.lock")
    monkeypatch.setattr(runner, "MAINTENANCE_TASKS_FILE", sandbox / "maintenance_tasks.json")
    monkeypatch.setattr(runner, "PARTS_FILE", sandbox / "parts.json")
    monkeypatch.setattr(runner, "CHECKLISTS_FILE", sandbox / "checklists.json")
    monkeypatch.setattr(runner, "PLANT_MAINTENANCE_STATE_FILE", sandbox / "plant_maintenance_state.json")
    monkeypatch.setattr(incident_store, "INCIDENTS_FILE", sandbox / "incident_feed.json")
    monkeypatch.setattr(runner, "configure_runner_logging", lambda: None)
    monkeypatch.setattr(
        runner,
        "maybe_deliver_scheduled_report",
        lambda settings=None: {"scheduled": False, "email_sent": False, "reason": "report_delivery_disabled", "report_file": None},
    )

    (sandbox / "parts.json").write_text(
        json.dumps([{"name": "Jaw Plate", "quantity_on_hand": 0, "min_stock_level": 1}], indent=2),
        encoding="utf-8",
    )
    (sandbox / "maintenance_tasks.json").write_text(
        json.dumps(
            [
                {
                    "id": "TASK-001",
                    "subject": "Planned maintenance JC-01",
                    "machine_id": "JC-01",
                    "status": "pending",
                    "condition_status": "due",
                    "due_date": datetime.now().date().isoformat(),
                }
            ],
            indent=2,
        ),
        encoding="utf-8",
    )

    summary = runner.run_machine_alert_scan(
        machines=[{"id": "BASE-SPARE", "name": "Base", "due_date": _date_str(10), "status": "normal"}],
        settings={
            "sms_enabled": False,
            "auto_machine_alerts": False,
            "auto_work_order_generation": False,
            "auto_spare_reorder_alerts": True,
            "auto_maintenance_followup_reminders": False,
            "checklist_missed_alerts_enabled": False,
        },
    )
    assert summary["spare_reorder_alerts_created"] == 1
    incidents = json.loads((sandbox / "incident_feed.json").read_text(encoding="utf-8"))
    assert any(str(item.get("category")) == "spare_reorder" for item in incidents)


def test_maintenance_not_closed_followup_incident_created(monkeypatch):
    sandbox = _sandbox_dir()
    monkeypatch.setattr(runner, "STATE_FILE", sandbox / "machine_alert_state.json")
    monkeypatch.setattr(runner, "LOCK_FILE", sandbox / "machine_alert_runner.lock")
    monkeypatch.setattr(runner, "MAINTENANCE_TASKS_FILE", sandbox / "maintenance_tasks.json")
    monkeypatch.setattr(runner, "PARTS_FILE", sandbox / "parts.json")
    monkeypatch.setattr(runner, "CHECKLISTS_FILE", sandbox / "checklists.json")
    monkeypatch.setattr(runner, "PLANT_MAINTENANCE_STATE_FILE", sandbox / "plant_maintenance_state.json")
    monkeypatch.setattr(incident_store, "INCIDENTS_FILE", sandbox / "incident_feed.json")
    monkeypatch.setattr(runner, "configure_runner_logging", lambda: None)
    monkeypatch.setattr(
        runner,
        "maybe_deliver_scheduled_report",
        lambda settings=None: {"scheduled": False, "email_sent": False, "reason": "report_delivery_disabled", "report_file": None},
    )

    stale = (datetime.now() - timedelta(days=2)).isoformat(timespec="seconds")
    (sandbox / "maintenance_tasks.json").write_text(
        json.dumps(
            [
                {
                    "id": "TASK-FO-1",
                    "subject": "Hydraulic service",
                    "machine_id": "EX-01",
                    "status": "pending",
                    "scheduled_at": stale,
                }
            ],
            indent=2,
        ),
        encoding="utf-8",
    )

    summary = runner.run_machine_alert_scan(
        machines=[{"id": "BASE-FOLLOW", "name": "Base", "due_date": _date_str(10), "status": "normal"}],
        settings={
            "sms_enabled": False,
            "auto_machine_alerts": False,
            "auto_work_order_generation": False,
            "auto_spare_reorder_alerts": False,
            "auto_maintenance_followup_reminders": True,
            "maintenance_followup_days": 1,
            "checklist_missed_alerts_enabled": False,
        },
    )
    assert summary["maintenance_followup_alerts_created"] == 1
    incidents = json.loads((sandbox / "incident_feed.json").read_text(encoding="utf-8"))
    assert any(str(item.get("category")) == "maintenance_followup" for item in incidents)


def test_missed_checklist_incident_created_after_cutoff(monkeypatch):
    sandbox = _sandbox_dir()
    monkeypatch.setattr(runner, "STATE_FILE", sandbox / "machine_alert_state.json")
    monkeypatch.setattr(runner, "LOCK_FILE", sandbox / "machine_alert_runner.lock")
    monkeypatch.setattr(runner, "MAINTENANCE_TASKS_FILE", sandbox / "maintenance_tasks.json")
    monkeypatch.setattr(runner, "PARTS_FILE", sandbox / "parts.json")
    monkeypatch.setattr(runner, "CHECKLISTS_FILE", sandbox / "checklists.json")
    monkeypatch.setattr(runner, "PLANT_MAINTENANCE_STATE_FILE", sandbox / "plant_maintenance_state.json")
    monkeypatch.setattr(incident_store, "INCIDENTS_FILE", sandbox / "incident_feed.json")
    monkeypatch.setattr(runner, "configure_runner_logging", lambda: None)
    monkeypatch.setattr(
        runner,
        "maybe_deliver_scheduled_report",
        lambda settings=None: {"scheduled": False, "email_sent": False, "reason": "report_delivery_disabled", "report_file": None},
    )

    (sandbox / "checklists.json").write_text(json.dumps({"template_items": ["Oil"], "entries": []}, indent=2), encoding="utf-8")
    summary = runner.run_machine_alert_scan(
        machines=[{"id": "BASE-CHECK", "name": "Base", "due_date": _date_str(10), "status": "normal"}],
        settings={
            "sms_enabled": False,
            "auto_machine_alerts": False,
            "auto_work_order_generation": False,
            "auto_spare_reorder_alerts": False,
            "auto_maintenance_followup_reminders": False,
            "checklist_missed_alerts_enabled": True,
            "checklist_missed_cutoff_hour": 0,
        },
    )
    assert summary["missed_checklist_alerts_created"] == 1
    incidents = json.loads((sandbox / "incident_feed.json").read_text(encoding="utf-8"))
    assert any(str(item.get("trigger")) == "missed_checklist" for item in incidents)


def test_machine_trigger_incidents_cover_hour_date_manual(monkeypatch):
    sandbox = _sandbox_dir()
    monkeypatch.setattr(runner, "STATE_FILE", sandbox / "machine_alert_state.json")
    monkeypatch.setattr(runner, "LOCK_FILE", sandbox / "machine_alert_runner.lock")
    monkeypatch.setattr(runner, "MAINTENANCE_TASKS_FILE", sandbox / "maintenance_tasks.json")
    monkeypatch.setattr(runner, "PARTS_FILE", sandbox / "parts.json")
    monkeypatch.setattr(runner, "CHECKLISTS_FILE", sandbox / "checklists.json")
    monkeypatch.setattr(runner, "PLANT_MAINTENANCE_STATE_FILE", sandbox / "plant_maintenance_state.json")
    monkeypatch.setattr(incident_store, "INCIDENTS_FILE", sandbox / "incident_feed.json")
    monkeypatch.setattr(runner, "configure_runner_logging", lambda: None)
    monkeypatch.setattr(
        runner,
        "maybe_deliver_scheduled_report",
        lambda settings=None: {"scheduled": False, "email_sent": False, "reason": "report_delivery_disabled", "report_file": None},
    )

    machines = [
        {"id": "M-DATE", "name": "Date Rule", "due_date": datetime.now().date().isoformat(), "status": "normal"},
        {"id": "M-HOUR", "name": "Hour Rule", "hours": "1000", "next_due_hours": "1000", "status": "normal"},
        {"id": "M-MANUAL", "name": "Manual Rule", "status": "critical"},
    ]
    summary = runner.run_machine_alert_scan(
        machines=machines,
        settings={
            "sms_enabled": False,
            "auto_machine_alerts": False,
            "machine_trigger_incident_feed_enabled": True,
            "auto_work_order_generation": False,
            "auto_spare_reorder_alerts": False,
            "auto_maintenance_followup_reminders": False,
            "checklist_missed_alerts_enabled": False,
            "machine_reminder_days": 3,
            "machine_overdue_after_days": 2,
        },
    )
    assert summary["machine_trigger_incidents_created"] >= 2
    by_trigger = summary.get("machine_trigger_incidents_by_trigger") or {}
    assert int(by_trigger.get("date", 0)) >= 1
    assert int(by_trigger.get("hours", 0)) >= 1
    assert int(by_trigger.get("manual", 0)) == 0


def test_rule_engine_and_predictive_layer_generate_incidents(monkeypatch):
    sandbox = _sandbox_dir()
    monkeypatch.setattr(runner, "STATE_FILE", sandbox / "machine_alert_state.json")
    monkeypatch.setattr(runner, "LOCK_FILE", sandbox / "machine_alert_runner.lock")
    monkeypatch.setattr(runner, "MAINTENANCE_TASKS_FILE", sandbox / "maintenance_tasks.json")
    monkeypatch.setattr(runner, "PARTS_FILE", sandbox / "parts.json")
    monkeypatch.setattr(runner, "CHECKLISTS_FILE", sandbox / "checklists.json")
    monkeypatch.setattr(runner, "PLANT_MAINTENANCE_STATE_FILE", sandbox / "plant_maintenance_state.json")
    monkeypatch.setattr(incident_store, "INCIDENTS_FILE", sandbox / "incident_feed.json")
    monkeypatch.setattr(rule_engine, "RULES_FILE", sandbox / "rule_engine_rules.json")
    monkeypatch.setattr(runner, "configure_runner_logging", lambda: None)
    monkeypatch.setattr(
        runner,
        "maybe_deliver_scheduled_report",
        lambda settings=None: {"scheduled": False, "email_sent": False, "reason": "report_delivery_disabled", "report_file": None},
    )

    (sandbox / "rule_engine_rules.json").write_text(
        json.dumps(
            [
                {
                    "id": "high_risk_any",
                    "name": "High risk machine",
                    "enabled": True,
                    "severity": "warning",
                    "trigger": "rule_engine",
                    "dedup_window_minutes": 30,
                    "condition": {"field": "risk_score", "op": "gte", "value": 60},
                    "message_template": "{machine_id} risk score {risk_score}",
                }
            ],
            indent=2,
        ),
        encoding="utf-8",
    )

    machines = [
        {
            "id": "EX-HR",
            "name": "Excavator Risk",
            "hours": "1260",
            "next_due_hours": "1200",
            "hour_overdue_after_hours": "5",
            "status": "normal",
        }
    ]
    summary = runner.run_machine_alert_scan(
        machines=machines,
        settings={
            "sms_enabled": False,
            "auto_machine_alerts": False,
            "auto_work_order_generation": False,
            "auto_spare_reorder_alerts": False,
            "auto_maintenance_followup_reminders": False,
            "checklist_missed_alerts_enabled": False,
            "rule_engine_enabled": True,
            "predictive_layer_enabled": True,
            "predictive_alert_threshold": 60,
        },
    )
    assert summary["rule_engine_alerts_created"] >= 1
    assert summary["predictive_alerts_created"] >= 1
    incidents = json.loads((sandbox / "incident_feed.json").read_text(encoding="utf-8"))
    categories = {str(item.get("category") or "") for item in incidents}
    assert "rule_engine" in categories
    assert "predictive" in categories


def test_status_change_alerts_only_blocks_repeat_even_after_cooldown(monkeypatch):
    sandbox = _sandbox_dir()
    monkeypatch.setattr(runner, "STATE_FILE", sandbox / "machine_alert_state.json")
    monkeypatch.setattr(runner, "LOCK_FILE", sandbox / "machine_alert_runner.lock")
    monkeypatch.setattr(runner, "configure_runner_logging", lambda: None)

    runner.STATE_FILE.write_text(
        json.dumps(
            {
                "JC-11": {
                    "status": "due",
                    "status_key": "due:date",
                    "last_sent_at": (datetime.now() - timedelta(days=3)).isoformat(timespec="seconds"),
                }
            }
        ),
        encoding="utf-8",
    )
    machine = {
        "id": "JC-11",
        "name": "Jaw Crusher",
        "due_date": _date_str(0),
        "status": "normal",
        "operator_phone": "6381528758",
    }
    settings = {
        "sms_enabled": True,
        "auto_machine_alerts": True,
        "auto_escalation_sms": False,
        "status_change_alerts_only": True,
        "machine_alert_cooldown_minutes": 1,
        "machine_reminder_days": 3,
        "machine_overdue_after_days": 2,
    }

    pending = runner.collect_pending_machine_alerts([machine], settings=settings, now=datetime.now())
    assert pending == []


def test_send_maintenance_completion_sms_includes_rolled_due_details():
    sms = FakeSMSService()
    machine = {
        "id": "MC-88",
        "name": "Primary Crusher",
        "operator_phone": "6381528758",
        "next_maintenance": _date_str(30),
        "next_due_hours": "1450",
        "last_maintenance_completed_at": datetime.now().isoformat(timespec="seconds"),
    }
    result = runner.send_maintenance_completion_sms(
        machine,
        completed_by="Sanjay",
        settings={
            "sms_enabled": True,
            "completion_sms_enabled": True,
            "completion_sms_include_supervisor": False,
            "completion_sms_include_admin": False,
        },
        sms_service=sms,
    )
    assert result["sent"] == 1
    assert result["failures"] == 0
    assert "Next due date" in sms.sent[0][1]
    assert "Next due hours" in sms.sent[0][1]


def test_admin_daily_summary_sms_sent_once_per_day(monkeypatch):
    sandbox = _sandbox_dir()
    monkeypatch.setattr(runner, "STATE_FILE", sandbox / "machine_alert_state.json")
    monkeypatch.setattr(runner, "META_STATE_FILE", sandbox / "machine_alert_meta_state.json")
    monkeypatch.setattr(runner, "LOCK_FILE", sandbox / "machine_alert_runner.lock")
    monkeypatch.setattr(runner, "MAINTENANCE_TASKS_FILE", sandbox / "maintenance_tasks.json")
    monkeypatch.setattr(runner, "PARTS_FILE", sandbox / "parts.json")
    monkeypatch.setattr(runner, "CHECKLISTS_FILE", sandbox / "checklists.json")
    monkeypatch.setattr(runner, "PLANT_MAINTENANCE_STATE_FILE", sandbox / "plant_maintenance_state.json")
    monkeypatch.setattr(incident_store, "INCIDENTS_FILE", sandbox / "incident_feed.json")
    monkeypatch.setattr(runner, "configure_runner_logging", lambda: None)
    monkeypatch.setattr(
        runner,
        "maybe_deliver_scheduled_report",
        lambda settings=None: {"scheduled": False, "email_sent": False, "reason": "report_delivery_disabled", "report_file": None},
    )

    sms = FakeSMSService()
    now = datetime.now().replace(hour=21, minute=0, second=0, microsecond=0)
    settings = {
        "sms_enabled": True,
        "auto_machine_alerts": False,
        "auto_work_order_generation": False,
        "auto_spare_reorder_alerts": False,
        "auto_maintenance_followup_reminders": False,
        "checklist_missed_alerts_enabled": False,
        "admin_daily_summary_sms_enabled": True,
        "admin_daily_summary_hour": 20,
        "escalation_admin_phones": "+916381528758",
    }
    machines = [{"id": "EX-03", "name": "Excavator", "status": "normal", "due_date": _date_str(7)}]

    first = runner.run_machine_alert_scan(machines=machines, sms_service=sms, settings=settings, now=now)
    assert first["daily_summary_sms_sent"] == 1
    assert first["daily_summary_reason"] == "sent"
    assert len(sms.sent) == 1

    second = runner.run_machine_alert_scan(machines=machines, sms_service=sms, settings=settings, now=now)
    assert second["daily_summary_sms_sent"] == 0
    assert second["daily_summary_reason"] == "already_sent_today"
    assert len(sms.sent) == 1


def test_cooldown_is_applied_per_machine_status_trigger_key(monkeypatch):
    sandbox = _sandbox_dir()
    monkeypatch.setattr(runner, "STATE_FILE", sandbox / "machine_alert_state.json")
    monkeypatch.setattr(runner, "LOCK_FILE", sandbox / "machine_alert_runner.lock")
    monkeypatch.setattr(runner, "configure_runner_logging", lambda: None)

    runner.STATE_FILE.write_text(
        json.dumps(
            {
                "MC-22": {
                    "status": "normal",
                    "status_key": "normal:manual",
                    "state_key_last_sent": {
                        "due:date": datetime.now().isoformat(timespec="seconds"),
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    machine = {
        "id": "MC-22",
        "name": "Crusher 22",
        "due_date": _date_str(0),
        "operator_phone": "6381528758",
        "status": "normal",
    }
    settings = {
        "sms_enabled": True,
        "auto_machine_alerts": True,
        "auto_escalation_sms": False,
        "status_change_alerts_only": False,
        "machine_alert_cooldown_minutes": 60,
        "machine_reminder_days": 3,
        "machine_overdue_after_days": 2,
    }
    pending = runner.collect_pending_machine_alerts([machine], settings=settings, now=datetime.now())
    assert pending == []


def test_per_recipient_rate_limit_caps_sms_per_hour(monkeypatch):
    sandbox = _sandbox_dir()
    monkeypatch.setattr(runner, "STATE_FILE", sandbox / "machine_alert_state.json")
    monkeypatch.setattr(runner, "META_STATE_FILE", sandbox / "machine_alert_meta_state.json")
    monkeypatch.setattr(runner, "LOCK_FILE", sandbox / "machine_alert_runner.lock")
    monkeypatch.setattr(runner, "MAINTENANCE_TASKS_FILE", sandbox / "maintenance_tasks.json")
    monkeypatch.setattr(runner, "PARTS_FILE", sandbox / "parts.json")
    monkeypatch.setattr(runner, "CHECKLISTS_FILE", sandbox / "checklists.json")
    monkeypatch.setattr(runner, "PLANT_MAINTENANCE_STATE_FILE", sandbox / "plant_maintenance_state.json")
    monkeypatch.setattr(incident_store, "INCIDENTS_FILE", sandbox / "incident_feed.json")
    monkeypatch.setattr(runner, "configure_runner_logging", lambda: None)
    monkeypatch.setattr(
        runner,
        "maybe_deliver_scheduled_report",
        lambda settings=None: {"scheduled": False, "email_sent": False, "reason": "report_delivery_disabled", "report_file": None},
    )

    sms = FakeSMSService()
    machines = [
        {"id": "MC-31", "name": "M1", "due_date": _date_str(0), "operator_phone": "6381528758", "status": "normal"},
        {"id": "MC-32", "name": "M2", "due_date": _date_str(0), "operator_phone": "6381528758", "status": "normal"},
    ]
    summary = runner.run_machine_alert_scan(
        machines=machines,
        sms_service=sms,
        settings={
            "sms_enabled": True,
            "auto_machine_alerts": True,
            "auto_escalation_sms": False,
            "status_change_alerts_only": False,
            "machine_alert_cooldown_minutes": 1,
            "machine_reminder_days": 3,
            "machine_overdue_after_days": 2,
            "sms_max_per_recipient_per_hour": 1,
            "sms_max_per_recipient_per_day": 5,
            "admin_daily_summary_sms_enabled": False,
        },
    )
    assert summary["machine_sent"] == 1
    assert summary["sms_sent"] == 1
    assert summary["failures"] >= 1
    assert len(sms.sent) == 1


def test_auto_stop_reminders_when_machine_returns_normal(monkeypatch):
    sandbox = _sandbox_dir()
    monkeypatch.setattr(runner, "STATE_FILE", sandbox / "machine_alert_state.json")
    monkeypatch.setattr(runner, "LOCK_FILE", sandbox / "machine_alert_runner.lock")
    monkeypatch.setattr(runner, "configure_runner_logging", lambda: None)

    runner.STATE_FILE.write_text(
        json.dumps(
            {
                "MC-77": {
                    "status": "due",
                    "status_key": "due:date",
                    "last_sent_at": datetime.now().isoformat(timespec="seconds"),
                    "last_escalation_day": 1,
                    "escalation_role": "supervisor",
                    "escalation_started_at": datetime.now().isoformat(timespec="seconds"),
                    "escalation_lifecycle": datetime.now().date().isoformat(),
                }
            }
        ),
        encoding="utf-8",
    )
    machine = {
        "id": "MC-77",
        "name": "Crusher 77",
        "due_date": _date_str(10),
        "status": "normal",
    }
    pending = runner.collect_pending_machine_alerts(
        [machine],
        settings={
            "sms_enabled": True,
            "auto_machine_alerts": True,
            "status_change_alerts_only": True,
            "machine_alert_cooldown_minutes": 60,
            "machine_reminder_days": 3,
            "machine_overdue_after_days": 2,
        },
        now=datetime.now(),
    )
    assert pending == []
    state = json.loads(runner.STATE_FILE.read_text(encoding="utf-8"))
    assert state["MC-77"]["status"] == "normal"
    assert "last_escalation_day" not in state["MC-77"]


def test_operator_record_alerts_generate_renewal_rejection_and_service_sms(monkeypatch):
    sandbox = _sandbox_dir()
    monkeypatch.setattr(runner, "STATE_FILE", sandbox / "machine_alert_state.json")
    monkeypatch.setattr(runner, "OPERATORS_EXTENDED_FILE", sandbox / "operators_extended.json")
    monkeypatch.setattr(incident_store, "INCIDENTS_FILE", sandbox / "incident_feed.json")
    monkeypatch.setattr(runner, "configure_runner_logging", lambda: None)

    today = datetime.now().date()
    (sandbox / "operators_extended.json").write_text(
        json.dumps(
            [
                {
                    "id": "OPR-0001",
                    "name": "Sanjay",
                    "phone": "6381528758",
                    "license_expiry": (today + timedelta(days=20)).isoformat(),
                    "medical_certificate_end_date": (today + timedelta(days=4)).isoformat(),
                    "company_start_date": (today - timedelta(days=365 * 11)).isoformat(),
                }
            ],
            indent=2,
        ),
        encoding="utf-8",
    )

    sms = FakeSMSService()
    settings = {
        "sms_enabled": True,
        "auto_operator_record_alerts": True,
        "auto_operator_record_sms": True,
        "operator_alert_renewal_days": 30,
        "operator_alert_rejection_days": 5,
        "machine_alert_cooldown_minutes": 60,
    }

    first = runner.auto_generate_operator_record_alerts(settings=settings, sms_service=sms, now=datetime.now())
    assert first["created"] == 3
    assert first["alerts_by_type"]["renewal"] == 1
    assert first["alerts_by_type"]["rejection"] == 1
    assert first["alerts_by_type"]["service_10y"] == 1
    assert first["sms_sent"] == 3
    assert len(sms.sent) == 3

    second = runner.auto_generate_operator_record_alerts(settings=settings, sms_service=sms, now=datetime.now())
    assert second["created"] == 0
    assert second["sms_sent"] == 0


def test_run_machine_alert_scan_includes_operator_record_alert_summary(monkeypatch):
    sandbox = _sandbox_dir()
    monkeypatch.setattr(runner, "STATE_FILE", sandbox / "machine_alert_state.json")
    monkeypatch.setattr(runner, "LOCK_FILE", sandbox / "machine_alert_runner.lock")
    monkeypatch.setattr(runner, "MAINTENANCE_TASKS_FILE", sandbox / "maintenance_tasks.json")
    monkeypatch.setattr(runner, "PARTS_FILE", sandbox / "parts.json")
    monkeypatch.setattr(runner, "CHECKLISTS_FILE", sandbox / "checklists.json")
    monkeypatch.setattr(runner, "PLANT_MAINTENANCE_STATE_FILE", sandbox / "plant_maintenance_state.json")
    monkeypatch.setattr(runner, "OPERATORS_EXTENDED_FILE", sandbox / "operators_extended.json")
    monkeypatch.setattr(incident_store, "INCIDENTS_FILE", sandbox / "incident_feed.json")
    monkeypatch.setattr(runner, "configure_runner_logging", lambda: None)
    monkeypatch.setattr(
        runner,
        "maybe_deliver_scheduled_report",
        lambda settings=None: {"scheduled": False, "email_sent": False, "reason": "report_delivery_disabled", "report_file": None},
    )

    today = datetime.now().date()
    (sandbox / "operators_extended.json").write_text(
        json.dumps(
            [
                {
                    "id": "OPR-1001",
                    "name": "Operator A",
                    "phone": "6381528758",
                    "license_expiry": (today + timedelta(days=15)).isoformat(),
                }
            ],
            indent=2,
        ),
        encoding="utf-8",
    )

    sms = FakeSMSService()
    summary = runner.run_machine_alert_scan(
        machines=[],
        sms_service=sms,
        settings={
            "sms_enabled": True,
            "auto_machine_alerts": False,
            "auto_work_order_generation": False,
            "auto_spare_reorder_alerts": False,
            "auto_maintenance_followup_reminders": False,
            "checklist_missed_alerts_enabled": False,
            "rule_engine_enabled": False,
            "predictive_layer_enabled": False,
            "auto_report_delivery_enabled": False,
            "auto_operator_record_alerts": True,
            "auto_operator_record_sms": True,
            "operator_alert_renewal_days": 30,
            "operator_alert_rejection_days": 5,
            "admin_daily_summary_sms_enabled": False,
        },
    )

    assert summary["operator_alerts_created"] == 0
    assert summary["operator_sms_sent"] == 0
    assert summary["sms_sent"] == 0
    assert summary["reason"] == "no_machine_details"
