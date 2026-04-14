from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from .app_paths import data_path
except Exception:
    from app_paths import data_path


INCIDENTS_FILE = data_path("incident_feed.json")


def _now() -> datetime:
    return datetime.now()


def _safe_parse_iso(value: Any) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except Exception:
        return None


def load_incidents(*, path: Optional[Path] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    target = path or INCIDENTS_FILE
    try:
        if target.exists():
            payload = json.loads(target.read_text(encoding="utf-8")) or []
            if isinstance(payload, list):
                rows = [dict(item) for item in payload if isinstance(item, dict)]
            else:
                rows = []
        else:
            rows = []
    except Exception:
        rows = []
    rows.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
    if isinstance(limit, int) and limit > 0:
        return rows[:limit]
    return rows


def save_incidents(rows: List[Dict[str, Any]], *, path: Optional[Path] = None) -> None:
    target = path or INCIDENTS_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def append_incident(
    *,
    category: str,
    severity: str,
    title: str,
    message: str,
    trigger: str,
    source: str,
    machine_id: str = "",
    task_id: str = "",
    dedup_key: Optional[str] = None,
    dedup_window_minutes: int = 60,
    extra: Optional[Dict[str, Any]] = None,
    path: Optional[Path] = None,
) -> Tuple[bool, Dict[str, Any]]:
    rows = load_incidents(path=path, limit=None)
    now = _now()
    key = str(dedup_key or "").strip()
    dedup_delta = timedelta(minutes=max(1, int(dedup_window_minutes or 1)))

    if key:
        for row in rows:
            if str(row.get("dedup_key") or "").strip() != key:
                continue
            created_at = _safe_parse_iso(row.get("created_at"))
            if created_at is None:
                continue
            if (now - created_at) <= dedup_delta:
                return False, row

    incident = {
        "id": f"inc_{int(now.timestamp() * 1000)}_{len(rows) + 1}",
        "created_at": now.isoformat(timespec="seconds"),
        "category": str(category or "general").strip().lower() or "general",
        "severity": str(severity or "info").strip().lower() or "info",
        "title": str(title or "").strip(),
        "message": str(message or "").strip(),
        "trigger": str(trigger or "").strip().lower() or "system",
        "source": str(source or "automation").strip().lower() or "automation",
        "machine_id": str(machine_id or "").strip(),
        "task_id": str(task_id or "").strip(),
        "dedup_key": key,
    }
    if isinstance(extra, dict) and extra:
        incident["extra"] = dict(extra)

    rows.append(incident)
    # keep file bounded for smooth app performance
    rows.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
    save_incidents(rows[:1200], path=path)
    return True, incident
