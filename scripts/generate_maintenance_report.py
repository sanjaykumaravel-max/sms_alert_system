#!/usr/bin/env python3
"""Generate maintenance report headlessly and save to data/maintenance_report.json

Tries to reuse `ReportsFrame._get_report_data` if GUI libs present; otherwise falls back
to direct file reads so this script works in minimal environments.
"""
import sys
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
OUT = DATA_DIR / "maintenance_report.json"

# Try to import ReportsFrame (uses customtkinter); fallback to file aggregation
try:
    sys.path.insert(0, str(ROOT))
    from src.ui.reports import ReportsFrame, DATA_DIR as RF_DATA_DIR
    import customtkinter as ctk
    # create hidden root to satisfy CTkFrame init
    root = ctk.CTk()
    root.withdraw()
    rf = ReportsFrame(root)
    data = rf._get_report_data('maintenance')
except Exception:
    # Fallback: assemble the maintenance report from data files
    try:
        def _load_json(p):
            try:
                if p.exists():
                    return json.loads(p.read_text(encoding='utf-8'))
            except Exception:
                return None
            return None

        machines = None
        try:
            import pandas as pd
            mpath = DATA_DIR / "machines.xlsx"
            if mpath.exists():
                machines = pd.read_excel(mpath).to_dict('records')
        except Exception:
            machines = None

        if machines is None:
            machines = _load_json(DATA_DIR / "machines.json") or []

        tasks = _load_json(DATA_DIR / "maintenance_tasks.json") or []
        hours = _load_json(DATA_DIR / "hour_entries.json") or []
        plant = _load_json(DATA_DIR / "plant_components.json") or {}
        parts = _load_json(DATA_DIR / "parts.json") or []

        # classify overdue/upcoming using a 100-hour threshold
        cur_map = {}
        for m in machines:
            for k in ('current_hours', 'hour_reading', 'operating_hours', 'hours'):
                try:
                    if k in m and m[k] not in (None, ''):
                        cur_map[str(m.get('id') or m.get('name') or '')] = float(m[k])
                        break
                except Exception:
                    continue

        overdue = []
        upcoming = []
        thresh = 100.0
        for t in tasks:
            try:
                mid = str(t.get('machine_id') or '')
                due = float(t.get('due_at_hours')) if t.get('due_at_hours') is not None else None
                cur = cur_map.get(mid)
                if due is None or cur is None:
                    continue
                if due <= cur:
                    overdue.append(t)
                elif due - cur <= thresh:
                    upcoming.append(t)
            except Exception:
                continue

        data = {
            'machines': machines,
            'tasks': tasks,
            'hour_entries': hours,
            'plant_components': plant,
            'parts': parts,
            'overdue': overdue,
            'upcoming': upcoming,
        }
    except Exception:
        data = {}

# Save output
try:
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, default=str)
    print(f"Saved maintenance report to: {OUT}")
except Exception as e:
    print(f"Failed to save report: {e}")
    sys.exit(2)
