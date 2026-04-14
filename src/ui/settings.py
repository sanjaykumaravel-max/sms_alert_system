
import csv
import threading
import zipfile
from datetime import datetime
from typing import Any, Dict, List

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, ttk

try:
    from ..app_paths import data_path, exports_dir, logs_dir
    from ..machine_alert_runner import run_machine_alert_scan
    from ..settings_store import load_settings, save_settings
    from ..windows_task_runner import install_machine_alert_task, query_machine_alert_task, remove_machine_alert_task
except Exception:
    from app_paths import data_path, exports_dir, logs_dir
    from machine_alert_runner import run_machine_alert_scan
    from settings_store import load_settings, save_settings
    from windows_task_runner import install_machine_alert_task, query_machine_alert_task, remove_machine_alert_task

from authz import has_role
from sms_service import default_sms_service

from .theme import SIMPLE_PALETTE
from . import theme as theme_mod
from .gradient import GradientPanel
from .validation import normalize_phone_input, validate_phone

PALETTE = SIMPLE_PALETTE
TASK_DETAIL_KEYS = ("installed", "state", "last_run_time", "last_result", "next_run_time")


def _extract_machine_hint(message: str) -> str:
    raw = str(message or "").strip()
    if not raw:
        return "-"
    prefixes = (
        "CRITICAL ALERT:",
        "OVERDUE ALERT:",
        "DUE ALERT:",
        "MAINTENANCE ALERT:",
    )
    for prefix in prefixes:
        if raw.startswith(prefix):
            remainder = raw[len(prefix):].strip()
            return remainder.split(" ", 1)[0].split("(", 1)[0].strip() or "-"
    return "-"


def _load_recent_audit_rows(limit: int = 120) -> List[Dict[str, Any]]:
    try:
        try:
            from ..db import SMSAudit, get_session
        except Exception:
            from db import SMSAudit, get_session
        sess = get_session()
        try:
            rows = (
                sess.query(SMSAudit)
                .order_by(SMSAudit.created_at.desc())
                .limit(limit)
                .all()
            )
            result = []
            for row in rows:
                message = str(row.message or "").replace("\n", " ").strip()
                result.append(
                    {
                        "created_at": row.created_at.isoformat(sep=" ", timespec="seconds") if row.created_at else "",
                        "to": row.to_number or "",
                        "machine": _extract_machine_hint(message),
                        "provider": row.provider or "",
                        "result": "Sent" if row.success else "Failed",
                        "message": message or "-",
                        "error": row.error or "",
                    }
                )
            return result
        finally:
            sess.close()
    except Exception:
        return []


class SettingsWindow:
    def __init__(self, parent, dashboard=None):
        self.top = ctk.CTkToplevel(parent)
        self.top.title("Settings")
        self.top.geometry("980x840")

        frame = SettingsFrame(self.top, on_saved=self.top.destroy, dashboard=dashboard)
        frame.pack(fill="both", expand=True)


