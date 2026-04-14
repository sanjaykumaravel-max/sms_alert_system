import json
import re
import tkinter as tk
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Dict, List, Optional

import customtkinter as ctk

try:
    from ..app_paths import data_dir
except Exception:
    from app_paths import data_dir
from .theme import SIMPLE_PALETTE
from . import theme as theme_mod
from .gradient import GradientPanel

PALETTE = SIMPLE_PALETTE


def _pm_data_dir() -> Path:
    path = data_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _pm_state_path() -> Path:
    return _pm_data_dir() / "plant_maintenance_state.json"


def _pm_num(value: Any, default: float = 0.0) -> float:
    try:
        txt = str(value or "").strip()
        m = re.search(r"-?\d+(\.\d+)?", txt)
        return float(m.group()) if m else default
    except Exception:
        return default


def _pm_next_wo_id(work_orders: List[Dict[str, Any]]) -> str:
    max_num = 0
    for row in work_orders or []:
        m = re.search(r"(\d+)$", str((row or {}).get("wo_id", "")))
        if m:
            max_num = max(max_num, int(m.group(1)))
    return f"WO-{max_num + 1:03d}"


def _pm_normalize_machine_text(machine_value: Any) -> str:
    return str(machine_value or "").strip().lower()


def _pm_runtime_hours_from_entry(entry: Dict[str, Any]) -> float:
    runtime = _pm_num(entry.get("per_day_hours"), 0.0)
    if runtime > 0:
        return runtime
    try:
        open_raw = str(entry.get("opening", "")).strip()
        close_raw = str(entry.get("closing", "")).strip()
        if not open_raw or not close_raw:
            return 0.0
        oh, om = [int(x) for x in open_raw.split(":", 1)]
        ch, cm = [int(x) for x in close_raw.split(":", 1)]
        open_h = oh + (om / 60.0)
        close_h = ch + (cm / 60.0)
        diff = close_h - open_h
        if diff < 0:
            diff += 24
        return max(0.0, diff)
    except Exception:
        return 0.0


def _pm_resolve_equipment_ids(machine_value: Any, equipment_rows: List[Dict[str, Any]]) -> List[str]:
    txt = _pm_normalize_machine_text(machine_value)
    if not txt:
        return []

    matched: List[str] = []
    for row in equipment_rows or []:
        eq_id = str((row or {}).get("equipment_id", "")).strip()
        name = str((row or {}).get("name", "")).strip().lower()
        if not eq_id:
            continue
        eq_id_low = eq_id.lower()
        if eq_id_low and eq_id_low in txt:
            matched.append(eq_id)
            continue
        if name and (name in txt or txt in name):
            matched.append(eq_id)

    # Fallback keyword mapping for crushing line labels.
    if not matched:
        keywords = (
            ("jaw", "JC"),
            ("cone", "CC"),
            ("screen", "VS"),
            ("vibrating", "VS"),
            ("conveyor", "CV"),
            ("hopper", "FH"),
        )
        for key, id_hint in keywords:
            if key not in txt:
                continue
            for row in equipment_rows or []:
                eq_id = str((row or {}).get("equipment_id", "")).strip()
                name = str((row or {}).get("name", "")).lower()
                if not eq_id:
                    continue
                if eq_id.upper().startswith(id_hint) or key in name:
                    matched.append(eq_id)
                    break

    # De-duplicate while preserving order.
    out: List[str] = []
    seen = set()
    for eq_id in matched:
        key = eq_id.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(eq_id)
    return out


