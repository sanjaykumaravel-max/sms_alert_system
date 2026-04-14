from datetime import datetime, timedelta

from src.machine_store import effective_machine_status


def _date_str(delta_days: int) -> str:
    return (datetime.now().date() + timedelta(days=delta_days)).isoformat()


def test_effective_machine_status_reminder_window():
    machine = {"status": "normal", "due_date": _date_str(2)}
    assert effective_machine_status(machine, reminder_days=3, overdue_after_days=2) == "maintenance"


def test_effective_machine_status_due_day():
    machine = {"status": "normal", "due_date": _date_str(0)}
    assert effective_machine_status(machine, reminder_days=3, overdue_after_days=2) == "due"


def test_effective_machine_status_overdue_after_two_days():
    machine = {"status": "normal", "due_date": _date_str(-2)}
    assert effective_machine_status(machine, reminder_days=3, overdue_after_days=2) == "overdue"


def test_effective_machine_status_manual_critical_wins():
    machine = {"status": "critical", "due_date": _date_str(5)}
    assert effective_machine_status(machine, reminder_days=3, overdue_after_days=2) == "critical"


def test_effective_machine_status_hour_based_reminder():
    machine = {
        "status": "normal",
        "hours": "992",
        "next_due_hours": "1000",
        "hour_alert_window": "10",
    }
    assert effective_machine_status(machine, reminder_days=3, overdue_after_days=2) == "maintenance"


def test_effective_machine_status_hour_based_due():
    machine = {
        "status": "normal",
        "hours": "1000",
        "next_due_hours": "1000",
    }
    assert effective_machine_status(machine, reminder_days=3, overdue_after_days=2) == "due"


def test_effective_machine_status_hour_based_overdue():
    machine = {
        "status": "normal",
        "hours": "1003",
        "next_due_hours": "1000",
        "hour_overdue_after_hours": "2",
    }
    assert effective_machine_status(machine, reminder_days=3, overdue_after_days=2) == "overdue"