class SettingsFrame(ctk.CTkFrame):
    def __init__(self, parent, on_saved=None, dashboard=None):
        super().__init__(parent, fg_color="transparent")
        self._on_saved = on_saved
        self.dashboard = dashboard
        self.user = getattr(dashboard, "user", None) if dashboard is not None else None
        self._is_admin = bool(has_role(self.user, "admin")) if self.user is not None else True
        self._admin_widgets: List[Any] = []
        self._task_value_labels: Dict[str, ctk.CTkLabel] = {}
        self._audit_rows: List[Dict[str, Any]] = []

        self.settings = load_settings()

        outer = ctk.CTkFrame(self, fg_color=PALETTE.get("card", "#111827"), corner_radius=16)
        outer.pack(fill="both", expand=True, padx=12, pady=12)

        self.scroll = ctk.CTkScrollableFrame(outer, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True, padx=6, pady=6)

        self._build_header()
        self._build_system_settings()
        self._build_task_status()
        self._build_backup_and_audit()
        self._build_test_sms()
        self._build_footer()
        self._apply_admin_permissions()

        self.after(150, self._refresh_task_status)
        self.after(250, self._refresh_audit_history)

    def _card(self) -> ctk.CTkFrame:
        return ctk.CTkFrame(self.scroll, fg_color="#0b1220", corner_radius=14)

    def _register_admin_widget(self, widget: Any) -> Any:
        self._admin_widgets.append(widget)
        return widget

    def _build_header(self) -> None:
        header = GradientPanel(
            self.scroll,
            colors=getattr(theme_mod, "SECTION_GRADIENTS", {}).get("settings", ("#111827", "#475569", "#94a3b8")),
            corner_radius=14,
            border_color="#1d2a3f",
        )
        header.pack(fill="x", padx=10, pady=(10, 8))

        ctk.CTkLabel(
            header.content,
            text="Settings",
            font=("Segoe UI Semibold", 24),
            text_color="#f8fafc",
        ).pack(anchor="w", padx=14, pady=(14, 2))

        access_text = "Administrator mode" if self._is_admin else "View-only mode"
        access_color = "#22c55e" if self._is_admin else "#f59e0b"
        ctk.CTkLabel(
            header.content,
            text=access_text,
            font=("Segoe UI Semibold", 12),
            text_color="#ffffff",
            fg_color=access_color,
            corner_radius=8,
            padx=8,
            pady=4,
        ).pack(anchor="w", padx=14, pady=(0, 8))

        subtitle = (
            "Control machine alert automation, SMS runtime behavior, backups, and audit history."
            if self._is_admin
            else "You can review status here, but only administrators can change system settings and user management."
        )
        ctk.CTkLabel(
            header.content,
            text=subtitle,
            font=("Segoe UI", 13),
            text_color="#dbeafe",
            wraplength=860,
            justify="left",
        ).pack(anchor="w", padx=14, pady=(0, 14))
    def _build_system_settings(self) -> None:
        frame = self._card()
        frame.pack(fill="x", padx=10, pady=8)

        ctk.CTkLabel(frame, text="System Controls", font=("Segoe UI Semibold", 16), text_color="#f8fafc").pack(anchor="w", padx=12, pady=(12, 4))
        ctk.CTkLabel(
            frame,
            text="These settings control global SMS and maintenance automation behavior for the whole app.",
            font=("Segoe UI", 12),
            text_color="#94a3b8",
            wraplength=860,
            justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 10))

        self.sms_var = tk.BooleanVar(value=self.settings.get("sms_enabled", False))
        sms_chk = ctk.CTkCheckBox(frame, text="Enable SMS sending (runtime)", variable=self.sms_var, text_color="#e2e8f0", font=("Segoe UI", 13))
        sms_chk.pack(anchor="w", padx=12, pady=(0, 8))
        self._register_admin_widget(sms_chk)

        self.auto_api_var = tk.BooleanVar(value=self.settings.get("auto_start_api_server", True))
        api_chk = ctk.CTkCheckBox(frame, text="Auto-start local API server on app launch", variable=self.auto_api_var, text_color="#e2e8f0", font=("Segoe UI", 13))
        api_chk.pack(anchor="w", padx=12, pady=(0, 8))
        self._register_admin_widget(api_chk)

        self.auto_machine_alerts_var = tk.BooleanVar(value=self.settings.get("auto_machine_alerts", True))
        auto_chk = ctk.CTkCheckBox(frame, text="Enable automatic machine alert SMS checks", variable=self.auto_machine_alerts_var, text_color="#e2e8f0", font=("Segoe UI", 13))
        auto_chk.pack(anchor="w", padx=12, pady=(0, 8))
        self._register_admin_widget(auto_chk)

        timing_row = ctk.CTkFrame(frame, fg_color="transparent")
        timing_row.pack(fill="x", padx=12, pady=(0, 8))
        ctk.CTkLabel(timing_row, text="Auto alert interval (min):", font=("Segoe UI", 13), text_color="#cbd5e1").grid(row=0, column=0, sticky="w")
        self.machine_alert_interval_var = tk.StringVar(value=str(self.settings.get("machine_alert_interval_minutes", 5)))
        interval_entry = ctk.CTkEntry(timing_row, textvariable=self.machine_alert_interval_var, width=90, height=34, font=("Segoe UI", 13))
        interval_entry.grid(row=0, column=1, padx=(8, 16))
        self._register_admin_widget(interval_entry)

        ctk.CTkLabel(timing_row, text="Cooldown (min):", font=("Segoe UI", 13), text_color="#cbd5e1").grid(row=0, column=2, sticky="w")
        self.machine_alert_cooldown_var = tk.StringVar(value=str(self.settings.get("machine_alert_cooldown_minutes", 360)))
        cooldown_entry = ctk.CTkEntry(timing_row, textvariable=self.machine_alert_cooldown_var, width=90, height=34, font=("Segoe UI", 13))
        cooldown_entry.grid(row=0, column=3, padx=(8, 0))
        self._register_admin_widget(cooldown_entry)

        stage_row = ctk.CTkFrame(frame, fg_color="transparent")
        stage_row.pack(fill="x", padx=12, pady=(0, 8))
        ctk.CTkLabel(stage_row, text="Reminder before due (days):", font=("Segoe UI", 13), text_color="#cbd5e1").grid(row=0, column=0, sticky="w")
        self.machine_reminder_days_var = tk.StringVar(value=str(self.settings.get("machine_reminder_days", 2)))
        reminder_entry = ctk.CTkEntry(stage_row, textvariable=self.machine_reminder_days_var, width=90, height=34, font=("Segoe UI", 13))
        reminder_entry.grid(row=0, column=1, padx=(8, 16))
        self._register_admin_widget(reminder_entry)

        ctk.CTkLabel(stage_row, text="Overdue after (days):", font=("Segoe UI", 13), text_color="#cbd5e1").grid(row=0, column=2, sticky="w")
        self.machine_overdue_after_days_var = tk.StringVar(value=str(self.settings.get("machine_overdue_after_days", 2)))
        overdue_entry = ctk.CTkEntry(stage_row, textvariable=self.machine_overdue_after_days_var, width=90, height=34, font=("Segoe UI", 13))
        overdue_entry.grid(row=0, column=3, padx=(8, 0))
        self._register_admin_widget(overdue_entry)

        self.auto_work_order_generation_var = tk.BooleanVar(value=self.settings.get("auto_work_order_generation", True))
        work_order_chk = ctk.CTkCheckBox(
            frame,
            text="Auto-generate work orders when machine is due/overdue",
            variable=self.auto_work_order_generation_var,
            text_color="#e2e8f0",
            font=("Segoe UI", 13),
        )
        work_order_chk.pack(anchor="w", padx=12, pady=(0, 6))
        self._register_admin_widget(work_order_chk)

        self.auto_escalation_sms_var = tk.BooleanVar(value=self.settings.get("auto_escalation_sms", True))
        escalation_chk = ctk.CTkCheckBox(
            frame,
            text="Enable escalation SMS (Due-2 operator, Due-1 supervisor, Due day manager)",
            variable=self.auto_escalation_sms_var,
            text_color="#e2e8f0",
            font=("Segoe UI", 13),
        )
        escalation_chk.pack(anchor="w", padx=12, pady=(0, 10))
        self._register_admin_widget(escalation_chk)

        self.status_change_alerts_only_var = tk.BooleanVar(value=self.settings.get("status_change_alerts_only", True))
        status_change_chk = ctk.CTkCheckBox(
            frame,
            text="Send machine alert SMS only when status changes (no duplicate same-state reminders)",
            variable=self.status_change_alerts_only_var,
            text_color="#e2e8f0",
            font=("Segoe UI", 13),
        )
        status_change_chk.pack(anchor="w", padx=12, pady=(0, 6))
        self._register_admin_widget(status_change_chk)

        self.persist_sms_rate_limit_state_var = tk.BooleanVar(value=self.settings.get("persist_sms_rate_limit_state", True))
        persist_limit_chk = ctk.CTkCheckBox(
            frame,
            text="Persist SMS rate-limit counters across app restarts",
            variable=self.persist_sms_rate_limit_state_var,
            text_color="#e2e8f0",
            font=("Segoe UI", 13),
        )
        persist_limit_chk.pack(anchor="w", padx=12, pady=(0, 10))
        self._register_admin_widget(persist_limit_chk)

        rate_limit_row = ctk.CTkFrame(frame, fg_color="transparent")
        rate_limit_row.pack(fill="x", padx=12, pady=(0, 8))
        ctk.CTkLabel(rate_limit_row, text="Max SMS / recipient / hour:", font=("Segoe UI", 13), text_color="#cbd5e1").grid(row=0, column=0, sticky="w")
        self.sms_max_per_recipient_per_hour_var = tk.StringVar(value=str(self.settings.get("sms_max_per_recipient_per_hour", 10)))
        rate_hour_entry = ctk.CTkEntry(rate_limit_row, textvariable=self.sms_max_per_recipient_per_hour_var, width=90, height=34, font=("Segoe UI", 13))
        rate_hour_entry.grid(row=0, column=1, padx=(8, 16))
        self._register_admin_widget(rate_hour_entry)

        ctk.CTkLabel(rate_limit_row, text="Max SMS / recipient / day:", font=("Segoe UI", 13), text_color="#cbd5e1").grid(row=0, column=2, sticky="w")
        self.sms_max_per_recipient_per_day_var = tk.StringVar(value=str(self.settings.get("sms_max_per_recipient_per_day", 50)))
        rate_day_entry = ctk.CTkEntry(rate_limit_row, textvariable=self.sms_max_per_recipient_per_day_var, width=90, height=34, font=("Segoe UI", 13))
        rate_day_entry.grid(row=0, column=3, padx=(8, 0))
        self._register_admin_widget(rate_day_entry)

        self.completion_sms_enabled_var = tk.BooleanVar(value=self.settings.get("completion_sms_enabled", True))
        completion_chk = ctk.CTkCheckBox(
            frame,
            text="Send SMS when maintenance is marked completed",
            variable=self.completion_sms_enabled_var,
            text_color="#e2e8f0",
            font=("Segoe UI", 13),
        )
        completion_chk.pack(anchor="w", padx=12, pady=(0, 6))
        self._register_admin_widget(completion_chk)

        completion_targets_row = ctk.CTkFrame(frame, fg_color="transparent")
        completion_targets_row.pack(fill="x", padx=12, pady=(0, 8))
        self.completion_sms_include_supervisor_var = tk.BooleanVar(value=self.settings.get("completion_sms_include_supervisor", False))
        completion_supervisor_chk = ctk.CTkCheckBox(
            completion_targets_row,
            text="Also send completion SMS to supervisor",
            variable=self.completion_sms_include_supervisor_var,
            text_color="#e2e8f0",
            font=("Segoe UI", 13),
        )
        completion_supervisor_chk.grid(row=0, column=0, sticky="w")
        self._register_admin_widget(completion_supervisor_chk)

        self.completion_sms_include_admin_var = tk.BooleanVar(value=self.settings.get("completion_sms_include_admin", False))
        completion_admin_chk = ctk.CTkCheckBox(
            completion_targets_row,
            text="Also send completion SMS to admin",
            variable=self.completion_sms_include_admin_var,
            text_color="#e2e8f0",
            font=("Segoe UI", 13),
        )
        completion_admin_chk.grid(row=0, column=1, sticky="w", padx=(18, 0))
        self._register_admin_widget(completion_admin_chk)

        daily_summary_row = ctk.CTkFrame(frame, fg_color="transparent")
        daily_summary_row.pack(fill="x", padx=12, pady=(0, 10))
        self.admin_daily_summary_sms_enabled_var = tk.BooleanVar(value=self.settings.get("admin_daily_summary_sms_enabled", True))
        daily_summary_chk = ctk.CTkCheckBox(
            daily_summary_row,
            text="Enable daily SMS summary to admin",
            variable=self.admin_daily_summary_sms_enabled_var,
            text_color="#e2e8f0",
            font=("Segoe UI", 13),
        )
        daily_summary_chk.grid(row=0, column=0, sticky="w")
        self._register_admin_widget(daily_summary_chk)

        ctk.CTkLabel(daily_summary_row, text="Send hour (0-23):", font=("Segoe UI", 13), text_color="#cbd5e1").grid(row=0, column=1, sticky="w", padx=(16, 8))
        self.admin_daily_summary_hour_var = tk.StringVar(value=str(self.settings.get("admin_daily_summary_hour", 20)))
        daily_summary_hour_entry = ctk.CTkEntry(daily_summary_row, textvariable=self.admin_daily_summary_hour_var, width=70, height=34, font=("Segoe UI", 13))
        daily_summary_hour_entry.grid(row=0, column=2, sticky="w")
        self._register_admin_widget(daily_summary_hour_entry)

        self.auto_spare_reorder_alerts_var = tk.BooleanVar(value=self.settings.get("auto_spare_reorder_alerts", True))
        spare_reorder_chk = ctk.CTkCheckBox(
            frame,
            text="Enable auto spare reorder alerts (min stock + planned maintenance)",
            variable=self.auto_spare_reorder_alerts_var,
            text_color="#e2e8f0",
            font=("Segoe UI", 13),
        )
        spare_reorder_chk.pack(anchor="w", padx=12, pady=(0, 6))
        self._register_admin_widget(spare_reorder_chk)

        self.auto_maintenance_followup_reminders_var = tk.BooleanVar(value=self.settings.get("auto_maintenance_followup_reminders", True))
        followup_chk = ctk.CTkCheckBox(
            frame,
            text="Enable maintenance not-closed follow-up reminders",
            variable=self.auto_maintenance_followup_reminders_var,
            text_color="#e2e8f0",
            font=("Segoe UI", 13),
        )
        followup_chk.pack(anchor="w", padx=12, pady=(0, 6))
        self._register_admin_widget(followup_chk)

        self.checklist_missed_alerts_enabled_var = tk.BooleanVar(value=self.settings.get("checklist_missed_alerts_enabled", True))
        checklist_missed_chk = ctk.CTkCheckBox(
            frame,
            text="Enable missed checklist auto alerts",
            variable=self.checklist_missed_alerts_enabled_var,
            text_color="#e2e8f0",
            font=("Segoe UI", 13),
        )
        checklist_missed_chk.pack(anchor="w", padx=12, pady=(0, 10))
        self._register_admin_widget(checklist_missed_chk)

        reminder_rule_row = ctk.CTkFrame(frame, fg_color="transparent")
        reminder_rule_row.pack(fill="x", padx=12, pady=(0, 8))
        ctk.CTkLabel(reminder_rule_row, text="Follow-up after (days):", font=("Segoe UI", 13), text_color="#cbd5e1").grid(row=0, column=0, sticky="w")
        self.maintenance_followup_days_var = tk.StringVar(value=str(self.settings.get("maintenance_followup_days", 1)))
        followup_days_entry = ctk.CTkEntry(reminder_rule_row, textvariable=self.maintenance_followup_days_var, width=90, height=34, font=("Segoe UI", 13))
        followup_days_entry.grid(row=0, column=1, padx=(8, 16))
        self._register_admin_widget(followup_days_entry)

        ctk.CTkLabel(reminder_rule_row, text="Checklist cutoff (hour):", font=("Segoe UI", 13), text_color="#cbd5e1").grid(row=0, column=2, sticky="w")
        self.checklist_missed_cutoff_hour_var = tk.StringVar(value=str(self.settings.get("checklist_missed_cutoff_hour", 18)))
        checklist_cutoff_entry = ctk.CTkEntry(reminder_rule_row, textvariable=self.checklist_missed_cutoff_hour_var, width=90, height=34, font=("Segoe UI", 13))
        checklist_cutoff_entry.grid(row=0, column=3, padx=(8, 0))
        self._register_admin_widget(checklist_cutoff_entry)

        self.rule_engine_enabled_var = tk.BooleanVar(value=self.settings.get("rule_engine_enabled", False))
        rule_engine_chk = ctk.CTkCheckBox(
            frame,
            text="Enable rule engine (custom if/then rules on machine + risk context)",
            variable=self.rule_engine_enabled_var,
            text_color="#e2e8f0",
            font=("Segoe UI", 13),
        )
        rule_engine_chk.pack(anchor="w", padx=12, pady=(0, 6))
        self._register_admin_widget(rule_engine_chk)

        self.predictive_layer_enabled_var = tk.BooleanVar(value=self.settings.get("predictive_layer_enabled", False))
        predictive_chk = ctk.CTkCheckBox(
            frame,
            text="Enable predictive layer (risk score and proactive incident alerts)",
            variable=self.predictive_layer_enabled_var,
            text_color="#e2e8f0",
            font=("Segoe UI", 13),
        )
        predictive_chk.pack(anchor="w", padx=12, pady=(0, 6))
        self._register_admin_widget(predictive_chk)

        self.rule_engine_sms_enabled_var = tk.BooleanVar(value=self.settings.get("rule_engine_sms_enabled", False))
        rule_sms_chk = ctk.CTkCheckBox(
            frame,
            text="Send SMS for rule engine matches",
            variable=self.rule_engine_sms_enabled_var,
            text_color="#e2e8f0",
            font=("Segoe UI", 13),
        )
        rule_sms_chk.pack(anchor="w", padx=12, pady=(0, 4))
        self._register_admin_widget(rule_sms_chk)

        self.predictive_sms_enabled_var = tk.BooleanVar(value=self.settings.get("predictive_sms_enabled", False))
        predictive_sms_chk = ctk.CTkCheckBox(
            frame,
            text="Send SMS for predictive risk threshold crossings",
            variable=self.predictive_sms_enabled_var,
            text_color="#e2e8f0",
            font=("Segoe UI", 13),
        )
        predictive_sms_chk.pack(anchor="w", padx=12, pady=(0, 10))
        self._register_admin_widget(predictive_sms_chk)

        predictive_row = ctk.CTkFrame(frame, fg_color="transparent")
        predictive_row.pack(fill="x", padx=12, pady=(0, 8))
        ctk.CTkLabel(predictive_row, text="Predictive threshold (40-95):", font=("Segoe UI", 13), text_color="#cbd5e1").grid(row=0, column=0, sticky="w")
        self.predictive_alert_threshold_var = tk.StringVar(value=str(self.settings.get("predictive_alert_threshold", 65)))
        predictive_threshold_entry = ctk.CTkEntry(predictive_row, textvariable=self.predictive_alert_threshold_var, width=90, height=34, font=("Segoe UI", 13))
        predictive_threshold_entry.grid(row=0, column=1, padx=(8, 16))
        self._register_admin_widget(predictive_threshold_entry)

        ctk.CTkLabel(predictive_row, text="Rule dedup (min):", font=("Segoe UI", 13), text_color="#cbd5e1").grid(row=0, column=2, sticky="w")
        self.rule_engine_dedup_minutes_var = tk.StringVar(value=str(self.settings.get("rule_engine_dedup_minutes", 360)))
        rule_dedup_entry = ctk.CTkEntry(predictive_row, textvariable=self.rule_engine_dedup_minutes_var, width=90, height=34, font=("Segoe UI", 13))
        rule_dedup_entry.grid(row=0, column=3, padx=(8, 16))
        self._register_admin_widget(rule_dedup_entry)

        ctk.CTkLabel(predictive_row, text="Predictive dedup (min):", font=("Segoe UI", 13), text_color="#cbd5e1").grid(row=0, column=4, sticky="w")
        self.predictive_dedup_minutes_var = tk.StringVar(value=str(self.settings.get("predictive_dedup_minutes", 360)))
        predictive_dedup_entry = ctk.CTkEntry(predictive_row, textvariable=self.predictive_dedup_minutes_var, width=90, height=34, font=("Segoe UI", 13))
        predictive_dedup_entry.grid(row=0, column=5, padx=(8, 0))
        self._register_admin_widget(predictive_dedup_entry)

        escalation_row = ctk.CTkFrame(frame, fg_color="transparent")
        escalation_row.pack(fill="x", padx=12, pady=(0, 8))
        escalation_row.grid_columnconfigure(1, weight=1)
        escalation_row.grid_columnconfigure(3, weight=1)
        ctk.CTkLabel(escalation_row, text="Supervisor phones:", font=("Segoe UI", 13), text_color="#cbd5e1").grid(row=0, column=0, sticky="w")
        self.escalation_supervisor_phones_var = tk.StringVar(value=str(self.settings.get("escalation_supervisor_phones", "")))
        supervisor_entry = ctk.CTkEntry(escalation_row, textvariable=self.escalation_supervisor_phones_var, height=34, font=("Segoe UI", 13), placeholder_text="+91xxxxxxxxxx,+91yyyyyyyyyy")
        supervisor_entry.grid(row=0, column=1, padx=(8, 14), sticky="ew")
        self._register_admin_widget(supervisor_entry)

        ctk.CTkLabel(escalation_row, text="Manager phones:", font=("Segoe UI", 13), text_color="#cbd5e1").grid(row=0, column=2, sticky="w")
        self.escalation_admin_phones_var = tk.StringVar(value=str(self.settings.get("escalation_admin_phones", "")))
        admin_entry = ctk.CTkEntry(escalation_row, textvariable=self.escalation_admin_phones_var, height=34, font=("Segoe UI", 13), placeholder_text="+91xxxxxxxxxx")
        admin_entry.grid(row=0, column=3, padx=(8, 0), sticky="ew")
        self._register_admin_widget(admin_entry)

        ctk.CTkLabel(frame, text="Automatic Report Delivery", font=("Segoe UI Semibold", 15), text_color="#f8fafc").pack(anchor="w", padx=12, pady=(6, 4))
        self.auto_report_delivery_enabled_var = tk.BooleanVar(value=self.settings.get("auto_report_delivery_enabled", False))
        report_chk = ctk.CTkCheckBox(
            frame,
            text="Enable scheduled report delivery (daily/weekly, PDF/email)",
            variable=self.auto_report_delivery_enabled_var,
            text_color="#e2e8f0",
            font=("Segoe UI", 13),
        )
        report_chk.pack(anchor="w", padx=12, pady=(0, 8))
        self._register_admin_widget(report_chk)

        report_row = ctk.CTkFrame(frame, fg_color="transparent")
        report_row.pack(fill="x", padx=12, pady=(0, 8))
        ctk.CTkLabel(report_row, text="Frequency:", font=("Segoe UI", 13), text_color="#cbd5e1").grid(row=0, column=0, sticky="w")
        self.report_delivery_frequency_var = tk.StringVar(value=str(self.settings.get("report_delivery_frequency", "daily")))
        report_freq_menu = ctk.CTkOptionMenu(report_row, values=["daily", "weekly"], variable=self.report_delivery_frequency_var, width=110)
        report_freq_menu.grid(row=0, column=1, padx=(8, 16), sticky="w")
        self._register_admin_widget(report_freq_menu)

        ctk.CTkLabel(report_row, text="Hour (0-23):", font=("Segoe UI", 13), text_color="#cbd5e1").grid(row=0, column=2, sticky="w")
        self.report_delivery_hour_var = tk.StringVar(value=str(self.settings.get("report_delivery_hour", 18)))
        report_hour_entry = ctk.CTkEntry(report_row, textvariable=self.report_delivery_hour_var, width=70, height=34, font=("Segoe UI", 13))
        report_hour_entry.grid(row=0, column=3, padx=(8, 16), sticky="w")
        self._register_admin_widget(report_hour_entry)

        ctk.CTkLabel(report_row, text="Weekday (0-6):", font=("Segoe UI", 13), text_color="#cbd5e1").grid(row=0, column=4, sticky="w")
        self.report_delivery_weekday_var = tk.StringVar(value=str(self.settings.get("report_delivery_weekday", 0)))
        report_weekday_entry = ctk.CTkEntry(report_row, textvariable=self.report_delivery_weekday_var, width=70, height=34, font=("Segoe UI", 13))
        report_weekday_entry.grid(row=0, column=5, padx=(8, 16), sticky="w")
        self._register_admin_widget(report_weekday_entry)

        ctk.CTkLabel(report_row, text="Format:", font=("Segoe UI", 13), text_color="#cbd5e1").grid(row=0, column=6, sticky="w")
        self.report_delivery_format_var = tk.StringVar(value=str(self.settings.get("report_delivery_format", "pdf")))
        report_format_menu = ctk.CTkOptionMenu(report_row, values=["pdf", "html", "csv", "xlsx", "docx"], variable=self.report_delivery_format_var, width=90)
        report_format_menu.grid(row=0, column=7, padx=(8, 0), sticky="w")
        self._register_admin_widget(report_format_menu)

        self.report_delivery_emails_var = tk.StringVar(value=str(self.settings.get("report_delivery_emails", "")))
        report_email_entry = ctk.CTkEntry(
            frame,
            textvariable=self.report_delivery_emails_var,
            height=34,
            font=("Segoe UI", 13),
            placeholder_text="Report recipient emails (comma separated)",
        )
        report_email_entry.pack(fill="x", padx=12, pady=(0, 8))
        self._register_admin_widget(report_email_entry)

        self.report_delivery_email_subject_var = tk.StringVar(value=str(self.settings.get("report_delivery_email_subject", "Mining Maintenance Report")))
        report_subject_entry = ctk.CTkEntry(
            frame,
            textvariable=self.report_delivery_email_subject_var,
            height=34,
            font=("Segoe UI", 13),
            placeholder_text="Report email subject",
        )
        report_subject_entry.pack(fill="x", padx=12, pady=(0, 8))
        self._register_admin_widget(report_subject_entry)

        smtp_row1 = ctk.CTkFrame(frame, fg_color="transparent")
        smtp_row1.pack(fill="x", padx=12, pady=(0, 8))
        smtp_row1.grid_columnconfigure(1, weight=1)
        smtp_row1.grid_columnconfigure(3, weight=1)
        ctk.CTkLabel(smtp_row1, text="SMTP host:", font=("Segoe UI", 13), text_color="#cbd5e1").grid(row=0, column=0, sticky="w")
        self.smtp_host_var = tk.StringVar(value=str(self.settings.get("smtp_host", "")))
        smtp_host_entry = ctk.CTkEntry(smtp_row1, textvariable=self.smtp_host_var, height=34, font=("Segoe UI", 13), placeholder_text="smtp.gmail.com")
        smtp_host_entry.grid(row=0, column=1, padx=(8, 14), sticky="ew")
        self._register_admin_widget(smtp_host_entry)
        ctk.CTkLabel(smtp_row1, text="Port:", font=("Segoe UI", 13), text_color="#cbd5e1").grid(row=0, column=2, sticky="w")
        self.smtp_port_var = tk.StringVar(value=str(self.settings.get("smtp_port", 587)))
        smtp_port_entry = ctk.CTkEntry(smtp_row1, textvariable=self.smtp_port_var, width=90, height=34, font=("Segoe UI", 13))
        smtp_port_entry.grid(row=0, column=3, padx=(8, 0), sticky="w")
        self._register_admin_widget(smtp_port_entry)

        smtp_row2 = ctk.CTkFrame(frame, fg_color="transparent")
        smtp_row2.pack(fill="x", padx=12, pady=(0, 8))
        smtp_row2.grid_columnconfigure(1, weight=1)
        smtp_row2.grid_columnconfigure(3, weight=1)
        ctk.CTkLabel(smtp_row2, text="SMTP username:", font=("Segoe UI", 13), text_color="#cbd5e1").grid(row=0, column=0, sticky="w")
        self.smtp_username_var = tk.StringVar(value=str(self.settings.get("smtp_username", "")))
        smtp_user_entry = ctk.CTkEntry(smtp_row2, textvariable=self.smtp_username_var, height=34, font=("Segoe UI", 13), placeholder_text="username")
        smtp_user_entry.grid(row=0, column=1, padx=(8, 14), sticky="ew")
        self._register_admin_widget(smtp_user_entry)
        ctk.CTkLabel(smtp_row2, text="SMTP password:", font=("Segoe UI", 13), text_color="#cbd5e1").grid(row=0, column=2, sticky="w")
        self.smtp_password_var = tk.StringVar(value=str(self.settings.get("smtp_password", "")))
        smtp_password_entry = ctk.CTkEntry(smtp_row2, textvariable=self.smtp_password_var, show="*", height=34, font=("Segoe UI", 13))
        smtp_password_entry.grid(row=0, column=3, padx=(8, 0), sticky="ew")
        self._register_admin_widget(smtp_password_entry)

        smtp_row3 = ctk.CTkFrame(frame, fg_color="transparent")
        smtp_row3.pack(fill="x", padx=12, pady=(0, 10))
        smtp_row3.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(smtp_row3, text="Sender email:", font=("Segoe UI", 13), text_color="#cbd5e1").grid(row=0, column=0, sticky="w")
        self.smtp_sender_email_var = tk.StringVar(value=str(self.settings.get("smtp_sender_email", "")))
        smtp_sender_entry = ctk.CTkEntry(smtp_row3, textvariable=self.smtp_sender_email_var, height=34, font=("Segoe UI", 13), placeholder_text="alerts@company.com")
        smtp_sender_entry.grid(row=0, column=1, padx=(8, 14), sticky="ew")
        self._register_admin_widget(smtp_sender_entry)
        self.smtp_use_tls_var = tk.BooleanVar(value=bool(self.settings.get("smtp_use_tls", True)))
        smtp_tls_chk = ctk.CTkCheckBox(smtp_row3, text="Use TLS", variable=self.smtp_use_tls_var, text_color="#e2e8f0", font=("Segoe UI", 13))
        smtp_tls_chk.grid(row=0, column=2, sticky="w")
        self._register_admin_widget(smtp_tls_chk)

        ctk.CTkLabel(frame, text="API server engine:", font=("Segoe UI", 13), text_color="#cbd5e1").pack(anchor="w", padx=12)
        self.engine_var = tk.StringVar(value=self.settings.get("api_server_engine", "auto"))
        engine_menu = ctk.CTkOptionMenu(frame, values=["auto", "uvicorn", "flask"], variable=self.engine_var)
        engine_menu.pack(fill="x", padx=12, pady=(4, 8))
        self._register_admin_widget(engine_menu)

        ctk.CTkLabel(frame, text="Appearance mode:", font=("Segoe UI", 13), text_color="#cbd5e1").pack(anchor="w", padx=12)
        self.ui_mode_var = tk.StringVar(value=self.settings.get("ui_mode", "dark"))
        mode_menu = ctk.CTkOptionMenu(frame, values=["dark", "light", "system"], variable=self.ui_mode_var)
        mode_menu.pack(fill="x", padx=12, pady=(4, 12))
        self._register_admin_widget(mode_menu)

    def _build_task_status(self) -> None:
        frame = self._card()
        frame.pack(fill="x", padx=10, pady=8)

        ctk.CTkLabel(frame, text="Background Machine Alerts", font=("Segoe UI Semibold", 16), text_color="#f8fafc").pack(anchor="w", padx=12, pady=(12, 4))
        ctk.CTkLabel(
            frame,
            text="Keeps date-based machine SMS checks running through Windows Task Scheduler even when the app window is closed.",
            font=("Segoe UI", 12),
            text_color="#94a3b8",
            wraplength=860,
            justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 8))

        self.task_status_label = ctk.CTkLabel(frame, text="Checking background task status...", font=("Segoe UI", 13), text_color="#cbd5e1")
        self.task_status_label.pack(anchor="w", padx=12, pady=(0, 8))

        details = ctk.CTkFrame(frame, fg_color="#111827", corner_radius=10)
        details.pack(fill="x", padx=12, pady=(0, 8))
        for idx, (key, label) in enumerate((("installed", "Installed"), ("state", "State"), ("last_run_time", "Last Run"), ("last_result", "Last Result"), ("next_run_time", "Next Run"))):
            row = idx // 2
            col = (idx % 2) * 2
            ctk.CTkLabel(details, text=f"{label}:", font=("Segoe UI Semibold", 12), text_color="#94a3b8").grid(row=row, column=col, padx=(12, 6), pady=6, sticky="w")
            value_label = ctk.CTkLabel(details, text="-", font=("Segoe UI", 12), text_color="#f8fafc")
            value_label.grid(row=row, column=col + 1, padx=(0, 18), pady=6, sticky="w")
            self._task_value_labels[key] = value_label

        button_row = ctk.CTkFrame(frame, fg_color="transparent")
        button_row.pack(fill="x", padx=12, pady=(0, 12))
        install_btn = ctk.CTkButton(button_row, text="Install Task", height=34, font=("Segoe UI Semibold", 13), command=self._install_task)
        install_btn.pack(side="left", padx=(0, 8))
        remove_btn = ctk.CTkButton(button_row, text="Remove Task", height=34, font=("Segoe UI Semibold", 13), command=self._remove_task)
        remove_btn.pack(side="left", padx=(0, 8))
        run_btn = ctk.CTkButton(button_row, text="Run Check Now", height=34, font=("Segoe UI Semibold", 13), command=self._run_background_check_now)
        run_btn.pack(side="left", padx=(0, 8))
        refresh_btn = ctk.CTkButton(button_row, text="Refresh Status", height=34, font=("Segoe UI Semibold", 13), command=self._refresh_task_status)
        refresh_btn.pack(side="left")
        self._register_admin_widget(install_btn)
        self._register_admin_widget(remove_btn)
        self._register_admin_widget(run_btn)
        self._register_admin_widget(refresh_btn)
    def _build_backup_and_audit(self) -> None:
        frame = self._card()
        frame.pack(fill="both", expand=True, padx=10, pady=8)

        ctk.CTkLabel(frame, text="Backup & Audit", font=("Segoe UI Semibold", 16), text_color="#f8fafc").pack(anchor="w", padx=12, pady=(12, 4))
        ctk.CTkLabel(frame, text="Export your core data and review recent SMS history in one place.", font=("Segoe UI", 12), text_color="#94a3b8").pack(anchor="w", padx=12, pady=(0, 8))

        export_row = ctk.CTkFrame(frame, fg_color="transparent")
        export_row.pack(fill="x", padx=12, pady=(0, 10))
        export_specs = (
            ("Export Machines", lambda: self._export_core_json("machines.json", "machines")),
            ("Export Operators", lambda: self._export_core_json("operators.json", "operators")),
            ("Export Schedules", lambda: self._export_core_json("schedules.json", "schedules")),
            ("Export Alert Logs", self._export_alert_logs),
            ("Create Full Backup", self._create_full_backup),
        )
        for text, command in export_specs:
            btn = ctk.CTkButton(export_row, text=text, height=34, font=("Segoe UI Semibold", 12), command=command)
            btn.pack(side="left", padx=(0, 8))
            self._register_admin_widget(btn)

        self.backup_status = ctk.CTkLabel(frame, text="", font=("Segoe UI", 12), text_color="#94a3b8")
        self.backup_status.pack(anchor="w", padx=12, pady=(0, 8))

        audit_header = ctk.CTkFrame(frame, fg_color="transparent")
        audit_header.pack(fill="x", padx=12, pady=(0, 6))
        ctk.CTkLabel(audit_header, text="Recent SMS Audit History", font=("Segoe UI Semibold", 14), text_color="#f8fafc").pack(side="left")
        ctk.CTkButton(audit_header, text="Refresh", width=90, height=32, command=self._refresh_audit_history).pack(side="right", padx=(8, 0))
        export_audit_btn = ctk.CTkButton(audit_header, text="Export Audit CSV", width=130, height=32, command=self._export_alert_logs)
        export_audit_btn.pack(side="right")
        self._register_admin_widget(export_audit_btn)

        table_wrap = ctk.CTkFrame(frame, fg_color="#111827", corner_radius=10)
        table_wrap.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        columns = ("created_at", "to", "machine", "provider", "result", "message")
        self.audit_tree = ttk.Treeview(table_wrap, columns=columns, show="headings", height=10, style="SettingsAudit.Treeview")
        style = ttk.Style()
        style.configure("SettingsAudit.Treeview", font=("Segoe UI", 11), rowheight=30, background="#0b1220", fieldbackground="#0b1220", foreground="#e2e8f0")
        style.configure("SettingsAudit.Treeview.Heading", font=("Segoe UI Semibold", 11), background="#1f2937", foreground="#e2e8f0")
        style.map("SettingsAudit.Treeview", background=[("selected", PALETTE.get("primary", "#06B6D4"))], foreground=[("selected", "#ffffff")])

        headings = {"created_at": "When", "to": "To", "machine": "Machine", "provider": "Provider", "result": "Result", "message": "Message"}
        widths = {"created_at": 150, "to": 130, "machine": 90, "provider": 90, "result": 70, "message": 420}
        for key in columns:
            self.audit_tree.heading(key, text=headings[key])
            self.audit_tree.column(key, width=widths[key], anchor="w")

        yscroll = ttk.Scrollbar(table_wrap, orient="vertical", command=self.audit_tree.yview)
        self.audit_tree.configure(yscrollcommand=yscroll.set)
        self.audit_tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        yscroll.pack(side="right", fill="y", padx=(0, 8), pady=8)

    def _build_test_sms(self) -> None:
        frame = self._card()
        frame.pack(fill="x", padx=10, pady=8)

        ctk.CTkLabel(frame, text="Test SMS", font=("Segoe UI Semibold", 16), text_color="#f8fafc").pack(anchor="w", padx=12, pady=(12, 4))
        ctk.CTkLabel(frame, text="Use this for a single controlled test message.", font=("Segoe UI", 12), text_color="#94a3b8").pack(anchor="w", padx=12, pady=(0, 8))

        self.test_phone = ctk.CTkEntry(frame, placeholder_text="+91xxxxxxxxxx", font=("Segoe UI", 13), height=36)
        self.test_phone.pack(fill="x", padx=12, pady=(0, 8))
        self.test_message = ctk.CTkEntry(frame, placeholder_text="Test alert message", font=("Segoe UI", 13), height=36)
        self.test_message.pack(fill="x", padx=12, pady=(0, 8))
        self.test_status = ctk.CTkLabel(frame, text="", font=("Segoe UI", 13), text_color="#94a3b8")
        self.test_status.pack(anchor="w", padx=12, pady=(0, 8))
        send_btn = ctk.CTkButton(frame, text="Send Test SMS", height=34, font=("Segoe UI Semibold", 13), command=self._send_test_sms)
        send_btn.pack(anchor="e", padx=12, pady=(0, 12))
        self._register_admin_widget(self.test_phone)
        self._register_admin_widget(self.test_message)
        self._register_admin_widget(send_btn)

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self.scroll, fg_color="transparent")
        footer.pack(fill="x", padx=10, pady=(0, 10))
        self.save_btn = ctk.CTkButton(footer, text="Save Settings", height=36, font=("Segoe UI Semibold", 13), command=self.save)
        self.save_btn.pack(side="right")
        self._register_admin_widget(self.save_btn)

    def _apply_admin_permissions(self) -> None:
        if self._is_admin:
            return
        for widget in self._admin_widgets:
            try:
                widget.configure(state="disabled")
            except Exception:
                try:
                    widget.configure(fg_color="#334155", hover_color="#334155")
                except Exception:
                    pass

    def _set_task_status(self, text: str, color: str = "#cbd5e1") -> None:
        try:
            self.task_status_label.configure(text=text, text_color=color)
        except Exception:
            pass

    def _set_task_details(self, data: Dict[str, Any]) -> None:
        values = {
            "installed": "Yes" if data.get("installed") else "No",
            "state": data.get("state") or "-",
            "last_run_time": data.get("last_run_time") or "-",
            "last_result": data.get("last_result") or "-",
            "next_run_time": data.get("next_run_time") or "-",
        }
        for key in TASK_DETAIL_KEYS:
            try:
                self._task_value_labels[key].configure(text=values[key])
            except Exception:
                pass
    def _refresh_task_status(self) -> None:
        def _worker():
            try:
                result = query_machine_alert_task()
                installed = bool(result.get("installed"))
                if installed:
                    text = "Background runner is installed and ready."
                    color = "#22c55e"
                else:
                    text = "Background runner is not installed yet."
                    color = "#f59e0b"
            except Exception as exc:
                result = {
                    "installed": False,
                    "state": None,
                    "last_run_time": None,
                    "last_result": None,
                    "next_run_time": None,
                }
                text = f"Task status check failed: {exc}"
                color = "#ef4444"

            try:
                self.after(0, lambda: (self._set_task_status(text, color), self._set_task_details(result)))
            except Exception:
                self._set_task_status(text, color)
                self._set_task_details(result)

        threading.Thread(target=_worker, daemon=True).start()

    def _require_admin(self, action: str) -> bool:
        if self._is_admin:
            return True
        messagebox.showerror("Permission denied", f"Only administrators can {action}.")
        return False

    def save(self, close_after: bool = True) -> None:
        if not self._require_admin("change system settings"):
            return
        try:
            interval = max(1, int(float(self.machine_alert_interval_var.get() or 5)))
            cooldown = max(1, int(float(self.machine_alert_cooldown_var.get() or 360)))
            reminder_days = max(1, int(float(self.machine_reminder_days_var.get() or 2)))
            overdue_after_days = max(1, int(float(self.machine_overdue_after_days_var.get() or 2)))
            sms_max_per_recipient_per_hour = max(1, int(float(self.sms_max_per_recipient_per_hour_var.get() or 10)))
            sms_max_per_recipient_per_day = max(sms_max_per_recipient_per_hour, int(float(self.sms_max_per_recipient_per_day_var.get() or 50)))
            followup_days = max(1, int(float(self.maintenance_followup_days_var.get() or 1)))
            checklist_cutoff_hour = int(float(self.checklist_missed_cutoff_hour_var.get() or 18))
            admin_daily_summary_hour = int(float(self.admin_daily_summary_hour_var.get() or 20))
            predictive_alert_threshold = int(float(self.predictive_alert_threshold_var.get() or 65))
            rule_engine_dedup_minutes = max(30, int(float(self.rule_engine_dedup_minutes_var.get() or 360)))
            predictive_dedup_minutes = max(30, int(float(self.predictive_dedup_minutes_var.get() or 360)))
            report_hour = int(float(self.report_delivery_hour_var.get() or 18))
            report_weekday = int(float(self.report_delivery_weekday_var.get() or 0))
            smtp_port = int(float(self.smtp_port_var.get() or 587))
        except Exception:
            messagebox.showerror("Validation", "Intervals, limits, day/hour, and port values must be valid numbers.")
            return

        mode = str(self.ui_mode_var.get()).lower()
        if mode not in ("dark", "light", "system"):
            messagebox.showerror("Validation", "Appearance mode must be dark, light, or system.")
            return

        if report_hour < 0 or report_hour > 23:
            messagebox.showerror("Validation", "Report delivery hour must be between 0 and 23.")
            return
        if checklist_cutoff_hour < 0 or checklist_cutoff_hour > 23:
            messagebox.showerror("Validation", "Checklist cutoff hour must be between 0 and 23.")
            return
        if admin_daily_summary_hour < 0 or admin_daily_summary_hour > 23:
            messagebox.showerror("Validation", "Daily summary SMS hour must be between 0 and 23.")
            return
        if sms_max_per_recipient_per_hour < 1 or sms_max_per_recipient_per_hour > 200:
            messagebox.showerror("Validation", "Max SMS per recipient per hour must be between 1 and 200.")
            return
        if sms_max_per_recipient_per_day < sms_max_per_recipient_per_hour or sms_max_per_recipient_per_day > 2000:
            messagebox.showerror("Validation", "Max SMS per recipient per day must be between hourly limit and 2000.")
            return
        if predictive_alert_threshold < 40 or predictive_alert_threshold > 95:
            messagebox.showerror("Validation", "Predictive threshold must be between 40 and 95.")
            return
        if report_weekday < 0 or report_weekday > 6:
            messagebox.showerror("Validation", "Report delivery weekday must be between 0 and 6.")
            return
        if smtp_port <= 0 or smtp_port > 65535:
            messagebox.showerror("Validation", "SMTP port must be between 1 and 65535.")
            return

        report_frequency = str(self.report_delivery_frequency_var.get() or "daily").strip().lower()
        if report_frequency not in ("daily", "weekly"):
            messagebox.showerror("Validation", "Report frequency must be daily or weekly.")
            return

        report_format = str(self.report_delivery_format_var.get() or "pdf").strip().lower()
        if report_format not in ("pdf", "html", "csv", "xlsx", "docx"):
            messagebox.showerror("Validation", "Report format must be one of: pdf, html, csv, xlsx, docx.")
            return

        self.settings["sms_enabled"] = bool(self.sms_var.get())
        self.settings["auto_start_api_server"] = bool(self.auto_api_var.get())
        self.settings["auto_machine_alerts"] = bool(self.auto_machine_alerts_var.get())
        self.settings["status_change_alerts_only"] = bool(self.status_change_alerts_only_var.get())
        self.settings["persist_sms_rate_limit_state"] = bool(self.persist_sms_rate_limit_state_var.get())
        self.settings["sms_max_per_recipient_per_hour"] = sms_max_per_recipient_per_hour
        self.settings["sms_max_per_recipient_per_day"] = sms_max_per_recipient_per_day
        self.settings["auto_work_order_generation"] = bool(self.auto_work_order_generation_var.get())
        self.settings["auto_escalation_sms"] = bool(self.auto_escalation_sms_var.get())
        self.settings["completion_sms_enabled"] = bool(self.completion_sms_enabled_var.get())
        self.settings["completion_sms_include_supervisor"] = bool(self.completion_sms_include_supervisor_var.get())
        self.settings["completion_sms_include_admin"] = bool(self.completion_sms_include_admin_var.get())
        self.settings["admin_daily_summary_sms_enabled"] = bool(self.admin_daily_summary_sms_enabled_var.get())
        self.settings["admin_daily_summary_hour"] = admin_daily_summary_hour
        self.settings["auto_spare_reorder_alerts"] = bool(self.auto_spare_reorder_alerts_var.get())
        self.settings["auto_maintenance_followup_reminders"] = bool(self.auto_maintenance_followup_reminders_var.get())
        self.settings["maintenance_followup_days"] = followup_days
        self.settings["checklist_missed_alerts_enabled"] = bool(self.checklist_missed_alerts_enabled_var.get())
        self.settings["checklist_missed_cutoff_hour"] = checklist_cutoff_hour
        self.settings["rule_engine_enabled"] = bool(self.rule_engine_enabled_var.get())
        self.settings["rule_engine_sms_enabled"] = bool(self.rule_engine_sms_enabled_var.get())
        self.settings["rule_engine_dedup_minutes"] = rule_engine_dedup_minutes
        self.settings["predictive_layer_enabled"] = bool(self.predictive_layer_enabled_var.get())
        self.settings["predictive_sms_enabled"] = bool(self.predictive_sms_enabled_var.get())
        self.settings["predictive_alert_threshold"] = predictive_alert_threshold
        self.settings["predictive_dedup_minutes"] = predictive_dedup_minutes
        self.settings["api_server_engine"] = str(self.engine_var.get())
        self.settings["machine_alert_interval_minutes"] = interval
        self.settings["machine_alert_cooldown_minutes"] = cooldown
        self.settings["machine_reminder_days"] = reminder_days
        self.settings["machine_overdue_after_days"] = overdue_after_days
        self.settings["escalation_supervisor_phones"] = str(self.escalation_supervisor_phones_var.get() or "").strip()
        self.settings["escalation_admin_phones"] = str(self.escalation_admin_phones_var.get() or "").strip()
        self.settings["auto_report_delivery_enabled"] = bool(self.auto_report_delivery_enabled_var.get())
        self.settings["report_delivery_frequency"] = report_frequency
        self.settings["report_delivery_hour"] = report_hour
        self.settings["report_delivery_weekday"] = report_weekday
        self.settings["report_delivery_format"] = report_format
        self.settings["report_delivery_emails"] = str(self.report_delivery_emails_var.get() or "").strip()
        self.settings["report_delivery_email_subject"] = str(self.report_delivery_email_subject_var.get() or "").strip()
        self.settings["smtp_host"] = str(self.smtp_host_var.get() or "").strip()
        self.settings["smtp_port"] = smtp_port
        self.settings["smtp_username"] = str(self.smtp_username_var.get() or "").strip()
        self.settings["smtp_password"] = str(self.smtp_password_var.get() or "").strip()
        self.settings["smtp_sender_email"] = str(self.smtp_sender_email_var.get() or "").strip()
        self.settings["smtp_use_tls"] = bool(self.smtp_use_tls_var.get())
        self.settings["ui_mode"] = mode
        self.settings = save_settings(self.settings)

        try:
            ctk.set_appearance_mode(self.settings.get("ui_mode", "dark"))
        except Exception:
            pass

        self._set_task_status("Settings saved successfully.", "#22c55e")
        if close_after and callable(self._on_saved):
            try:
                self._on_saved()
            except Exception:
                pass

    def _install_task(self) -> None:
        if not self._require_admin("install the background task"):
            return
        self.save(close_after=False)
        self._set_task_status("Installing background task...", "#cbd5e1")

        def _worker():
            result = install_machine_alert_task(self.settings.get("machine_alert_interval_minutes", 5))
            success = bool(result.get("success"))
            text = result.get("stdout") or result.get("stderr") or "Task installation finished."
            color = "#22c55e" if success else "#ef4444"
            try:
                self.after(0, lambda: (self._set_task_status(text, color), self._refresh_task_status()))
            except Exception:
                self._set_task_status(text, color)

        threading.Thread(target=_worker, daemon=True).start()

    def _remove_task(self) -> None:
        if not self._require_admin("remove the background task"):
            return
        self._set_task_status("Removing background task...", "#cbd5e1")

        def _worker():
            result = remove_machine_alert_task()
            success = bool(result.get("success"))
            text = result.get("stdout") or result.get("stderr") or "Task removal finished."
            color = "#22c55e" if success else "#ef4444"
            try:
                self.after(0, lambda: (self._set_task_status(text, color), self._refresh_task_status()))
            except Exception:
                self._set_task_status(text, color)

        threading.Thread(target=_worker, daemon=True).start()
    def _run_background_check_now(self) -> None:
        if not self._require_admin("run a background check"):
            return
        self._set_task_status("Running one machine alert check...", "#cbd5e1")

        def _worker():
            try:
                summary = run_machine_alert_scan(settings=load_settings())
                if summary.get("skipped"):
                    reason = str(summary.get("reason") or "skipped").replace("_", " ")
                    text = f"Background check skipped: {reason}"
                    color = "#f59e0b"
                else:
                    text = (
                        f"Background check complete: {summary.get('machine_sent', 0)} machine(s), "
                        f"{summary.get('sms_sent', 0)} SMS, {summary.get('failures', 0)} failed, "
                        f"WO+{summary.get('work_orders_created', 0)}, "
                        f"pending={summary.get('pending', 0)}, "
                        f"report={summary.get('report_reason') or 'not_due'}."
                    )
                    color = "#22c55e"
            except Exception as exc:
                text = f"Background check failed: {exc}"
                color = "#ef4444"

            try:
                self.after(0, lambda: (self._set_task_status(text, color), self._refresh_task_status(), self._refresh_audit_history()))
            except Exception:
                self._set_task_status(text, color)

        threading.Thread(target=_worker, daemon=True).start()

    def _export_core_json(self, filename: str, label: str) -> None:
        if not self._require_admin(f"export {label} data"):
            return
        try:
            source = data_path(filename)
            export_path = exports_dir() / f"{label}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            export_path.write_text(source.read_text(encoding="utf-8") if source.exists() else "[]", encoding="utf-8")
            self.backup_status.configure(text=f"Exported {label} backup to {export_path}", text_color="#22c55e")
        except Exception as exc:
            self.backup_status.configure(text=f"Failed to export {label}: {exc}", text_color="#ef4444")

    def _export_alert_logs(self) -> None:
        if not self._require_admin("export alert logs"):
            return
        try:
            rows = _load_recent_audit_rows(limit=5000)
            export_path = exports_dir() / f"sms_audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            with export_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["when", "to", "machine", "provider", "result", "message", "error"])
                for row in rows:
                    writer.writerow([
                        row.get("created_at", ""),
                        row.get("to", ""),
                        row.get("machine", ""),
                        row.get("provider", ""),
                        row.get("result", ""),
                        row.get("message", ""),
                        row.get("error", ""),
                    ])
            self.backup_status.configure(text=f"Exported alert logs to {export_path}", text_color="#22c55e")
        except Exception as exc:
            self.backup_status.configure(text=f"Failed to export alert logs: {exc}", text_color="#ef4444")

    def _create_full_backup(self) -> None:
        if not self._require_admin("create a full backup"):
            return
        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            export_path = exports_dir() / f"system_backup_{ts}.zip"
            audit_rows = _load_recent_audit_rows(limit=5000)
            with zipfile.ZipFile(export_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for file_name in (
                    "machines.json",
                    "operators.json",
                    "schedules.json",
                    "machine_alert_state.json",
                    "incident_feed.json",
                    "rule_engine_rules.json",
                    "settings.json",
                    "app.db",
                ):
                    source = data_path(file_name)
                    if source.exists():
                        archive.write(source, arcname=f"data/{source.name}")
                log_file = logs_dir() / "machine_alert_runner.log"
                if log_file.exists():
                    archive.write(log_file, arcname=f"logs/{log_file.name}")
                rows_for_csv = [["when", "to", "machine", "provider", "result", "message", "error"]]
                for row in audit_rows:
                    rows_for_csv.append([
                        row.get("created_at", ""),
                        row.get("to", ""),
                        row.get("machine", ""),
                        row.get("provider", ""),
                        row.get("result", ""),
                        row.get("message", ""),
                        row.get("error", ""),
                    ])
                csv_text = "\n".join(",".join(f'"{str(value).replace(chr(34), chr(34) * 2)}"' for value in line) for line in rows_for_csv)
                archive.writestr("exports/sms_audit.csv", csv_text)
            self.backup_status.configure(text=f"Created full backup at {export_path}", text_color="#22c55e")
        except Exception as exc:
            self.backup_status.configure(text=f"Failed to create full backup: {exc}", text_color="#ef4444")
    def _populate_audit_tree(self, rows: List[Dict[str, Any]]) -> None:
        for item in self.audit_tree.get_children():
            self.audit_tree.delete(item)
        for row in rows:
            self.audit_tree.insert(
                "",
                "end",
                values=(
                    row.get("created_at", ""),
                    row.get("to", ""),
                    row.get("machine", ""),
                    row.get("provider", ""),
                    row.get("result", ""),
                    row.get("message", ""),
                ),
            )

    def _refresh_audit_history(self) -> None:
        def _worker():
            rows = _load_recent_audit_rows()
            self._audit_rows = rows
            try:
                self.after(0, lambda: self._populate_audit_tree(rows))
            except Exception:
                self._populate_audit_tree(rows)

        threading.Thread(target=_worker, daemon=True).start()

    def _send_test_sms(self) -> None:
        if not self._require_admin("send a test SMS"):
            return
        phone = self.test_phone.get().strip()
        msg = self.test_message.get().strip() or "Test alert from Mining Maintenance System"
        if not validate_phone(phone, "Test phone"):
            return
        phone = normalize_phone_input(phone) or phone

        def _worker():
            try:
                if hasattr(default_sms_service, "send_with_delivery_retry"):
                    res = default_sms_service.send_with_delivery_retry(
                        phone,
                        msg,
                        max_retries=1,
                        delivery_timeout_seconds=120,
                        poll_interval_seconds=12,
                        initial_poll_delay_seconds=18,
                        retry_backoff_seconds=10,
                    )
                else:
                    res = default_sms_service.send(phone, msg)
            except Exception as exc:
                res = {"success": False, "error": str(exc)}

            def _update():
                request_id = res.get("request_id") or res.get("message_id") or ""
                if res.get("delivered"):
                    suffix = f" (req: {request_id})" if request_id else ""
                    self.test_status.configure(text=f"Delivered{suffix}", text_color="#22c55e")
                elif res.get("success"):
                    suffix = f" (req: {request_id})" if request_id else ""
                    self.test_status.configure(text=f"SMS sent to gateway{suffix}; delivery check unavailable.", text_color="#f59e0b")
                else:
                    error_text = res.get("response_text") or res.get("error") or str(res)
                    self.test_status.configure(text=f"Failed: {error_text}", text_color="#ef4444")
                self._refresh_audit_history()

            try:
                self.after(0, _update)
            except Exception:
                _update()

        threading.Thread(target=_worker, daemon=True).start()