def sync_runtime_from_hour_entry(entry: Dict[str, Any], state_path: Optional[Path] = None) -> Dict[str, Any]:
    """Update plant-maintenance runtime counters from an hour-entry record."""
    state_path = state_path or _pm_state_path()
    if not state_path.exists():
        return {"success": False, "error": "plant_maintenance_state_missing", "state_path": str(state_path)}

    try:
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f) or {}
    except Exception as exc:
        return {"success": False, "error": "state_read_failed", "detail": str(exc), "state_path": str(state_path)}

    if not isinstance(state, dict):
        return {"success": False, "error": "invalid_state_payload", "state_path": str(state_path)}

    runtime_delta = _pm_runtime_hours_from_entry(entry)
    hour_reading = entry.get("hour_reading")
    matched_equipment_ids = _pm_resolve_equipment_ids(entry.get("machine"), state.get("equipment", []))
    if runtime_delta <= 0 or not matched_equipment_ids:
        return {
            "success": False,
            "error": "no_runtime_or_equipment_match",
            "runtime_delta": runtime_delta,
            "matched_equipment_ids": matched_equipment_ids,
        }

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    updated_pm = 0
    updated_lube = 0

    # Update equipment runtime shadow fields.
    for row in state.get("equipment", []) or []:
        eq_id = str((row or {}).get("equipment_id", "")).strip()
        if eq_id not in matched_equipment_ids:
            continue
        total_runtime = _pm_num(row.get("runtime_hours_total"), 0.0) + runtime_delta
        row["runtime_hours_total"] = round(total_runtime, 2)
        row["last_runtime_sync"] = timestamp
        if hour_reading is not None and str(hour_reading).strip() != "":
            row["last_hour_reading"] = hour_reading

    # Update usage-based PM tasks.
    for row in state.get("pm_schedule", []) or []:
        eq_id = str((row or {}).get("equipment_id", "")).strip()
        if eq_id not in matched_equipment_ids:
            continue
        if str(row.get("maintenance_type", "")).lower() != "usage":
            continue
        current = _pm_num(row.get("current_hours"), 0.0) + runtime_delta
        row["current_hours"] = round(current, 2)
        threshold = _pm_num(row.get("threshold"), 0.0)
        if threshold > 0 and current >= threshold:
            row["status"] = "Overdue"
        elif threshold > 0 and current >= 0.9 * threshold:
            row["status"] = "Due Soon"
        else:
            row["status"] = "Planned"
        row["last_runtime_sync"] = timestamp
        updated_pm += 1

    # Update lubrication counters.
    for row in state.get("lubrication", []) or []:
        eq_id = str((row or {}).get("equipment_id", "")).strip()
        if eq_id not in matched_equipment_ids:
            continue
        current = _pm_num(row.get("current_hours"), 0.0) + runtime_delta
        row["current_hours"] = round(current, 2)
        due_h = _pm_num(row.get("next_due_hours"), 0.0)
        if due_h > 0 and current >= due_h:
            row["status"] = "Due"
        elif due_h > 0 and current >= 0.9 * due_h:
            row["status"] = "Watch"
        else:
            row["status"] = "Normal"
        row["last_runtime_sync"] = timestamp
        updated_lube += 1

    # Auto-generate work orders for newly due usage PM tasks.
    work_orders = state.setdefault("work_orders", [])
    open_set = {
        (str((wo or {}).get("equipment_id", "")), str((wo or {}).get("task", "")))
        for wo in work_orders
        if str((wo or {}).get("status", "")).lower() != "closed"
    }
    created_work_orders = 0
    for row in state.get("pm_schedule", []) or []:
        if str(row.get("maintenance_type", "")).lower() != "usage":
            continue
        eq_id = str(row.get("equipment_id", ""))
        if eq_id not in matched_equipment_ids:
            continue
        status = str(row.get("status", "")).lower()
        key = (eq_id, str(row.get("task", "")))
        if status not in ("overdue", "due soon") or key in open_set:
            continue
        work_orders.append(
            {
                "wo_id": _pm_next_wo_id(work_orders),
                "equipment_id": eq_id,
                "task": row.get("task", ""),
                "priority": "High" if status == "overdue" else "Medium",
                "due_date": datetime.now().strftime("%Y-%m-%d"),
                "status": "Open",
                "assigned_to": row.get("owner", "Maintenance Team"),
                "estimated_cost": "0",
                "source": "auto_runtime_sync",
            }
        )
        open_set.add(key)
        created_work_orders += 1

    try:
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as exc:
        return {"success": False, "error": "state_write_failed", "detail": str(exc), "state_path": str(state_path)}

    return {
        "success": True,
        "runtime_delta": round(runtime_delta, 2),
        "matched_equipment_ids": matched_equipment_ids,
        "updated_pm_rows": updated_pm,
        "updated_lubrication_rows": updated_lube,
        "created_work_orders": created_work_orders,
        "state_path": str(state_path),
    }


