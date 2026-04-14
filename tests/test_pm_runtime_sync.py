import json

from src.ui.plant_maintenance import sync_runtime_from_hour_entry


def _write_state(path, payload):
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _read_state(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_runtime_sync_updates_usage_pm_and_lubrication_and_creates_wo(tmp_path):
    state_path = tmp_path / "plant_maintenance_state.json"
    state = {
        "equipment": [
            {"equipment_id": "CC-01", "name": "Cone Crusher"},
        ],
        "pm_schedule": [
            {
                "task_id": "PM-CC-001",
                "equipment_id": "CC-01",
                "task": "Cone oil change",
                "maintenance_type": "Usage",
                "threshold": "1000",
                "current_hours": "998",
                "status": "Planned",
                "owner": "Lube Team",
            }
        ],
        "lubrication": [
            {
                "equipment_id": "CC-01",
                "next_due_hours": "1000",
                "current_hours": "997",
                "status": "Normal",
            }
        ],
        "work_orders": [],
        "spares": [],
        "breakdowns": [],
    }
    _write_state(state_path, state)

    entry = {
        "machine": "CC-01 - Cone Crusher",
        "per_day_hours": 4,
        "hour_reading": 1234,
    }
    out = sync_runtime_from_hour_entry(entry, state_path=state_path)
    assert out["success"] is True
    assert out["matched_equipment_ids"] == ["CC-01"]

    updated = _read_state(state_path)
    pm = updated["pm_schedule"][0]
    assert float(pm["current_hours"]) == 1002.0
    assert pm["status"] == "Overdue"

    lube = updated["lubrication"][0]
    assert float(lube["current_hours"]) == 1001.0
    assert lube["status"] == "Due"

    assert len(updated["work_orders"]) == 1
    assert updated["work_orders"][0]["equipment_id"] == "CC-01"
    assert updated["work_orders"][0]["source"] == "auto_runtime_sync"


def test_runtime_sync_matches_by_name_and_avoids_duplicate_open_work_order(tmp_path):
    state_path = tmp_path / "plant_maintenance_state.json"
    state = {
        "equipment": [
            {"equipment_id": "JC-01", "name": "Jaw Crusher"},
        ],
        "pm_schedule": [
            {
                "task_id": "PM-JC-001",
                "equipment_id": "JC-01",
                "task": "Check jaw plate wear",
                "maintenance_type": "Usage",
                "threshold": "10",
                "current_hours": "9",
                "status": "Planned",
                "owner": "Mech Team",
            }
        ],
        "lubrication": [],
        "work_orders": [
            {
                "wo_id": "WO-001",
                "equipment_id": "JC-01",
                "task": "Check jaw plate wear",
                "status": "Open",
            }
        ],
        "spares": [],
        "breakdowns": [],
    }
    _write_state(state_path, state)

    entry = {
        "machine": "Jaw Crusher Line 1",
        "per_day_hours": 2,
    }
    out = sync_runtime_from_hour_entry(entry, state_path=state_path)
    assert out["success"] is True
    assert out["matched_equipment_ids"] == ["JC-01"]

    updated = _read_state(state_path)
    pm = updated["pm_schedule"][0]
    assert float(pm["current_hours"]) == 11.0
    assert pm["status"] == "Overdue"
    # No duplicate WO should be generated because one is already open for same task.
    assert len(updated["work_orders"]) == 1


def test_runtime_sync_returns_error_when_no_equipment_match(tmp_path):
    state_path = tmp_path / "plant_maintenance_state.json"
    state = {
        "equipment": [{"equipment_id": "JC-01", "name": "Jaw Crusher"}],
        "pm_schedule": [],
        "lubrication": [],
        "work_orders": [],
        "spares": [],
        "breakdowns": [],
    }
    _write_state(state_path, state)

    out = sync_runtime_from_hour_entry({"machine": "Unknown Unit", "per_day_hours": 3}, state_path=state_path)
    assert out["success"] is False
    assert out["error"] == "no_runtime_or_equipment_match"
