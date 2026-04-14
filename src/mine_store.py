from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, List

try:
    from .app_paths import data_path
except Exception:
    from app_paths import data_path


MINES_FILE = data_path("mines.json")

DEFAULT_MINE: Dict[str, Any] = {
    "id": "",
    "mine_name": "",
    "company_name": "",
    "quarry_type": "",
    "lease_area": "",
    "address": "",
    "logo_path": "",
    "google_maps_link": "",
    "notes": "",
    "created_at": "",
    "last_updated": "",
}


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _slugify(value: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return base or "mine"


def _empty_payload() -> Dict[str, Any]:
    return {"active_mine_id": "", "mines": []}


def normalize_mine_record(record: Dict[str, Any], *, existing_ids: set[str] | None = None) -> Dict[str, Any]:
    mine = dict(DEFAULT_MINE)
    mine.update(record or {})

    mine_name = str(mine.get("mine_name") or "").strip()
    company_name = str(mine.get("company_name") or "").strip()
    quarry_type = str(mine.get("quarry_type") or "").strip()
    lease_area = str(mine.get("lease_area") or "").strip()
    address = str(mine.get("address") or "").strip()
    logo_path = str(mine.get("logo_path") or "").strip()
    google_maps_link = str(mine.get("google_maps_link") or "").strip()
    notes = str(mine.get("notes") or "").strip()

    existing_ids = {str(item).strip() for item in (existing_ids or set()) if str(item).strip()}
    mine_id = str(mine.get("id") or "").strip()
    if not mine_id:
        root = _slugify(f"{mine_name}-{company_name}")
        mine_id = root
        suffix = 2
        while mine_id in existing_ids:
            mine_id = f"{root}-{suffix}"
            suffix += 1

    created_at = str(mine.get("created_at") or "").strip() or _now_iso()
    last_updated = _now_iso()

    return {
        "id": mine_id,
        "mine_name": mine_name,
        "company_name": company_name,
        "quarry_type": quarry_type,
        "lease_area": lease_area,
        "address": address,
        "logo_path": logo_path,
        "google_maps_link": google_maps_link,
        "notes": notes,
        "created_at": created_at,
        "last_updated": last_updated,
    }


def load_mines_payload() -> Dict[str, Any]:
    if not MINES_FILE.exists():
        return _empty_payload()
    try:
        raw = json.loads(MINES_FILE.read_text(encoding="utf-8")) or {}
    except Exception:
        return _empty_payload()
    mines = raw.get("mines")
    if not isinstance(mines, list):
        mines = []
    active_mine_id = str(raw.get("active_mine_id") or "").strip()
    normalized: List[Dict[str, Any]] = []
    used_ids: set[str] = set()
    for item in mines:
        if not isinstance(item, dict):
            continue
        mine = normalize_mine_record(item, existing_ids=used_ids)
        used_ids.add(mine["id"])
        normalized.append(mine)
    if active_mine_id and active_mine_id not in used_ids:
        active_mine_id = normalized[0]["id"] if normalized else ""
    return {"active_mine_id": active_mine_id, "mines": normalized}


def save_mines_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    current = _empty_payload()
    current.update(payload or {})
    mines = current.get("mines")
    if not isinstance(mines, list):
        mines = []
    normalized: List[Dict[str, Any]] = []
    used_ids: set[str] = set()
    for item in mines:
        if not isinstance(item, dict):
            continue
        mine = normalize_mine_record(item, existing_ids=used_ids)
        used_ids.add(mine["id"])
        normalized.append(mine)
    active_mine_id = str(current.get("active_mine_id") or "").strip()
    if not active_mine_id and normalized:
        active_mine_id = normalized[0]["id"]
    if active_mine_id and active_mine_id not in used_ids:
        active_mine_id = normalized[0]["id"] if normalized else ""

    result = {"active_mine_id": active_mine_id, "mines": normalized}
    MINES_FILE.parent.mkdir(parents=True, exist_ok=True)
    MINES_FILE.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def load_mines() -> List[Dict[str, Any]]:
    return list(load_mines_payload().get("mines") or [])


def save_mines(mines: List[Dict[str, Any]], *, active_mine_id: str | None = None) -> Dict[str, Any]:
    payload = load_mines_payload()
    payload["mines"] = list(mines or [])
    if active_mine_id is not None:
        payload["active_mine_id"] = str(active_mine_id or "").strip()
    return save_mines_payload(payload)


def get_active_mine_id() -> str:
    return str(load_mines_payload().get("active_mine_id") or "").strip()


def set_active_mine(mine_id: str) -> Dict[str, Any]:
    payload = load_mines_payload()
    payload["active_mine_id"] = str(mine_id or "").strip()
    return save_mines_payload(payload)


def get_active_mine() -> Dict[str, Any] | None:
    payload = load_mines_payload()
    active_id = str(payload.get("active_mine_id") or "").strip()
    mines = payload.get("mines") or []
    for mine in mines:
        if str(mine.get("id") or "").strip() == active_id:
            return dict(mine)
    if mines:
        return dict(mines[0])
    return None