class PlantMaintenanceFrame(ctk.CTkFrame):
    """Preventive-maintenance workspace for crushing plant operations."""

    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        local_data_dir = _pm_data_dir()
        local_data_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = local_data_dir / "plant_maintenance_state.json"
        self.components_path = local_data_dir / "plant_components.json"
        self.state: Dict[str, Any] = {}
        self.components: Dict[str, List[Dict[str, str]]] = {}
        self.trees: Dict[str, ttk.Treeview] = {}
        self.kpis: Dict[str, ctk.CTkLabel] = {}
        self.alerts_list: Optional[tk.Listbox] = None
        self.component_boxes: Dict[str, tk.Listbox] = {}
        self.table_style_name = "PM.Dark.Treeview"

        self.specs: Dict[str, Dict[str, Any]] = {}
        self._load_state()
        self._load_components()
        self._apply_table_theme()
        self._build_ui()
        self._refresh_all()

    def _today(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def _apply_table_theme(self):
        style = ttk.Style(self)
        # "clam" honors dark color customizations for Treeview more reliably on Windows.
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        heading_style = f"{self.table_style_name}.Heading"
        style.configure(
            self.table_style_name,
            background="#0f172a",
            fieldbackground="#0f172a",
            foreground="#e2e8f0",
            borderwidth=0,
            rowheight=34,
            font=("Segoe UI", 12),
        )
        style.map(
            self.table_style_name,
            background=[("selected", "#1d4ed8")],
            foreground=[("selected", "#f8fafc")],
        )
        style.configure(
            heading_style,
            background="#111827",
            foreground="#cbd5e1",
            relief="flat",
            borderwidth=0,
            font=("Segoe UI Semibold", 12),
            padding=(8, 8),
        )
        style.map(
            heading_style,
            background=[("active", "#1f2937")],
            foreground=[("active", "#f8fafc")],
        )

    def _num(self, value: Any, default: float = 0.0) -> float:
        try:
            txt = str(value or "").strip()
            m = re.search(r"-?\d+(\.\d+)?", txt)
            return float(m.group()) if m else default
        except Exception:
            return default

    def _parse_date(self, value: Any) -> Optional[datetime]:
        try:
            txt = str(value or "").strip()
            if not txt or txt == "-":
                return None
            return datetime.strptime(txt, "%Y-%m-%d")
        except Exception:
            return None

    def _default_state(self) -> Dict[str, Any]:
        today = datetime.now().date()
        return {
            "equipment": [
                {
                    "equipment_id": "JC-01",
                    "name": "Jaw Crusher",
                    "type": "Primary Crusher",
                    "stage": "Primary",
                    "capacity": "190-200 TPH",
                    "feed_size": "700-600 mm",
                    "output_size": "180-150 mm",
                    "criticality": "High",
                    "status": "Running",
                    "notes": "Fixed jaw ~1 month, movable jaw ~2 months in high wear feed.",
                },
                {
                    "equipment_id": "CC-01",
                    "name": "Cone Crusher",
                    "type": "Secondary Crusher",
                    "stage": "Secondary",
                    "capacity": "500-600 T/day",
                    "feed_size": "160 mm",
                    "output_size": "50-55 mm",
                    "criticality": "High",
                    "status": "Running",
                    "notes": "Oil about 20 L/day and 1000 h cycle.",
                },
                {
                    "equipment_id": "VS-01",
                    "name": "Vibrating Screen",
                    "type": "Screening",
                    "stage": "Final",
                    "capacity": "Plant dependent",
                    "feed_size": "50 mm",
                    "output_size": "0-22 mm",
                    "criticality": "Medium",
                    "status": "Running",
                    "notes": "Oversize recycle to cone, undersize final output.",
                },
            ],
            "pm_schedule": [
                {
                    "task_id": "PM-JC-001",
                    "equipment_id": "JC-01",
                    "task": "Check jaw plate wear",
                    "frequency": "Weekly",
                    "maintenance_type": "Time",
                    "threshold": "-",
                    "current_hours": "0",
                    "next_due": str(today + timedelta(days=7)),
                    "last_done": "",
                    "status": "Planned",
                    "owner": "Mechanical Team",
                },
                {
                    "task_id": "PM-CC-001",
                    "equipment_id": "CC-01",
                    "task": "Cone oil change",
                    "frequency": "Usage",
                    "maintenance_type": "Usage",
                    "threshold": "1000",
                    "current_hours": "820",
                    "next_due": "-",
                    "last_done": "",
                    "status": "Planned",
                    "owner": "Lubrication Team",
                },
            ],
            "inspections": [],
            "breakdowns": [],
            "lubrication": [
                {
                    "equipment_id": "CC-01",
                    "oil_type": "Hydraulic/Lube",
                    "quantity_l_per_day": "20",
                    "last_changed": "",
                    "next_due_hours": "1000",
                    "current_hours": "820",
                    "status": "Normal",
                }
            ],
            "spares": [
                {"part": "Jaw Plate Fixed", "equipment_id": "JC-01", "stock": "2", "min_level": "1", "location": "Main Store", "last_updated": self._today()},
                {"part": "Cone Liner", "equipment_id": "CC-01", "stock": "3", "min_level": "1", "location": "Main Store", "last_updated": self._today()},
            ],
            "work_orders": [
                {"wo_id": "WO-001", "equipment_id": "JC-01", "task": "Weekly jaw check", "priority": "High", "due_date": str(today + timedelta(days=1)), "status": "Open", "assigned_to": "Mechanical Team", "estimated_cost": "1500"}
            ],
        }

    def _default_components(self) -> Dict[str, List[Dict[str, str]]]:
        return {
            "primary_crusher": [{"name": "Fixed Jaw Plate", "details": "Monitor thickness and wear profile."}, {"name": "Movable Jaw Plate", "details": "Replace as per wear limit."}],
            "secondary_crusher": [{"name": "Mantle", "details": "Check liner wear."}, {"name": "Concave", "details": "Track CSS and profile."}],
            "conveyor": [{"name": "Belt", "details": "Check alignment."}, {"name": "Roller", "details": "Replace noisy rollers."}],
            "screen": [{"name": "Deck", "details": "Check panel integrity."}, {"name": "Mesh", "details": "Watch tears and blinding."}],
        }

    def _load_state(self):
        if not self.state_path.exists():
            self.state = self._default_state()
            self._save_state()
            return
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                loaded = json.load(f) or {}
        except Exception:
            loaded = {}
        base = self._default_state()
        for key in base:
            if isinstance(loaded.get(key), list):
                base[key] = loaded[key]
        self.state = base

    def _save_state(self):
        try:
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2)
        except Exception:
            pass

    def _load_components(self):
        if not self.components_path.exists():
            self.components = self._default_components()
            self._save_components()
            return
        try:
            with open(self.components_path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
        except Exception:
            data = {}
        base = self._default_components()
        for key in base:
            rows = data.get(key)
            if isinstance(rows, list) and rows:
                out = []
                for it in rows:
                    if isinstance(it, dict):
                        out.append({"name": str(it.get("name", "")).strip(), "details": str(it.get("details", "")).strip()})
                    else:
                        out.append({"name": str(it).strip(), "details": ""})
                base[key] = [r for r in out if r["name"]] or base[key]
        self.components = base

    def _save_components(self):
        try:
            with open(self.components_path, "w", encoding="utf-8") as f:
                json.dump(self.components, f, indent=2)
        except Exception:
            pass

    def _next_wo_id(self) -> str:
        max_num = 0
        for row in self.state.get("work_orders", []):
            m = re.search(r"(\d+)$", str(row.get("wo_id", "")))
            if m:
                max_num = max(max_num, int(m.group(1)))
        return f"WO-{max_num + 1:03d}"

    def _task_status(self, row: Dict[str, Any]) -> str:
        status = str(row.get("status", "") or "Planned")
        if status.lower() in ("closed", "completed"):
            return status
        if str(row.get("maintenance_type", "")).lower() == "usage":
            th = self._num(row.get("threshold"), 0)
            cur = self._num(row.get("current_hours"), 0)
            if th > 0 and cur >= th:
                return "Overdue"
            if th > 0 and cur >= 0.9 * th:
                return "Due Soon"
            return "Planned"
        due = self._parse_date(row.get("next_due"))
        if due is None:
            return status
        today = datetime.now().date()
        if due.date() < today:
            return "Overdue"
        if due.date() <= today + timedelta(days=3):
            return "Due Soon"
        return "Planned"

    def _compute_alerts(self) -> List[str]:
        alerts: List[str] = []
        today = datetime.now().date()
        for row in self.state.get("pm_schedule", []):
            s = self._task_status(row)
            if s in ("Overdue", "Due Soon"):
                alerts.append(f"{s}: {row.get('task', '')} ({row.get('equipment_id', '-')})")
        for row in self.state.get("spares", []):
            stock = int(self._num(row.get("stock"), 0))
            min_level = int(self._num(row.get("min_level"), 0))
            if stock <= min_level:
                alerts.append(f"Low stock: {row.get('part', '')} ({stock} <= {min_level})")
        for row in self.state.get("lubrication", []):
            due_h = self._num(row.get("next_due_hours"), 0)
            cur_h = self._num(row.get("current_hours"), 0)
            if due_h > 0 and cur_h >= due_h:
                alerts.append(f"Lubrication due: {row.get('equipment_id', '')} at {int(cur_h)}/{int(due_h)} h")
        for row in self.state.get("work_orders", []):
            if str(row.get("status", "")).lower() == "closed":
                continue
            due = self._parse_date(row.get("due_date"))
            if due is not None and due.date() < today:
                alerts.append(f"Overdue WO: {row.get('wo_id', '')} ({row.get('equipment_id', '')})")
        for row in self.state.get("breakdowns", []):
            if str(row.get("status", "")).lower() not in ("closed", "resolved"):
                alerts.append(f"Open breakdown: {row.get('equipment_id', '')} {row.get('failure_type', '')}")
        if not alerts:
            alerts.append("No active alerts. System is under control.")
        return alerts

    def _selected_index(self, key: str) -> Optional[int]:
        tree = self.trees.get(key)
        if tree is None:
            return None
        try:
            sel = tree.selection()
            if not sel:
                return None
            idx = int(sel[0])
            return idx if idx >= 0 else None
        except Exception:
            return None

    def _open_form_dialog(self, title: str, fields: List[tuple[str, str, str]], initial: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, str]]:
        initial = initial or {}
        result: Dict[str, str] = {}
        top = ctk.CTkToplevel(self)
        top.title(title)
        top.geometry("500x560")
        top.transient(self.winfo_toplevel())
        top.grab_set()

        panel = ctk.CTkScrollableFrame(top)
        panel.pack(fill="both", expand=True, padx=12, pady=12)
        vars_map: Dict[str, tk.StringVar] = {}
        for key, label, placeholder in fields:
            ctk.CTkLabel(panel, text=label, font=("Segoe UI", 13)).pack(anchor="w", pady=(8, 2))
            var = tk.StringVar(value=str(initial.get(key, "")))
            ctk.CTkEntry(panel, textvariable=var, placeholder_text=placeholder, height=34).pack(fill="x")
            vars_map[key] = var

        footer = ctk.CTkFrame(top, fg_color="transparent")
        footer.pack(fill="x", padx=12, pady=(0, 12))

        def _save():
            for k, var in vars_map.items():
                result[k] = str(var.get() or "").strip()
            top.destroy()

        def _cancel():
            result.clear()
            top.destroy()

        ctk.CTkButton(footer, text="Save", width=90, command=_save).pack(side="left")
        ctk.CTkButton(footer, text="Cancel", width=90, command=_cancel, fg_color="#334155", hover_color="#475569").pack(side="left", padx=(8, 0))
        self.wait_window(top)
        return result or None

    def _build_ui(self):
        shell = ctk.CTkFrame(self, fg_color="transparent")
        shell.pack(fill="both", expand=True, padx=18, pady=18)

        header = GradientPanel(
            shell,
            colors=getattr(theme_mod, "SECTION_GRADIENTS", {}).get("plant_maintenance", ("#120a21", "#6d28d9", "#a78bfa")),
            corner_radius=14,
            border_color="#1d2a3f",
        )
        header.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(header.content, text="Plant Maintenance Control Center", font=("Segoe UI Semibold", 24), text_color="#f8fafc").pack(anchor="w", padx=14, pady=(12, 2))
        ctk.CTkLabel(
            header.content,
            text="Primary Jaw + Secondary Cone + Screening. Preventive maintenance, inspections, spares, work orders, and alerts.",
            font=("Segoe UI", 13),
            text_color="#e9d5ff",
        ).pack(anchor="w", padx=14, pady=(0, 10))

        kpi_row = ctk.CTkFrame(header.content, fg_color="transparent")
        kpi_row.pack(fill="x", padx=12, pady=(0, 12))

        def _kpi(title: str) -> ctk.CTkLabel:
            card = ctk.CTkFrame(kpi_row, fg_color="#0b1220", corner_radius=10)
            card.pack(side="left", fill="x", expand=True, padx=4)
            ctk.CTkLabel(card, text=title, font=("Segoe UI", 11), text_color="#94a3b8").pack(anchor="w", padx=10, pady=(8, 2))
            value = ctk.CTkLabel(card, text="0", font=("Segoe UI Semibold", 15), text_color="#f8fafc")
            value.pack(anchor="w", padx=10, pady=(0, 10))
            return value

        self.kpis["equipment"] = _kpi("Equipment")
        self.kpis["due_pm"] = _kpi("Due PM")
        self.kpis["open_wo"] = _kpi("Open Work Orders")
        self.kpis["alerts"] = _kpi("Alerts")

        tabs = ctk.CTkTabview(shell, corner_radius=12)
        tabs.pack(fill="both", expand=True)
        self._build_overview_tab(tabs.add("Overview"))
        self._build_data_tab(tabs.add("Equipment"), "equipment")
        self._build_data_tab(tabs.add("PM Planner"), "pm_schedule")
        self._build_data_tab(tabs.add("Inspection"), "inspections")
        self._build_data_tab(tabs.add("Breakdown"), "breakdowns")
        self._build_data_tab(tabs.add("Lubrication"), "lubrication")
        self._build_data_tab(tabs.add("Spares"), "spares")
        self._build_data_tab(tabs.add("Work Orders"), "work_orders")
        self._build_alerts_tab(tabs.add("Alerts"))
        self._build_components_tab(tabs.add("Components"))

    def _build_overview_tab(self, tab):
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_columnconfigure(1, weight=1)
        flow = ctk.CTkFrame(tab, fg_color="#0b1220", corner_radius=10)
        flow.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 8))
        ctk.CTkLabel(flow, text="Process Flow", font=("Segoe UI Semibold", 15), text_color="#e2e8f0").pack(anchor="w", padx=12, pady=(10, 4))
        ctk.CTkLabel(flow, text="Jaw 700 mm -> 150 mm | Cone 150 mm -> 50 mm | Screen 50 mm -> 0-22 mm", font=("Segoe UI", 12), text_color="#cbd5e1").pack(anchor="w", padx=12, pady=(0, 10))

        left = ctk.CTkTextbox(tab, font=("Consolas", 12), height=280)
        left.grid(row=1, column=0, sticky="nsew", padx=(10, 5), pady=(0, 10))
        left.insert("1.0", "Primary Jaw:\n- Compression crushing\n- Capacity 190-200 TPH\n- Plate wear driven by hardness and abrasiveness\n- Fixed plate life ~1 month, movable ~2 months\n\nSecondary Cone:\n- Eccentric compression\n- Capacity 500-600 T/day\n- Oil around 20 L/day\n- 1000 h lubrication cycle\n\nKey risks:\n- Jaw choking from oversized feed\n- Cone overfeed and poor lubrication\n- Uneven feed causing liner wear")
        left.configure(state="disabled")

        right = ctk.CTkTextbox(tab, font=("Consolas", 12), height=280)
        right.grid(row=1, column=1, sticky="nsew", padx=(5, 10), pady=(0, 10))
        right.insert("1.0", "CMMS Implementation:\n1. Equipment registry\n2. Preventive schedule (time + usage)\n3. Inspection checklist logs\n4. Breakdown tracking and MTTR/MTBF base data\n5. Lubrication tracker\n6. Spare stock reorder logic\n7. Work order lifecycle\n8. Alert engine\n\nApp logic:\n- if today >= next_due -> maintenance due\n- if hours >= threshold -> maintenance due\n- if stock <= min_level -> reorder alert")
        right.configure(state="disabled")

    def _build_data_tab(self, tab, key: str):
        specs: Dict[str, Dict[str, Any]] = {
            "equipment": {
                "columns": [
                    ("equipment_id", "Equipment ID", 110), ("name", "Name", 150), ("type", "Type", 120), ("stage", "Stage", 85),
                    ("capacity", "Capacity", 100), ("feed_size", "Feed", 90), ("output_size", "Output", 90), ("criticality", "Criticality", 90), ("status", "Status", 90),
                ],
                "fields": [
                    ("equipment_id", "Equipment ID", "JC-01"), ("name", "Name", "Jaw Crusher"), ("type", "Type", "Primary Crusher"),
                    ("stage", "Stage", "Primary"), ("capacity", "Capacity", "200 TPH"), ("feed_size", "Feed Size", "700 mm"),
                    ("output_size", "Output Size", "150 mm"), ("criticality", "Criticality", "High"), ("status", "Status", "Running"), ("notes", "Notes", ""),
                ],
            },
            "pm_schedule": {
                "columns": [
                    ("task_id", "Task ID", 95), ("equipment_id", "Equip", 70), ("task", "Task", 210), ("frequency", "Freq", 80),
                    ("maintenance_type", "Type", 70), ("threshold", "Threshold", 85), ("current_hours", "Current Hrs", 90),
                    ("next_due", "Next Due", 95), ("status", "Status", 85), ("owner", "Owner", 120),
                ],
                "fields": [
                    ("task_id", "Task ID", "PM-001"), ("equipment_id", "Equipment ID", "JC-01"), ("task", "Task", "Check wear"),
                    ("frequency", "Frequency", "Weekly"), ("maintenance_type", "Maintenance Type", "Time or Usage"),
                    ("threshold", "Threshold", "1000"), ("current_hours", "Current Hours", "0"), ("next_due", "Next Due (YYYY-MM-DD)", self._today()),
                    ("last_done", "Last Done", ""), ("status", "Status", "Planned"), ("owner", "Owner", "Maintenance Team"),
                ],
            },
            "inspections": {
                "columns": [("date", "Date", 95), ("equipment_id", "Equip", 70), ("parameter", "Parameter", 220), ("status", "Status", 85), ("remarks", "Remarks", 240), ("inspector", "Inspector", 110)],
                "fields": [("date", "Date", self._today()), ("equipment_id", "Equipment ID", "JC-01"), ("parameter", "Parameter", "Vibration"), ("status", "Status", "OK"), ("remarks", "Remarks", ""), ("inspector", "Inspector", "Shift A")],
            },
            "breakdowns": {
                "columns": [("date", "Date", 95), ("equipment_id", "Equip", 70), ("failure_type", "Failure", 120), ("cause", "Cause", 160), ("downtime_hours", "Down h", 80), ("action_taken", "Action", 190), ("cost", "Cost", 80), ("status", "Status", 90)],
                "fields": [("date", "Date", self._today()), ("equipment_id", "Equipment ID", "JC-01"), ("failure_type", "Failure Type", "Mechanical"), ("cause", "Cause", ""), ("downtime_hours", "Downtime Hours", "0"), ("action_taken", "Action Taken", ""), ("cost", "Cost", "0"), ("status", "Status", "Open")],
            },
            "lubrication": {
                "columns": [("equipment_id", "Equip", 70), ("oil_type", "Oil Type", 160), ("quantity_l_per_day", "L/day", 70), ("last_changed", "Last Changed", 100), ("next_due_hours", "Next Hrs", 90), ("current_hours", "Current Hrs", 90), ("status", "Status", 90)],
                "fields": [("equipment_id", "Equipment ID", "CC-01"), ("oil_type", "Oil Type", "Hydraulic/Lube"), ("quantity_l_per_day", "Quantity L/day", "20"), ("last_changed", "Last Changed", ""), ("next_due_hours", "Next Due Hours", "1000"), ("current_hours", "Current Hours", "0"), ("status", "Status", "Normal")],
            },
            "spares": {
                "columns": [("part", "Part", 170), ("equipment_id", "Equip", 70), ("stock", "Stock", 70), ("min_level", "Min", 70), ("location", "Location", 120), ("last_updated", "Updated", 100)],
                "fields": [("part", "Part", "Jaw Plate"), ("equipment_id", "Equipment ID", "JC-01"), ("stock", "Stock", "1"), ("min_level", "Min Level", "1"), ("location", "Location", "Main Store"), ("last_updated", "Updated", self._today())],
            },
            "work_orders": {
                "columns": [("wo_id", "WO ID", 85), ("equipment_id", "Equip", 70), ("task", "Task", 210), ("priority", "Priority", 85), ("due_date", "Due Date", 95), ("status", "Status", 90), ("assigned_to", "Assigned", 110), ("estimated_cost", "Cost", 80)],
                "fields": [("wo_id", "WO ID", self._next_wo_id()), ("equipment_id", "Equipment ID", "JC-01"), ("task", "Task", "PM task"), ("priority", "Priority", "Medium"), ("due_date", "Due Date", self._today()), ("status", "Status", "Open"), ("assigned_to", "Assigned To", "Maintenance Team"), ("estimated_cost", "Estimated Cost", "0")],
            },
        }
        self.specs[key] = specs[key]

        controls = ctk.CTkFrame(tab, fg_color="transparent")
        controls.pack(fill="x", padx=10, pady=(10, 6))
        button_font = ("Segoe UI Semibold", 13)
        ctk.CTkButton(controls, text="Add", width=80, height=34, font=button_font, command=lambda k=key: self._record_add(k)).pack(side="left", padx=(0, 6))
        ctk.CTkButton(controls, text="Edit", width=80, height=34, font=button_font, command=lambda k=key: self._record_edit(k)).pack(side="left", padx=6)
        ctk.CTkButton(controls, text="Delete", width=86, height=34, font=button_font, fg_color="#b91c1c", hover_color="#991b1b", command=lambda k=key: self._record_delete(k)).pack(side="left", padx=6)
        self._attach_custom_buttons(controls, key)

        card = ctk.CTkFrame(tab, fg_color="#0b1220", corner_radius=10)
        card.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        cols = [c[0] for c in self.specs[key]["columns"]]
        tree = ttk.Treeview(card, columns=cols, show="headings", style=self.table_style_name)
        for col, title, width in self.specs[key]["columns"]:
            tree.heading(col, text=title)
            tree.column(col, width=width, anchor="center")
        tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        bar = tk.Scrollbar(card, orient="vertical", command=tree.yview)
        bar.pack(side="right", fill="y", padx=(4, 8), pady=8)
        tree.configure(yscrollcommand=bar.set)
        self.trees[key] = tree

    def _attach_custom_buttons(self, controls, key: str):
        button_font = ("Segoe UI Semibold", 13)
        if key == "pm_schedule":
            ctk.CTkButton(controls, text="Mark Done", width=110, height=34, font=button_font, fg_color="#0f766e", hover_color="#115e59", command=self._pm_mark_done).pack(side="left", padx=6)
            ctk.CTkButton(controls, text="Generate WOs", width=124, height=34, font=button_font, command=self._wo_generate_from_pm).pack(side="left", padx=6)
        elif key == "inspections":
            ctk.CTkButton(controls, text="Seed Jaw/Cone", width=132, height=34, font=button_font, command=self._inspection_seed).pack(side="left", padx=6)
        elif key == "lubrication":
            ctk.CTkButton(controls, text="Log Oil Change", width=134, height=34, font=button_font, command=self._lube_log_change).pack(side="left", padx=6)
        elif key == "spares":
            ctk.CTkButton(controls, text="Adjust Stock", width=122, height=34, font=button_font, command=self._spares_adjust).pack(side="left", padx=6)
        elif key == "work_orders":
            ctk.CTkButton(controls, text="Advance Status", width=126, height=34, font=button_font, command=self._wo_advance).pack(side="left", padx=6)

    def _build_alerts_tab(self, tab):
        controls = ctk.CTkFrame(tab, fg_color="transparent")
        controls.pack(fill="x", padx=10, pady=(10, 6))
        ctk.CTkButton(controls, text="Refresh Alerts", width=136, height=34, font=("Segoe UI Semibold", 13), command=self._refresh_alerts).pack(side="left")
        card = ctk.CTkFrame(tab, fg_color="#0b1220", corner_radius=10)
        card.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.alerts_list = tk.Listbox(card, font=("Segoe UI", 13), bg="#0b1220", fg="#e2e8f0", selectbackground="#1e40af", relief="flat", borderwidth=0, highlightthickness=0)
        self.alerts_list.pack(fill="both", expand=True, padx=10, pady=10)

    def _build_components_tab(self, tab):
        wrap = ctk.CTkFrame(tab, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=10, pady=10)
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_columnconfigure(1, weight=1)
        areas = [("primary_crusher", "Primary Jaw"), ("secondary_crusher", "Secondary Cone"), ("conveyor", "Conveyor"), ("screen", "Screen")]
        for idx, (key, title) in enumerate(areas):
            box = ctk.CTkFrame(wrap, fg_color="#0b1220", corner_radius=10)
            box.grid(row=idx // 2, column=idx % 2, sticky="nsew", padx=6, pady=6)
            wrap.grid_rowconfigure(idx // 2, weight=1)
            ctk.CTkLabel(box, text=title, font=("Segoe UI Semibold", 16), text_color="#e2e8f0").pack(anchor="w", padx=10, pady=(10, 6))
            lb = tk.Listbox(box, height=8, font=("Segoe UI", 13), bg="#0b1220", fg="#e2e8f0", selectbackground="#1e40af", relief="flat", borderwidth=0, highlightthickness=0)
            lb.pack(fill="both", expand=True, padx=10, pady=(0, 8))
            self.component_boxes[key] = lb
            btns = ctk.CTkFrame(box, fg_color="transparent")
            btns.pack(fill="x", padx=10, pady=(0, 10))
            button_font = ("Segoe UI Semibold", 13)
            ctk.CTkButton(btns, text="Add", width=72, height=34, font=button_font, command=lambda k=key: self._component_add(k)).pack(side="left", padx=(0, 6))
            ctk.CTkButton(btns, text="Edit", width=72, height=34, font=button_font, command=lambda k=key: self._component_edit(k)).pack(side="left", padx=6)
            ctk.CTkButton(btns, text="Delete", width=78, height=34, font=button_font, fg_color="#b91c1c", hover_color="#991b1b", command=lambda k=key: self._component_delete(k)).pack(side="left", padx=6)

    def _clear_tree(self, key: str):
        tree = self.trees.get(key)
        if tree is None:
            return
        for iid in tree.get_children():
            tree.delete(iid)

    def _refresh_table(self, key: str):
        tree = self.trees.get(key)
        spec = self.specs.get(key)
        rows = self.state.get(key, [])
        if tree is None or spec is None:
            return
        self._clear_tree(key)
        tree.tag_configure("row_even", background="#0f172a", foreground="#e2e8f0")
        tree.tag_configure("row_odd", background="#111827", foreground="#e2e8f0")
        cols = [c[0] for c in spec["columns"]]
        for idx, row in enumerate(rows):
            if key == "pm_schedule":
                row["status"] = self._task_status(row)
            values = [row.get(col, "") for col in cols]
            row_tag = "row_even" if idx % 2 == 0 else "row_odd"
            tree.insert("", "end", iid=str(idx), values=values, tags=(row_tag,))

    def _refresh_components(self):
        for key, lb in self.component_boxes.items():
            lb.delete(0, "end")
            rows = self.components.get(key, [])
            if not rows:
                lb.insert("end", "No components")
                continue
            for row in rows:
                lb.insert("end", row.get("name", ""))

    def _refresh_alerts(self):
        alerts = self._compute_alerts()
        if self.alerts_list is not None:
            self.alerts_list.delete(0, "end")
            for alert in alerts:
                self.alerts_list.insert("end", alert)

        due_pm = sum(1 for row in self.state.get("pm_schedule", []) if self._task_status(row) in ("Overdue", "Due Soon"))
        open_wo = sum(1 for row in self.state.get("work_orders", []) if str(row.get("status", "")).lower() != "closed")
        if "equipment" in self.kpis:
            self.kpis["equipment"].configure(text=str(len(self.state.get("equipment", []))))
        if "due_pm" in self.kpis:
            self.kpis["due_pm"].configure(text=str(due_pm))
        if "open_wo" in self.kpis:
            self.kpis["open_wo"].configure(text=str(open_wo))
        if "alerts" in self.kpis:
            self.kpis["alerts"].configure(text=str(len(alerts)))

    def _refresh_all(self):
        for key in self.specs:
            self._refresh_table(key)
        self._refresh_components()
        self._refresh_alerts()

    def _record_add(self, key: str):
        spec = self.specs.get(key)
        if spec is None:
            return
        initial = {}
        if key == "work_orders":
            initial["wo_id"] = self._next_wo_id()
            initial["due_date"] = self._today()
            initial["status"] = "Open"
        rec = self._open_form_dialog(f"Add {key}", spec["fields"], initial=initial)
        if not rec:
            return
        self.state.setdefault(key, []).append(rec)
        self._save_state()
        self._refresh_all()

    def _record_edit(self, key: str):
        idx = self._selected_index(key)
        rows = self.state.get(key, [])
        spec = self.specs.get(key)
        if idx is None or idx >= len(rows) or spec is None:
            messagebox.showwarning("Select", "Select a row to edit.")
            return
        rec = self._open_form_dialog(f"Edit {key}", spec["fields"], initial=rows[idx])
        if not rec:
            return
        rows[idx] = rec
        self._save_state()
        self._refresh_all()

    def _record_delete(self, key: str):
        idx = self._selected_index(key)
        rows = self.state.get(key, [])
        if idx is None or idx >= len(rows):
            messagebox.showwarning("Select", "Select a row to delete.")
            return
        if not messagebox.askyesno("Delete", "Delete selected row?"):
            return
        del rows[idx]
        self._save_state()
        self._refresh_all()

    def _pm_mark_done(self):
        idx = self._selected_index("pm_schedule")
        rows = self.state.get("pm_schedule", [])
        if idx is None or idx >= len(rows):
            messagebox.showwarning("Select", "Select PM task to mark done.")
            return
        row = rows[idx]
        today = datetime.now().date()
        row["last_done"] = str(today)
        freq = str(row.get("frequency", "")).lower()
        if "daily" in freq:
            row["next_due"] = str(today + timedelta(days=1))
        elif "weekly" in freq:
            row["next_due"] = str(today + timedelta(days=7))
        elif "monthly" in freq:
            row["next_due"] = str(today + timedelta(days=30))
        if str(row.get("maintenance_type", "")).lower() == "usage":
            row["current_hours"] = "0"
        row["status"] = "Planned"
        self._save_state()
        self._refresh_all()

    def _inspection_seed(self):
        rows = self.state.setdefault("inspections", [])
        today = self._today()
        rows.extend(
            [
                {"date": today, "equipment_id": "JC-01", "parameter": "Feed size uniformity", "status": "OK", "remarks": "No oversized lumps", "inspector": "Auto Seed"},
                {"date": today, "equipment_id": "JC-01", "parameter": "Jaw plate wear", "status": "Watch", "remarks": "Plan replacement on wear limit", "inspector": "Auto Seed"},
                {"date": today, "equipment_id": "CC-01", "parameter": "Oil temperature", "status": "OK", "remarks": "Within operating range", "inspector": "Auto Seed"},
                {"date": today, "equipment_id": "CC-01", "parameter": "Liner wear profile", "status": "Watch", "remarks": "Monitor uneven wear", "inspector": "Auto Seed"},
            ]
        )
        self._save_state()
        self._refresh_all()

    def _lube_log_change(self):
        idx = self._selected_index("lubrication")
        rows = self.state.get("lubrication", [])
        if idx is None or idx >= len(rows):
            messagebox.showwarning("Select", "Select lubrication row to log oil change.")
            return
        rows[idx]["last_changed"] = self._today()
        rows[idx]["current_hours"] = "0"
        rows[idx]["status"] = "Normal"
        self._save_state()
        self._refresh_all()

    def _spares_adjust(self):
        idx = self._selected_index("spares")
        rows = self.state.get("spares", [])
        if idx is None or idx >= len(rows):
            messagebox.showwarning("Select", "Select spare row to adjust stock.")
            return
        dialog = ctk.CTkInputDialog(text="Enter stock adjustment (e.g. -1, +2):", title="Adjust Stock")
        value = dialog.get_input() if dialog else None
        if value is None or str(value).strip() == "":
            return
        delta = int(self._num(value, 0))
        current = int(self._num(rows[idx].get("stock"), 0))
        rows[idx]["stock"] = str(max(0, current + delta))
        rows[idx]["last_updated"] = self._today()
        self._save_state()
        self._refresh_all()

    def _wo_advance(self):
        idx = self._selected_index("work_orders")
        rows = self.state.get("work_orders", [])
        if idx is None or idx >= len(rows):
            messagebox.showwarning("Select", "Select work order to advance status.")
            return
        status = str(rows[idx].get("status", "Open")).lower()
        if status == "open":
            rows[idx]["status"] = "In Progress"
        elif status == "in progress":
            rows[idx]["status"] = "Closed"
        else:
            rows[idx]["status"] = "Closed"
        self._save_state()
        self._refresh_all()

    def _wo_generate_from_pm(self):
        open_set = {(str(r.get("equipment_id", "")), str(r.get("task", ""))) for r in self.state.get("work_orders", []) if str(r.get("status", "")).lower() != "closed"}
        created = 0
        for task in self.state.get("pm_schedule", []):
            status = self._task_status(task)
            key = (str(task.get("equipment_id", "")), str(task.get("task", "")))
            if status not in ("Overdue", "Due Soon") or key in open_set:
                continue
            self.state["work_orders"].append(
                {
                    "wo_id": self._next_wo_id(),
                    "equipment_id": task.get("equipment_id", ""),
                    "task": task.get("task", ""),
                    "priority": "High" if status == "Overdue" else "Medium",
                    "due_date": self._today(),
                    "status": "Open",
                    "assigned_to": task.get("owner", "Maintenance Team"),
                    "estimated_cost": "0",
                }
            )
            open_set.add(key)
            created += 1
        if created == 0:
            messagebox.showinfo("Work Orders", "No new work orders were generated.")
        self._save_state()
        self._refresh_all()

    def _component_selected(self, key: str) -> Optional[int]:
        lb = self.component_boxes.get(key)
        if lb is None:
            return None
        sel = lb.curselection()
        if not sel:
            return None
        idx = int(sel[0])
        return idx if 0 <= idx < len(self.components.get(key, [])) else None

    def _component_add(self, key: str):
        rec = self._open_form_dialog("Add Component", [("name", "Name", "Component"), ("details", "Details", "Notes")], {"name": "", "details": ""})
        if not rec:
            return
        self.components.setdefault(key, []).append(rec)
        self._save_components()
        self._refresh_components()

    def _component_edit(self, key: str):
        idx = self._component_selected(key)
        if idx is None:
            messagebox.showwarning("Select", "Select component to edit.")
            return
        rec = self._open_form_dialog("Edit Component", [("name", "Name", "Component"), ("details", "Details", "Notes")], self.components[key][idx])
        if not rec:
            return
        self.components[key][idx] = rec
        self._save_components()
        self._refresh_components()

    def _component_delete(self, key: str):
        idx = self._component_selected(key)
        if idx is None:
            messagebox.showwarning("Select", "Select component to delete.")
            return
        if not messagebox.askyesno("Delete", "Delete selected component?"):
            return
        del self.components[key][idx]
        self._save_components()
        self._refresh_components()
