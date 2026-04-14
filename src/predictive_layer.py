from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    from .machine_store import (
        evaluate_machine_status,
        machine_current_hours,
        machine_due_date,
        machine_hour_alert_window,
        machine_hour_overdue_after,
        machine_next_due_hours,
    )
except Exception:
    from machine_store import (
        evaluate_machine_status,
        machine_current_hours,
        machine_due_date,
        machine_hour_alert_window,
        machine_hour_overdue_after,
        machine_next_due_hours,
    )


def _clamp_score(score: float) -> int:
    return max(0, min(100, int(round(score))))


def _risk_level(score: int) -> str:
    if score >= 85:
        return "critical"
    if score >= 65:
        return "high"
    if score >= 40:
        return "watch"
    return "normal"


def predict_machine_risk(
    machine: Dict[str, Any],
    *,
    now: Optional[datetime] = None,
    reminder_days: int = 3,
    overdue_after_days: int = 2,
    status_context: Optional[Dict[str, Any]] = None,
    extras: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    current = now or datetime.now()
    context = status_context or evaluate_machine_status(
        machine,
        reminder_days=max(1, int(reminder_days)),
        overdue_after_days=max(1, int(overdue_after_days)),
    )
    extra = dict(extras or {})
    score = 0.0
    reasons: List[str] = []

    status = str(context.get("status") or "normal").strip().lower()
    trigger = str(context.get("trigger") or "manual").strip().lower()

    if status == "critical":
        score += 55
        reasons.append("Manual critical status")
    elif status == "overdue":
        score += 45
        reasons.append("Maintenance overdue")
    elif status == "due":
        score += 30
        reasons.append("Maintenance due now")
    elif status == "maintenance":
        score += 18
        reasons.append("Maintenance due soon")

    due_dt = machine_due_date(machine)
    days_to_due: Optional[int] = None
    if due_dt is not None:
        days_to_due = (due_dt - current.date()).days
        if days_to_due < 0:
            overdue_days = abs(days_to_due)
            score += min(35, 10 + (overdue_days * 5))
            reasons.append(f"Date overdue by {overdue_days} day(s)")
        elif days_to_due == 0:
            score += 18
            reasons.append("Date due today")
        elif days_to_due <= max(1, int(reminder_days)):
            score += 8 + (max(1, int(reminder_days)) - days_to_due) * 3
            reasons.append(f"Date due in {days_to_due} day(s)")

    current_hours = machine_current_hours(machine)
    next_due_hours = machine_next_due_hours(machine)
    hours_to_due: Optional[float] = None
    if current_hours is not None and next_due_hours is not None:
        hours_to_due = round(float(next_due_hours) - float(current_hours), 2)
        alert_window = float(machine_hour_alert_window(machine))
        overdue_after_hours = float(machine_hour_overdue_after(machine))
        if hours_to_due < 0:
            overdue_by_hours = abs(hours_to_due)
            score += min(30, 10 + overdue_by_hours * 1.5)
            reasons.append(f"Runtime overdue by {overdue_by_hours:.1f} h")
        elif hours_to_due == 0:
            score += 20
            reasons.append("Runtime due now")
        elif hours_to_due <= alert_window:
            closeness = 1.0 - (hours_to_due / max(1.0, alert_window))
            score += 8 + (closeness * 10)
            reasons.append(f"Runtime due in {hours_to_due:.1f} h")

        if float(current_hours) >= float(next_due_hours) + overdue_after_hours:
            score += 12
            reasons.append("Exceeded runtime overdue threshold")

    open_task_days = int(extra.get("open_task_days") or 0)
    if open_task_days > 0:
        score += min(16, open_task_days * 3)
        reasons.append(f"Open maintenance task for {open_task_days} day(s)")

    missed_checklist_days = int(extra.get("missed_checklist_days") or 0)
    if missed_checklist_days > 0:
        score += min(12, missed_checklist_days * 4)
        reasons.append(f"Checklist missed for {missed_checklist_days} day(s)")

    incidents_7d = int(extra.get("incidents_7d") or 0)
    if incidents_7d > 0:
        score += min(12, incidents_7d * 2)
        reasons.append(f"{incidents_7d} incident(s) in last 7 days")

    if trigger == "manual" and status == "normal":
        score = max(0.0, score - 3.0)

    risk_score = _clamp_score(score)
    return {
        "risk_score": risk_score,
        "risk_level": _risk_level(risk_score),
        "status": status,
        "trigger": trigger,
        "current_hours": current_hours,
        "next_due_hours": next_due_hours,
        "hours_to_due": hours_to_due,
        "days_to_due": days_to_due,
        "reasons": reasons[:8],
    }


def rank_machine_risk(
    machines: List[Dict[str, Any]],
    *,
    now: Optional[datetime] = None,
    reminder_days: int = 3,
    overdue_after_days: int = 2,
    extras_by_machine: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for machine in machines or []:
        machine_id = str(machine.get("id") or machine.get("name") or "").strip()
        if not machine_id:
            continue
        extras = dict((extras_by_machine or {}).get(machine_id) or {})
        prediction = predict_machine_risk(
            machine,
            now=now,
            reminder_days=reminder_days,
            overdue_after_days=overdue_after_days,
            extras=extras,
        )
        rows.append(
            {
                "machine_id": machine_id,
                "machine_name": str(machine.get("name") or machine.get("model") or machine_id).strip(),
                **prediction,
            }
        )
    rows.sort(key=lambda item: (int(item.get("risk_score", 0)), str(item.get("machine_id") or "")), reverse=True)
    return rows
