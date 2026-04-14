import json
from pathlib import Path
from uuid import uuid4

from src import api_client


def _sandbox_dir() -> Path:
    base = Path("tests") / ".runtime_tmp" / f"operator_store_{uuid4().hex}"
    base.mkdir(parents=True, exist_ok=True)
    return base


def test_get_operators_reads_local_store(monkeypatch):
    operators_file = _sandbox_dir() / "operators.json"
    operators_file.write_text(
        json.dumps(
            [
                {"id": 1, "name": "Sanjay", "phone": "+916381528758", "active": True},
                {"id": 2, "name": "Inactive User", "phone": "+919999999999", "active": False},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(api_client, "_operators_path", lambda: operators_file)

    client = api_client.APIClient()
    all_ops = api_client.asyncio.run(client.get_operators())
    active_ops = api_client.asyncio.run(client.get_operators(active_only=True))

    assert len(all_ops) == 2
    assert len(active_ops) == 1
    assert active_ops[0]["name"] == "Sanjay"


def test_create_operator_persists_to_local_store(monkeypatch):
    operators_file = _sandbox_dir() / "operators.json"
    monkeypatch.setattr(api_client, "_operators_path", lambda: operators_file)

    client = api_client.APIClient()
    created = api_client.asyncio.run(
        client.create_operator({"name": "Operator One", "phone": "+916381528758", "active": True})
    )

    assert created["id"] == 1
    payload = json.loads(operators_file.read_text(encoding="utf-8"))
    assert payload[0]["name"] == "Operator One"
