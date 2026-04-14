import asyncio
import json
import sys
from pathlib import Path
import os

import pytest

# Ensure project root is importable (so `import src.server_async` works)
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


def test_generate_from_templates(tmp_path, monkeypatch):
    templates_file = tmp_path / "templates.json"
    tasks_file = tmp_path / "tasks.json"

    # simple daily template
    tpl = {
        "id": "tpl_test_unit",
        "name": "Unit Test Daily",
        "subject": "Unit Task",
        "type": "daily",
        "every": 1,
        "start": None,
    }

    _write(templates_file, [tpl])
    _write(tasks_file, [])

    # point server helpers to our temp files
    monkeypatch.setattr(server_async, "_templates_path", lambda: templates_file)
    monkeypatch.setattr(server_async, "_tasks_path", lambda: tasks_file)

    res = asyncio.run(server_async.api_generate_from_templates(horizon_days=3, dedup_minutes=60))
    assert isinstance(res, dict)
    assert res.get("created", 0) > 0

    tasks = _read(tasks_file)
    assert any(t.get("subject") == "Unit Task" for t in tasks)
