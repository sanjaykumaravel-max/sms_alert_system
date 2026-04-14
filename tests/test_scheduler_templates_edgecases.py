import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta

import pytest

# ensure project root importable
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import src.server_async as server_async


def _write(p: Path, data):
    p.write_text(json.dumps(data, indent=2))


def _read(p: Path):
    if not p.exists():
        return []
    return json.loads(p.read_text())


def test_deduplication_prevents_duplicates(tmp_path, monkeypatch):
    templates_file = tmp_path / "templates.json"
    tasks_file = tmp_path / "tasks.json"

    tpl = {
        "id": "tpl_dup",
        "name": "Dup",
        "subject": "Dup Task",
        "type": "daily",
        "every": 1,
        "start": None,
    }

    # existing task scheduled at the midnight occurrence the generator will produce (tomorrow midnight)
    now = datetime.utcnow()
    occ_dt = datetime.combine((now + timedelta(days=1)).date(), datetime.min.time())
    existing = {"id": "existing1", "subject": "Dup Task", "scheduled_at": occ_dt.isoformat(), "status": "pending"}

    _write(templates_file, [tpl])
    _write(tasks_file, [existing])

    monkeypatch.setattr(server_async, "_templates_path", lambda: templates_file)
    monkeypatch.setattr(server_async, "_tasks_path", lambda: tasks_file)

    res = asyncio.run(server_async.api_generate_from_templates(horizon_days=1, dedup_minutes=60))
    assert isinstance(res, dict)
    # no new tasks should be created due to dedup
    assert res.get("created", 0) == 0
    tasks = _read(tasks_file)
    assert len(tasks) == 1


def test_hourly_generation_creates_expected_intervals(tmp_path, monkeypatch):
    templates_file = tmp_path / "templates.json"
    tasks_file = tmp_path / "tasks.json"

    tpl = {
        "id": "tpl_hour",
        "name": "Hourly",
        "subject": "Hourly Task",
        "type": "hourly",
        "interval_hours": 6,
        "start": None,
    }

    _write(templates_file, [tpl])
    _write(tasks_file, [])

    monkeypatch.setattr(server_async, "_templates_path", lambda: templates_file)
    monkeypatch.setattr(server_async, "_tasks_path", lambda: tasks_file)

    res = asyncio.run(server_async.api_generate_from_templates(horizon_days=1, dedup_minutes=1))
    assert isinstance(res, dict)
    created = res.get("created", 0)
    # over 24 hours, interval 6 hours should create roughly 4 occurrences
    assert created >= 3

    tasks = _read(tasks_file)
    subjects = [t.get("subject") for t in tasks]
    assert "Hourly Task" in subjects
