import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, filedialog
from typing import List, Dict, Any, Optional, Callable, TYPE_CHECKING
import os
import re
import time
from datetime import datetime, timedelta

if TYPE_CHECKING:
    from customtkinter import CTkFrame
from pathlib import Path
import json
import logging
import csv

try:
    from ..app_paths import data_dir as app_data_dir, data_path, exports_dir
    from ..incident_store import load_incidents
    from ..machine_alert_runner import run_machine_alert_scan
    from ..predictive_layer import rank_machine_risk
    from ..machine_store import (
        evaluate_machine_status,
        effective_machine_status,
        load_machines,
        machine_current_hours,
        machine_due_date,
        machine_service_interval_hours,
        machine_next_due_hours,
        parse_machine_hours,
        save_machines,
    )
    from ..mine_store import get_active_mine, load_mines as load_mine_profiles
    from ..sms_contacts import (
        collect_sms_recipients,
        is_placeholder_sms_phone as _is_placeholder_sms_phone,
        normalize_sms_phone as _normalize_sms_phone,
    )
except Exception:
    from app_paths import data_dir as app_data_dir, data_path, exports_dir
    from incident_store import load_incidents
    from machine_alert_runner import run_machine_alert_scan
    from predictive_layer import rank_machine_risk
    from machine_store import (
        evaluate_machine_status,
        effective_machine_status,
        load_machines,
        machine_current_hours,
        machine_due_date,
        machine_service_interval_hours,
        machine_next_due_hours,
        parse_machine_hours,
        save_machines,
    )
    from mine_store import get_active_mine, load_mines as load_mine_profiles
    from sms_contacts import (
        collect_sms_recipients,
        is_placeholder_sms_phone as _is_placeholder_sms_phone,
        normalize_sms_phone as _normalize_sms_phone,
    )

try:
    from PIL import Image
except ImportError:
    Image = None

from .sidebar import Sidebar
from . import theme as theme_mod
from .gradient import GradientPanel
from .cards import AnimatedCard, MachineCard, StatusIndicator
from api_client import sync_get_operators
from sms_service import default_sms_service
from . import settings as settings_ui
from .scroll import enable_mousewheel_scroll

logger = logging.getLogger(__name__)
SECTION_THEME = getattr(theme_mod, "SECTION_COLORS", {})


def _normalize_ui_mode(mode: Any) -> str:
    val = str(mode or "").strip().lower()
    if val not in ("dark", "light", "system"):
        return "dark"
    return val


def _load_ui_mode_setting() -> str:
    try:
        cfg = settings_ui.load_settings()
        return _normalize_ui_mode(cfg.get("ui_mode", "dark"))
    except Exception:
        return _normalize_ui_mode(os.environ.get("UI_MODE", "dark"))


def _apply_ui_mode(mode: str) -> str:
    mode = _normalize_ui_mode(mode)
    try:
        ctk.set_appearance_mode(mode)
    except Exception:
        pass
    return mode


def schedule_retries(
    ops: List[Dict[str, Any]],
    sms_service: Any,
    message_template: str,
    callback: Optional[Callable[[Dict[str, Any], Dict[str, Any]], None]] = None
) -> None:
    """Schedule retries for a list of operator dicts using provided sms_service.

    - `ops`: list of operator dicts (must include 'phone')
    - `sms_service`: object exposing `send_async(phone, msg, callback=cb)`
    - `message_template`: format string; attempt `message_template.format(**op)` else use template
    - `callback`: optional function(op, result) called when an individual send completes
    """
    for op in ops:
        phone = op.get('phone')
        if not phone:
            if callback:
                callback(op, {'success': False, 'error': 'no phone'})
            continue

        try:
            try:
                msg = message_template.format(**op)
            except Exception:
                msg = message_template

            def _cb_factory(o):
                def _cb(res):
                    try:
                        if callback:
                            callback(o, res)
                    except Exception:
                        pass
                return _cb

            sms_service.send_async(phone, msg, callback=_cb_factory(op))
        except Exception as e:
            if callback:
                try:
                    callback(op, {'success': False, 'error': str(e)})
                except Exception:
                    pass


ctk.set_appearance_mode(_load_ui_mode_setting())
ctk.set_default_color_theme("blue")


class Dashboard(ctk.CTkFrame):
    """Main dashboard frame for the SMS Alert application."""

    def __init__(self, master, user: Dict[str, str]) -> None:
        """Initialize the dashboard.

        Args:
            master: Parent widget.
            user: User information dictionary containing name, role, etc.
        """
        super().__init__(master)
        self.user = user
        self._ui_mode = _apply_ui_mode(_load_ui_mode_setting())

        # Cache for data to avoid repeated API calls
        self._data_cache = {}
        self._cache_timestamp = {}
        # force immediate refresh when other parts of app update machines
        self._cache_timeout = 0  # seconds (0 = always fetch fresh)
        self._mine_card_glow_after_id = None
        self._mine_glow_phase = 0
        self._mine_glow_base = "#1d2a3f"
        self._mine_glow_surface = "#07111d"
        self._mine_glow_accent = "#14b8a6"

        # apply palette background for consistent look
        try:
            self.configure(fg_color=theme_mod.SIMPLE_PALETTE.get('bg', "#1a1a1a"))
        except Exception:
            pass

        # Layout configuration
        self.grid_columnconfigure(0, minsize=220)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Sidebar
        self.sidebar_scrollable = ctk.CTkScrollableFrame(
            self,
            width=220,
            corner_radius=0,
            fg_color="#08101d",
            scrollbar_button_color="#334155",
            scrollbar_button_hover_color="#475569",
        )
        self.sidebar = Sidebar(self.sidebar_scrollable, dashboard=self)
        # Keep natural content height so sidebar overflow remains scrollable.
        self.sidebar.pack(fill="both", expand=True, anchor="n")
        self.sidebar_scrollable.grid(row=0, column=0, sticky="nsew")
        try:
            enable_mousewheel_scroll(self.sidebar_scrollable)
        except Exception:
            pass

        # Main area - use a scrollable frame so long dashboards can scroll
        try:
            # customtkinter provides a CTkScrollableFrame which is ideal here
            self.main_frame = ctk.CTkScrollableFrame(
                self,
                corner_radius=0,
                fg_color="#081520",
                scrollbar_button_color="#334155",
                scrollbar_button_hover_color="#475569",
            )
        except Exception:
            # Fallback to a normal frame if CTkScrollableFrame isn't available
            self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="#081520")
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        try:
            enable_mousewheel_scroll(self.main_frame)
        except Exception:
            pass

        # Content frames
        self.content_frames: Dict[str, ctk.CTkFrame] = {}
        self.current_content: Optional[str] = None

        # Create only dashboard content now; other content is lazy-loaded on demand
        self.create_dashboard_content()

        # Mine setup is handled before dashboard entry, so the dashboard always opens directly here.
        initial_content = "dashboard"
        self.show_content(initial_content)
        try:
            if hasattr(self, "sidebar") and self.sidebar is not None:
                self.sidebar._activate_by_name("Dashboard")
        except Exception:
            pass

        # Load data immediately (should be fast with timeouts)
        self._load_initial_data()
        # Start periodic refresh (every 30s) to keep cards up-to-date
        try:
            self._start_periodic_refresh(30)
        except Exception:
            pass
        try:
            self._start_background_automation()
        except Exception:
            logger.exception("Failed to start dashboard automation")

    def _apply_dark_treeview_style(self, style_name: str, heading_style: Optional[str] = None) -> str:
        """Create a reusable dark Treeview style for worksheet-style tables."""
        heading_style = heading_style or f"{style_name}.Heading"
        try:
            style = ttk.Style(self)
            try:
                style.theme_use("clam")
            except Exception:
                pass
            style.configure(
                style_name,
                font=("Segoe UI", 12),
                rowheight=36,
                background="#0f172a",
                fieldbackground="#0f172a",
                foreground="#e2e8f0",
                borderwidth=0,
                relief="flat",
            )
            style.configure(
                heading_style,
                font=("Segoe UI Semibold", 12),
                background="#111827",
                foreground="#cbd5e1",
                borderwidth=0,
                relief="flat",
                padding=(8, 8),
            )
            style.map(
                style_name,
                background=[("selected", "#1d4ed8")],
                foreground=[("selected", "#f8fafc")],
            )
            style.map(
                heading_style,
                background=[("active", "#1f2937")],
                foreground=[("active", "#f8fafc")],
            )
        except Exception:
            pass
        return style_name

    def _apply_dark_combobox_style(self, style_name: str = "Worksheet.TCombobox") -> str:
        try:
            style = ttk.Style(self)
            try:
                style.theme_use("clam")
            except Exception:
                pass
            style.configure(
                style_name,
                fieldbackground="#0f172a",
                background="#0f172a",
                foreground="#e2e8f0",
                arrowcolor="#cbd5e1",
                bordercolor="#1f2937",
                lightcolor="#1f2937",
                darkcolor="#1f2937",
                insertcolor="#f8fafc",
                padding=8,
            )
            style.map(
                style_name,
                fieldbackground=[("readonly", "#0f172a")],
                background=[("readonly", "#0f172a")],
                foreground=[("readonly", "#e2e8f0")],
                selectbackground=[("readonly", "#1d4ed8")],
                selectforeground=[("readonly", "#f8fafc")],
            )
        except Exception:
            pass
        return style_name

    def _load_initial_data(self) -> None:
        """Load initial data - show UI immediately with cached/empty data, then refresh in background."""
        # Show UI immediately with empty data
        self._update_ui_with_data([])

        # Then load real data in background
        self.after(100, self._load_data_async)

    def _start_periodic_refresh(self, interval_sec: int = 30) -> None:
        """Start a periodic refresh calling `refresh_ui()` every `interval_sec` seconds."""
        def _tick():
            try:
                # refresh in background
                self.refresh_ui()
            except Exception:
                pass
            try:
                # schedule next
                if getattr(self, 'winfo_exists', lambda: True)():
                    self._refresh_after_id = self.after(int(interval_sec * 1000), _tick)
            except Exception:
                pass

        try:
            self._refresh_after_id = self.after(int(interval_sec * 1000), _tick)
        except Exception:
            pass

    def _start_background_automation(self) -> None:
        try:
            self.start_hour_task_scheduler()
        except Exception:
            logger.exception("Failed to start automatic task generation")
        try:
            cfg = settings_ui.load_settings()
            should_run_bg_scan = any(
                bool(cfg.get(flag, False))
                for flag in (
                    "auto_machine_alerts",
                    "auto_work_order_generation",
                    "auto_spare_reorder_alerts",
                    "auto_maintenance_followup_reminders",
                    "checklist_missed_alerts_enabled",
                    "rule_engine_enabled",
                    "predictive_layer_enabled",
                    "auto_report_delivery_enabled",
                )
            )
            if should_run_bg_scan:
                interval_minutes = int(cfg.get("machine_alert_interval_minutes", 5) or 5)
                self.start_machine_alert_scheduler(interval_minutes=interval_minutes)
        except Exception:
            logger.exception("Failed to start automatic machine alert scheduler")

    def _load_data_async(self) -> None:
        """Load data asynchronously for refresh operations."""
        import threading

        def load_data():
            try:
                machines = self._get_cached_data('machines', self._load_user_machines) or []
                # Update UI on main thread
                self.after(0, lambda: self._update_ui_with_data(machines))
            except Exception:
                pass

        # Start background loading
        thread = threading.Thread(target=load_data, daemon=True)
        thread.start()

    def _get_cached_data(self, key: str, fetch_func: Callable[[], List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """Get data from cache or fetch fresh data."""
        import time

        current_time = time.time()
        if key in self._cache_timestamp and (current_time - self._cache_timestamp[key]) < self._cache_timeout:
            return self._data_cache.get(key, [])

        # Fetch fresh data
        data = fetch_func()
        self._data_cache[key] = data
        self._cache_timestamp[key] = current_time
        return data

    def _load_user_machines(self) -> List[Dict[str, Any]]:
        """Read machines only from the shared user-managed machine store."""
        try:
            rows = load_machines() or []
            return [dict(row) for row in rows if isinstance(row, dict)]
        except Exception:
            logger.exception("Failed to load user machine store")
            return []

    def _load_mine_profiles(self) -> List[Dict[str, Any]]:
        try:
            rows = load_mine_profiles() or []
            return [dict(row) for row in rows if isinstance(row, dict)]
        except Exception:
            logger.exception("Failed to load mine profiles")
            return []

    def _has_configured_mine(self) -> bool:
        return bool(self._load_mine_profiles())

    def get_active_mine_profile(self) -> Optional[Dict[str, Any]]:
        try:
            mine = get_active_mine()
            if isinstance(mine, dict) and mine:
                return dict(mine)
        except Exception:
            logger.exception("Failed to read active mine profile")
        return None

    def _update_ui_with_data(self, machines: List[Dict[str, Any]]) -> None:
        """Update UI with loaded data."""
        self.machines = machines

        # Update stats cards
        try:
            stats = self.compute_stats(machines)
            if hasattr(self, 'card_total'):
                self.card_total.value_label.configure(text=str(stats['total']))
                try:
                    self.card_total.hide_spinner()
                except Exception:
                    pass
            if hasattr(self, 'card_critical'):
                self.card_critical.value_label.configure(text=str(stats['critical']))
                try:
                    self.card_critical.hide_spinner()
                except Exception:
                    pass
            if hasattr(self, 'card_due'):
                self.card_due.value_label.configure(text=str(stats['due']))
                try:
                    self.card_due.hide_spinner()
                except Exception:
                    pass
            if hasattr(self, 'card_overdue'):
                self.card_overdue.value_label.configure(text=str(stats['overdue']))
                try:
                    self.card_overdue.hide_spinner()
                except Exception:
                    pass
        except Exception:
            # If stats computation fails, show error state
            try:
                if hasattr(self, 'card_total'):
                    self.card_total.value_label.configure(text="Error")
                    try:
                        self.card_total.hide_spinner()
                    except Exception:
                        pass
                if hasattr(self, 'card_critical'):
                    self.card_critical.value_label.configure(text="Error")
                    try:
                        self.card_critical.hide_spinner()
                    except Exception:
                        pass
                if hasattr(self, 'card_due'):
                    self.card_due.value_label.configure(text="Error")
                    try:
                        self.card_due.hide_spinner()
                    except Exception:
                        pass
                if hasattr(self, 'card_overdue'):
                    self.card_overdue.value_label.configure(text="Error")
                    try:
                        self.card_overdue.hide_spinner()
                    except Exception:
                        pass
            except Exception:
                pass

        # machine overview removed; no machine list to update

    def show_content(self, content_name: str) -> None:
        """Switch to the specified content frame."""
        # Hide current content
        if self.current_content == "dashboard" and content_name != "dashboard":
            self._stop_mine_card_glow()
        if self.current_content and self.current_content in self.content_frames:
            self.content_frames[self.current_content].pack_forget()

        # Show new content
        # If content hasn't been created yet, try to create it lazily by calling
        # a `create_{name}_content` method if present. This avoids heavy upfront
        # work which causes a UI freeze after login.
        if content_name not in self.content_frames:
            creator_name = f"create_{content_name}_content"
            creator = getattr(self, creator_name, None)
            if callable(creator):
                try:
                    creator()
                except Exception:
                    pass
            else:
                logger.warning("No content creator found for '%s'", content_name)

        if content_name not in self.content_frames:
            # Avoid silent no-op when a sidebar item points to unknown content.
            placeholder = ctk.CTkFrame(self.main_frame, fg_color="transparent")
            self.content_frames[content_name] = placeholder
            msg = ctk.CTkLabel(
                placeholder,
                text=f"'{content_name}' view is not available yet.",
                font=("Segoe UI Semibold", 18),
                text_color="#f8fafc",
            )
            msg.pack(padx=24, pady=(24, 8), anchor="w")
            hint = ctk.CTkLabel(
                placeholder,
                text="Please contact support or refresh the app.",
                font=("Segoe UI", 13),
                text_color="#94a3b8",
            )
            hint.pack(padx=24, pady=(0, 24), anchor="w")

        if content_name in self.content_frames:
            try:
                self._apply_section_theme(content_name)
            except Exception:
                pass
            self.content_frames[content_name].pack(fill="both", expand=True)
            self.current_content = content_name

            # Refresh dashboard data when showing it
            if content_name == "dashboard":
                # Ensure heavy dashboard components are loaded lazily
                try:
                    if not getattr(self, '_modern_loaded', False):
                        # load in main thread to keep UI consistent
                        self.create_modern_dashboard_components(self.modern_container)
                        self._modern_loaded = True
                except Exception:
                    pass
                self._restart_mine_card_glow()
                self.refresh_ui()

            # Lazy-load reports when their tab is shown
            if content_name == 'reports':
                try:
                    if not getattr(self, '_reports_loaded', False):
                        self._ensure_reports_loaded()
                        self._reports_loaded = True
                except Exception:
                    pass

            if content_name == "mine_details":
                try:
                    if hasattr(self, "mine_details_ui") and self.mine_details_ui is not None:
                        self.mine_details_ui.refresh()
                except Exception:
                    pass

    def create_dashboard_content(self) -> None:
        """Create the dashboard content frame."""
        frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.content_frames["dashboard"] = frame

        # Create dashboard widgets inside this frame
        self.create_header(frame)
        self.create_cards(frame)
        # Create a placeholder container for modern components and lazy-load heavy charts
        self.modern_container = ctk.CTkFrame(frame, fg_color="transparent")
        self.modern_container.pack(fill="x", padx=20, pady=(10, 20))
        self._modern_loaded = False
        self.create_bwe_status(frame)  # This line remains unchanged
        # machine overview removed per request
        self.create_sms_controls(frame)
        # Add audit view (lazy-loaded)
        # `create_audit_content` will be called when user navigates to 'audit'
        # so we don't fetch DB data until requested.

    def create_machines_content(self) -> None:
        """Create the machines management content frame."""
        import logging
        logging.getLogger(__name__).info("Dashboard.create_machines_content called")
        from .machines import MachinesFrame
        frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.content_frames["machines"] = frame

        # Create machines management UI inside this frame and pass dashboard reference
        machines_ui = MachinesFrame(frame, dashboard=self)
        machines_ui.pack(fill="both", expand=True)
        self.machines_ui = machines_ui

    def create_mine_details_content(self) -> None:
        """Create mine details management content frame."""
        from .mine_details import MineDetailsFrame

        frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.content_frames["mine_details"] = frame

        mine_ui = MineDetailsFrame(frame, dashboard=self)
        mine_ui.pack(fill="both", expand=True)
        self.mine_details_ui = mine_ui

    def create_operators_content(self) -> None:
        """Create the operators management content frame."""
        from .operators import OperatorsFrame
        frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.content_frames["operators"] = frame

        # Create operators management UI inside this frame and pass dashboard for role checks
        operators_ui = OperatorsFrame(frame)
        # ensure dashboard reference exists on the operators UI for permission checks
        try:
            operators_ui.dashboard = self
        except Exception:
            pass
        operators_ui.pack(fill="both", expand=True)

    def create_alerts_content(self) -> None:
        """Create the alerts content frame."""
        from .alerts import AlertsFrame
        frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.content_frames["alerts"] = frame

        # Create alerts UI inside this frame and attach dashboard reference
        alerts_ui = AlertsFrame(frame, dashboard=self)
        alerts_ui.pack(fill="both", expand=True)

    def create_schedules_content(self) -> None:
        """Create the schedules content frame."""
        from .schedules import SchedulesFrame
        frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.content_frames["schedules"] = frame

        # Create schedules UI inside this frame
        schedules_ui = SchedulesFrame(frame)
        schedules_ui.pack(fill="both", expand=True)

    def create_parts_content(self) -> None:
        """Create parts / wear items management content frame."""
        from .parts import PartsFrame

        frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.content_frames["parts"] = frame

        parts_ui = PartsFrame(frame)
        try:
            parts_ui.dashboard = self
        except Exception:
            pass
        parts_ui.pack(fill="both", expand=True)

    def create_checklist_content(self) -> None:
        """Create daily checklist content frame."""
        from .checklist import ChecklistFrame

        frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.content_frames["checklist"] = frame

        checklist_ui = ChecklistFrame(frame)
        checklist_ui.pack(fill="both", expand=True)

    def create_operator_records_content(self) -> None:
        """Create operator records content frame."""
        from .operator_records import OperatorRecordsFrame

        frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.content_frames["operator_records"] = frame

        ops_ui = OperatorRecordsFrame(frame)
        ops_ui.pack(fill="both", expand=True)

    def create_audit_content(self) -> None:
        """Create a simple SMS audit viewer with export button."""
        frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.content_frames["audit"] = frame

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", pady=(0,8), padx=20)
        title = ctk.CTkLabel(header, text="SMS Audit", font=("Segoe UI Semibold", 20), text_color="#f8fafc")
        title.pack(side="left")

        controls = ctk.CTkFrame(header, fg_color="transparent")
        controls.pack(side="right")

        self._audit_to_var = tk.StringVar(value="")
        self._audit_provider_var = tk.StringVar(value="")
        to_entry = ctk.CTkEntry(controls, placeholder_text="to number", width=160, textvariable=self._audit_to_var)
        to_entry.pack(side="left", padx=(0,6))
        prov_entry = ctk.CTkEntry(controls, placeholder_text="provider", width=120, textvariable=self._audit_provider_var)
        prov_entry.pack(side="left", padx=(0,6))
        load_btn = ctk.CTkButton(controls, text="Load", width=80, command=lambda: self._load_audit_page(1))
        load_btn.pack(side="left", padx=(0,6))
        export_btn = ctk.CTkButton(controls, text="Export", width=80, command=self._export_audit_stream)
        export_btn.pack(side="left")

        container = ctk.CTkFrame(frame, fg_color=theme_mod.SIMPLE_PALETTE.get('card', 'transparent'))
        container.pack(fill="both", expand=True, padx=20, pady=10)

        # List area with pagination
        list_frame = ctk.CTkFrame(container, fg_color="transparent")
        list_frame.pack(fill="both", expand=True)
        self._audit_listbox = tk.Listbox(list_frame, height=12)
        self._audit_listbox.pack(fill="both", expand=True)

        pager = ctk.CTkFrame(container, fg_color="transparent")
        pager.pack(fill="x", pady=(8,0))
        self._audit_page = 1
        self._audit_per_page = 50
        self._audit_page_label = ctk.CTkLabel(pager, text="Page 1")
        prev_btn = ctk.CTkButton(pager, text="Prev", width=80, command=lambda: self._load_audit_page(self._audit_page - 1))
        next_btn = ctk.CTkButton(pager, text="Next", width=80, command=lambda: self._load_audit_page(self._audit_page + 1))
        prev_btn.pack(side="left", padx=6)
        self._audit_page_label.pack(side="left", padx=6)
        next_btn.pack(side="left", padx=6)

        # Load first page
        self._load_audit_page(1)

    def _export_audit_csv(self):
        # Deprecated: kept for compatibility; prefer streaming export via API
        try:
            self._export_audit_stream()
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror('Export failed', str(e))

    def _load_audit_page(self, page: int = 1):
        try:
            import requests
            host = f"http://{os.getenv('API_HOST', '127.0.0.1')}:{os.getenv('API_PORT', os.getenv('PORT', '8000'))}"
            params = {
                'to_number': self._audit_to_var.get() or None,
                'provider': self._audit_provider_var.get() or None,
                'page': page,
                'per_page': self._audit_per_page
            }
            headers = {}
            sk = os.getenv('SERVER_API_KEY')
            if sk:
                headers['X-API-KEY'] = sk
            resp = requests.get(f"{host}/api/v1/audit", params={k: v for k, v in params.items() if v}, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get('items', []) if isinstance(data, dict) else data
                self._audit_listbox.delete(0, 'end')
                for it in items:
                    line = f"{it.get('created_at','')} | {it.get('to','')} | {it.get('provider','')} | {'OK' if it.get('success') else 'FAIL'}"
                    self._audit_listbox.insert('end', line)
                self._audit_page = int(data.get('page', page)) if isinstance(data, dict) else page
                self._audit_page_label.configure(text=f"Page {self._audit_page}")
            else:
                self._audit_listbox.delete(0, 'end')
                self._audit_listbox.insert('end', f"API error {resp.status_code}")
        except Exception:
            try:
                self._audit_listbox.delete(0, 'end')
                self._audit_listbox.insert('end', 'Failed to load audit (API/local DB may be unavailable)')
            except Exception:
                pass

    def _export_audit_stream(self):
        try:
            import requests
            host = f"http://{os.getenv('API_HOST', '127.0.0.1')}:{os.getenv('API_PORT', os.getenv('PORT', '8000'))}"
            params = {}
            to_number = getattr(self, '_audit_to_var', None) and self._audit_to_var.get()
            provider = getattr(self, '_audit_provider_var', None) and self._audit_provider_var.get()
            if to_number:
                params['to_number'] = to_number
            if provider:
                params['provider'] = provider
            headers = {}
            sk = os.getenv('SERVER_API_KEY')
            if sk:
                headers['X-API-KEY'] = sk

            resp = requests.get(f"{host}/api/v1/audit/export", params=params, headers=headers, stream=True, timeout=30)
            if resp.status_code == 200:
                p = exports_dir()
                p.mkdir(parents=True, exist_ok=True)
                fn = p / f"sms_audit_stream_{int(time.time())}.csv"
                with open(fn, 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                from tkinter import messagebox
                messagebox.showinfo('Export', f'Exported audit to {fn}')
            else:
                from tkinter import messagebox
                messagebox.showerror('Export failed', f'API error {resp.status_code}')
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror('Export failed', str(e))

    def create_scheduler_content(self) -> None:
        """Create preventive maintenance scheduler content frame."""
        from .scheduler import SchedulerFrame
        frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.content_frames["scheduler"] = frame

        sched_ui = SchedulerFrame(frame, dashboard=self)
        sched_ui.pack(fill="both", expand=True)
        # Keep reference so generated tasks can refresh the scheduler view
        self.scheduler_ui = sched_ui

    def generate_hour_based_tasks(self, threshold_hours: float = 100.0) -> None:
        """Generate maintenance tasks based on current hour readings and service intervals.

        - Reads machine list (API or local Excel) and finds hour-based service intervals
        - Creates tasks with `due_at_hours = current_hours + interval`
        - Persists tasks to `data/maintenance_tasks.json` used by the scheduler
        """
        try:
            local_data_dir = app_data_dir()
            local_data_dir.mkdir(parents=True, exist_ok=True)
            tasks_path = local_data_dir / "maintenance_tasks.json"

            # Load existing tasks
            existing = []
            try:
                if tasks_path.exists():
                    with open(tasks_path, 'r', encoding='utf-8') as f:
                        existing = json.load(f) or []
            except Exception:
                existing = []

            try:
                machines = self._load_user_machines()
            except Exception:
                machines = load_machines()

            new_tasks = []
            for m in machines:
                # robust current hour lookup
                cur_keys = ['current_hours', 'hour_reading', 'operating_hours', 'hours', 'meter']
                current = None
                for k in cur_keys:
                    try:
                        if k in m and m[k] is not None and str(m[k]).strip() != "":
                            current = float(m[k])
                            break
                    except Exception:
                        continue

                # service intervals may be provided as a dict under 'service_intervals'
                intervals = {}
                try:
                    if isinstance(m.get('service_intervals'), dict):
                        intervals = m.get('service_intervals')
                    else:
                        # scan for keys ending with '_interval'
                        for kk, vv in list(m.items()):
                            if kk.endswith('_interval'):
                                name = kk.replace('_interval', '')
                                try:
                                    intervals[name] = float(vv)
                                except Exception:
                                    pass
                except Exception:
                    intervals = {}

                if not intervals:
                    # common heuristic fields
                    common = {
                        'engine_oil': m.get('engine_oil_interval'),
                        'hydraulic_oil': m.get('hydraulic_oil_interval'),
                        'gearbox_oil': m.get('gearbox_oil_interval'),
                        'air_filter': m.get('air_filter_interval'),
                        'generator_oil': m.get('generator_oil_interval'),
                        'coolant': m.get('coolant_interval')
                    }
                    for kk, vv in common.items():
                        try:
                            if vv:
                                intervals[kk] = float(vv)
                        except Exception:
                            pass

                if not intervals or current is None:
                    # cannot generate hour-based tasks without both interval and current reading
                    continue

                machine_id = str(m.get('id') or m.get('name') or m.get('machine_id') or '')
                machine_name = str(m.get('name') or m.get('id') or '')

                for item, interval in intervals.items():
                    try:
                        interval_f = float(interval)
                    except Exception:
                        continue
                    due_at = current + interval_f

                    subj = f"{item.replace('_',' ').title()} service for {machine_name or machine_id}"

                    # detect duplicates: subject + machine_id +/- 1 hour
                    dup = False
                    for ex in existing:
                        try:
                            if ex.get('machine_id') == machine_id and ex.get('subject') == subj:
                                # if due_at close, skip
                                if abs(float(ex.get('due_at_hours', 0)) - due_at) < 1.0:
                                    dup = True
                                    break
                        except Exception:
                            continue

                    if dup:
                        continue

                    task = {
                        'subject': subj,
                        'machine_id': machine_id,
                        'due_at_hours': due_at,
                        'status': 'pending',
                        'notes': f"Interval: {interval_f} hrs; current_hours: {current}"
                    }
                    new_tasks.append(task)

            if new_tasks:
                merged = existing + new_tasks
                try:
                    with open(tasks_path, 'w', encoding='utf-8') as f:
                        json.dump(merged, f, indent=2)
                except Exception:
                    pass

                # if scheduler UI present, ask it to refresh (best-effort)
                try:
                    if getattr(self, 'scheduler_ui', None):
                        try:
                            self.scheduler_ui._load()
                            self.scheduler_ui._refresh()
                        except Exception:
                            pass
                except Exception:
                    pass

        except Exception:
            logger.exception('Failed to generate hour-based tasks')

    def start_hour_task_scheduler(self, interval_hours: float = 6.0) -> None:
        """Start periodic generation of hour-based tasks every `interval_hours` hours."""
        try:
            self.stop_hour_task_scheduler()
            self._task_scheduler_interval = float(interval_hours)
            self._task_scheduler_running = True

            def _tick():
                try:
                    self.generate_hour_based_tasks()
                finally:
                    try:
                        if getattr(self, '_task_scheduler_running', False):
                            ms = int(self._task_scheduler_interval * 3600 * 1000)
                            self._task_scheduler_after_id = self.after(ms, _tick)
                    except Exception:
                        # fallback schedule in 1 minute
                        try:
                            self._task_scheduler_after_id = self.after(60*1000, _tick)
                        except Exception:
                            pass

            # schedule first tick immediately
            try:
                self._task_scheduler_after_id = self.after(10, _tick)
            except Exception:
                _tick()
        except Exception:
            logger.exception('Failed to start task scheduler')

    def stop_hour_task_scheduler(self) -> None:
        try:
            self._task_scheduler_running = False
            if getattr(self, '_task_scheduler_after_id', None):
                try:
                    self.after_cancel(self._task_scheduler_after_id)
                except Exception:
                    pass
                self._task_scheduler_after_id = None
        except Exception:
            pass

    def _run_machine_alert_scan(self) -> None:
        try:
            machines = getattr(self, "machines", None) or self._load_user_machines()
            summary_data = run_machine_alert_scan(
                machines=machines,
                sms_service=default_sms_service,
                settings=settings_ui.load_settings(),
                fallback_recipients=self._resolve_sms_operators(),
            )

            if summary_data.get("skipped"):
                reason = str(summary_data.get("reason") or "skipped").replace("_", " ")
                summary = f"SMS Status: Background alerts skipped ({reason})"
            else:
                summary = (
                    f"SMS Status: Auto alerts sent for {summary_data.get('machine_sent', 0)} machine(s), "
                    f"{summary_data.get('sms_sent', 0)} SMS, {summary_data.get('failures', 0)} failed, "
                    f"pending:{summary_data.get('pending', 0)} "
                    f"WO:{summary_data.get('work_orders_created', 0)}"
                )

            if summary_data.get("machine_sent") or summary_data.get("failures") or summary_data.get("skipped"):
                try:
                    self.after(0, lambda: getattr(self, "sms_status_label", None) and self.sms_status_label.configure(text=summary))
                except Exception:
                    pass
        except Exception:
            logger.exception("Automatic machine alert scan failed")
        finally:
            self._auto_machine_alert_check_running = False

    def _launch_machine_alert_scan(self) -> None:
        if getattr(self, "_auto_machine_alert_check_running", False):
            return
        self._auto_machine_alert_check_running = True
        import threading
        threading.Thread(target=self._run_machine_alert_scan, daemon=True).start()

    def start_machine_alert_scheduler(self, interval_minutes: float = 5.0) -> None:
        try:
            self.stop_machine_alert_scheduler()
            self._machine_alert_interval_minutes = max(1.0, float(interval_minutes))
            self._machine_alert_scheduler_running = True

            def _tick():
                try:
                    self._launch_machine_alert_scan()
                finally:
                    if getattr(self, "_machine_alert_scheduler_running", False):
                        ms = int(self._machine_alert_interval_minutes * 60 * 1000)
                        self._machine_alert_after_id = self.after(ms, _tick)

            self._machine_alert_after_id = self.after(1500, _tick)
        except Exception:
            logger.exception("Failed to start machine alert scheduler")

    def stop_machine_alert_scheduler(self) -> None:
        try:
            self._machine_alert_scheduler_running = False
            if getattr(self, "_machine_alert_after_id", None):
                try:
                    self.after_cancel(self._machine_alert_after_id)
                except Exception:
                    pass
                self._machine_alert_after_id = None
        except Exception:
            pass

    def create_reports_content(self) -> None:
        """Create the reports content frame."""
        # Lazy-load reports: create placeholder, load on demand
        frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.content_frames["reports"] = frame
        placeholder = ctk.CTkFrame(frame, fg_color="transparent")
        placeholder.pack(fill="both", expand=True, padx=20, pady=20)
        lbl = ctk.CTkLabel(placeholder, text="Reports are ready to load", font=("Segoe UI", 14), text_color="#94a3b8")
        lbl.pack()

    def create_maintenance_history_content(self) -> None:
        """Create the maintenance history workspace."""
        from .maintenance_history import MaintenanceHistoryFrame

        frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.content_frames["maintenance_history"] = frame
        history_ui = MaintenanceHistoryFrame(frame, dashboard=self)
        history_ui.pack(fill="both", expand=True)
        self.maintenance_history_ui = history_ui

    def create_settings_content(self) -> None:
        """Create settings content inside the main app workspace."""
        from .settings import SettingsFrame

        frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.content_frames["settings"] = frame

        settings_ui_frame = SettingsFrame(frame, dashboard=self)
        settings_ui_frame.pack(fill="both", expand=True)

    def create_rule_engine_content(self) -> None:
        """Create visual rule engine editor inside the main app workspace."""
        from .rule_engine import RuleEngineFrame

        frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.content_frames["rule_engine"] = frame

        rule_ui = RuleEngineFrame(frame, dashboard=self)
        rule_ui.pack(fill="both", expand=True)

    def create_admin_content(self) -> None:
        """Lazy-load admin management UI (users & roles)."""
        try:
            from .admin import AdminFrame
            frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
            self.content_frames["admin"] = frame
            admin_ui = AdminFrame(frame, dashboard=self)
            admin_ui.pack(fill="both", expand=True)
        except Exception:
            # If admin UI cannot be loaded (missing deps), create placeholder
            frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
            self.content_frames["admin"] = frame
            lbl = ctk.CTkLabel(frame, text="Admin UI unavailable", font=("Segoe UI Semibold", 16), text_color="#f8fafc")
            lbl.pack(padx=20, pady=20)

    def create_plant_maintenance_content(self) -> None:
        """Create preventive maintenance CMMS-like workspace."""
        from .plant_maintenance import PlantMaintenanceFrame

        frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.content_frames["plant_maintenance"] = frame
        plant_ui = PlantMaintenanceFrame(frame)
        plant_ui.pack(fill="both", expand=True)

    def _hour_data_path(self) -> "Path":
        try:
            local_data_dir = app_data_dir()
            local_data_dir.mkdir(parents=True, exist_ok=True)
            return local_data_dir / "hour_entries.json"
        except Exception:
            return Path("hour_entries.json")

    def _resolve_hour_entry_machine(self, selected_value: str) -> Optional[Dict[str, Any]]:
        selected = str(selected_value or "").strip()
        if not selected or selected == "(No machines loaded)":
            return None
        machine_id = selected.split(" - ", 1)[0].strip()
        for machine in self._load_user_machines():
            machine_mid = str(machine.get("id") or "").strip()
            machine_name = str(machine.get("name") or "").strip()
            if selected == machine_mid or selected == machine_name:
                return dict(machine)
            if machine_mid and (selected.startswith(f"{machine_mid} -") or machine_id == machine_mid):
                return dict(machine)
        return None

    def _sync_machine_runtime_from_hour_entry(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        selected_machine = str(entry.get("machine") or "").strip()
        machine = None
        entry_machine_id = str(entry.get("machine_id") or "").strip()
        if entry_machine_id:
            for row in self._load_user_machines():
                if str(row.get("id") or "").strip() == entry_machine_id:
                    machine = dict(row)
                    break
        if machine is None:
            machine = self._resolve_hour_entry_machine(selected_machine)
        if not machine:
            return {"success": False, "reason": "machine_not_found"}

        machines = load_machines(include_archived=True)
        target_index = None
        target_id = str(machine.get("id") or "").strip()
        for idx, row in enumerate(machines):
            if str(row.get("id") or "").strip() == target_id:
                target_index = idx
                break
        if target_index is None:
            return {"success": False, "reason": "machine_not_found"}

        current_hours = machine_current_hours(machine) or 0.0
        reading = parse_machine_hours(entry.get("hour_reading"))
        runtime_delta = parse_machine_hours(entry.get("per_day_hours")) or 0.0
        updated_hours = reading if reading is not None else current_hours + runtime_delta

        row = dict(machines[target_index])
        row["hours"] = round(updated_hours, 2)
        row["current_hours"] = round(updated_hours, 2)
        row["last_hour_entry_at"] = datetime.now().isoformat(timespec="seconds")
        row["last_runtime_hours"] = round(runtime_delta, 2)
        if reading is not None:
            row["last_hour_reading"] = round(reading, 2)

        interval_hours = machine_service_interval_hours(row)
        next_due_hours = machine_next_due_hours(row)
        if interval_hours is not None and next_due_hours is None:
            row["next_due_hours"] = round(updated_hours + interval_hours, 2)

        machines[target_index] = row
        save_machines(machines)

        try:
            self._data_cache.pop("machines", None)
            self._cache_timestamp.pop("machines", None)
        except Exception:
            pass
        try:
            self.machines = self._load_user_machines()
        except Exception:
            pass
        try:
            self.refresh_ui()
        except Exception:
            pass

        return {
            "success": True,
            "machine_id": target_id,
            "hours": round(updated_hours, 2),
            "next_due_hours": row.get("next_due_hours"),
        }

    def _save_hour_entry(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "local_saved": False,
            "api_saved": False,
            "pm_runtime_synced": False,
            "pm_sync": {},
            "machine_runtime_synced": False,
            "machine_sync": {},
        }
        try:
            p = self._hour_data_path()
            existing = []
            if p.exists():
                try:
                    with open(p, 'r', encoding='utf-8') as f:
                        existing = json.load(f) or []
                except Exception:
                    existing = []
            existing.append(entry)
            with open(p, 'w', encoding='utf-8') as f:
                json.dump(existing, f, indent=2)
            result["local_saved"] = True
        except Exception:
            logger.exception('Failed to save hour entry')
        # Best-effort: push to API
        try:
            from api_client import sync_create_hour_entry
            try:
                sync_create_hour_entry(entry)
                result["api_saved"] = True
            except Exception:
                pass
        except Exception:
            pass
        try:
            machine_sync = self._sync_machine_runtime_from_hour_entry(entry)
            result["machine_sync"] = machine_sync or {}
            result["machine_runtime_synced"] = bool((machine_sync or {}).get("success"))
        except Exception:
            logger.exception("Failed to sync machine runtime from hour entry")
        # Best-effort: sync runtime counters into Plant Maintenance state.
        try:
            from .plant_maintenance import sync_runtime_from_hour_entry

            sync_out = sync_runtime_from_hour_entry(entry)
            result["pm_sync"] = sync_out or {}
            result["pm_runtime_synced"] = bool((sync_out or {}).get("success"))

            # If Plant Maintenance screen is already created, refresh it immediately.
            try:
                pm_frame = self.content_frames.get("plant_maintenance")
                if pm_frame is not None:
                    for child in pm_frame.winfo_children():
                        if hasattr(child, "_refresh_all"):
                            try:
                                child._refresh_all()
                            except Exception:
                                pass
            except Exception:
                pass
        except Exception:
            pass
        return result
    def create_hour_entry_content(self) -> None:
        """Create a modern worksheet-style UI for machine hour entry."""
        frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.content_frames["hour_entry"] = frame

        worksheet_tree_style = self._apply_dark_treeview_style("Worksheet.Treeview")
        worksheet_combo_style = self._apply_dark_combobox_style("Worksheet.TCombobox")

        container = ctk.CTkFrame(frame, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=20)

        card_color = theme_mod.SIMPLE_PALETTE.get("card", "#111827")
        title_color = "#f8fafc"
        subtitle_color = "#94a3b8"

        header_card = ctk.CTkFrame(container, fg_color=card_color, corner_radius=14)
        header_card.pack(fill="x", pady=(0, 12))

        title = ctk.CTkLabel(
            header_card,
            text="Hour Entry Worksheet",
            font=("Segoe UI Semibold", 24),
            text_color=title_color,
        )
        title.pack(anchor="w", padx=16, pady=(12, 4))

        subtitle = ctk.CTkLabel(
            header_card,
            text="Capture opening/closing times and monitor runtime trends.",
            font=("Segoe UI", 13),
            text_color=subtitle_color,
        )
        subtitle.pack(anchor="w", padx=16, pady=(0, 12))

        form_card = ctk.CTkFrame(container, fg_color=card_color, corner_radius=14)
        form_card.pack(fill="x", pady=(0, 12))

        form_title = ctk.CTkLabel(
            form_card,
            text="Input",
            font=("Segoe UI Semibold", 16),
            text_color="#e2e8f0",
        )
        form_title.grid(row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12, 8))

        label_font = ("Segoe UI", 13)
        input_font = ("Segoe UI", 14)

        lbl_machine = ctk.CTkLabel(form_card, text="Machine", font=label_font, text_color="#cbd5e1")
        lbl_machine.grid(row=1, column=0, sticky="w", padx=14, pady=8)
        machines = getattr(self, "machines", None) or self._load_user_machines()
        options = [f"{m.get('id')} - {m.get('name') or m.get('type')}" for m in machines]
        if not options:
            options = ["(No machines loaded)"]
        self._hour_machine_var = tk.StringVar(value=options[0])
        self._hour_machine_values = options
        machine_menu = ttk.Combobox(
            form_card,
            textvariable=self._hour_machine_var,
            values=options,
            state="readonly",
            font=input_font,
            style=worksheet_combo_style,
        )
        machine_menu.grid(row=1, column=1, sticky="ew", padx=14, pady=8)

        lbl_open = ctk.CTkLabel(form_card, text="Opening time (HH:MM)", font=label_font, text_color="#cbd5e1")
        lbl_open.grid(row=2, column=0, sticky="w", padx=14, pady=8)
        self._hour_open_var = tk.StringVar(value="08:00")
        open_entry = ctk.CTkEntry(form_card, textvariable=self._hour_open_var, font=input_font, height=36)
        open_entry.grid(row=2, column=1, sticky="ew", padx=14, pady=8)

        lbl_close = ctk.CTkLabel(form_card, text="Closing time (HH:MM)", font=label_font, text_color="#cbd5e1")
        lbl_close.grid(row=3, column=0, sticky="w", padx=14, pady=8)
        self._hour_close_var = tk.StringVar(value="17:00")
        close_entry = ctk.CTkEntry(form_card, textvariable=self._hour_close_var, font=input_font, height=36)
        close_entry.grid(row=3, column=1, sticky="ew", padx=14, pady=8)

        lbl_read = ctk.CTkLabel(form_card, text="Hour reading", font=label_font, text_color="#cbd5e1")
        lbl_read.grid(row=4, column=0, sticky="w", padx=14, pady=(8, 14))
        self._hour_reading_var = tk.StringVar(value="0")
        reading_entry = ctk.CTkEntry(form_card, textvariable=self._hour_reading_var, font=input_font, height=36)
        reading_entry.grid(row=4, column=1, sticky="ew", padx=14, pady=(8, 14))

        form_card.grid_columnconfigure(1, weight=1)

        calc_card = ctk.CTkFrame(container, fg_color=card_color, corner_radius=14)
        calc_card.pack(fill="both", expand=True, pady=(0, 12))

        calc_title = ctk.CTkLabel(
            calc_card,
            text="Calculated Runtime",
            font=("Segoe UI Semibold", 16),
            text_color="#e2e8f0",
        )
        calc_title.pack(anchor="w", padx=14, pady=(12, 8))

        metrics = ctk.CTkFrame(calc_card, fg_color="transparent")
        metrics.pack(fill="x", padx=12, pady=(0, 10))

        def _make_metric(parent, title_text: str):
            box = ctk.CTkFrame(parent, fg_color="#0b1220", corner_radius=10)
            box.pack(side="left", fill="x", expand=True, padx=4)
            title_lbl = ctk.CTkLabel(box, text=title_text, font=("Segoe UI", 12), text_color="#94a3b8")
            title_lbl.pack(anchor="w", padx=10, pady=(8, 2))
            value_lbl = ctk.CTkLabel(box, text="-", font=("Segoe UI Semibold", 15), text_color="#f8fafc")
            value_lbl.pack(anchor="w", padx=10, pady=(0, 10))
            return value_lbl

        self._per_day_label = _make_metric(metrics, "Daily")
        self._per_week_label = _make_metric(metrics, "Weekly")
        self._per_month_label = _make_metric(metrics, "Monthly")

        lists_frame = ctk.CTkFrame(calc_card, fg_color="transparent")
        lists_frame.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        week_col = ctk.CTkFrame(lists_frame, fg_color="#0b1220", corner_radius=10)
        week_col.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        month_col = ctk.CTkFrame(lists_frame, fg_color="#0b1220", corner_radius=10)
        month_col.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        week_lbl = ctk.CTkLabel(week_col, text="Week (7 days)", font=("Segoe UI Semibold", 14), text_color="#cbd5e1")
        week_lbl.pack(anchor="w", padx=10, pady=(8, 4))
        month_lbl = ctk.CTkLabel(month_col, text="Month (30 days)", font=("Segoe UI Semibold", 14), text_color="#cbd5e1")
        month_lbl.pack(anchor="w", padx=10, pady=(8, 4))

        self._week_listbox = tk.Listbox(
            week_col,
            height=7,
            font=("Segoe UI", 12),
            bg="#0b1220",
            fg="#e2e8f0",
            selectbackground="#1d4ed8",
            selectforeground="#f8fafc",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
        )
        self._week_listbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._month_listbox = tk.Listbox(
            month_col,
            height=10,
            font=("Segoe UI", 12),
            bg="#0b1220",
            fg="#e2e8f0",
            selectbackground="#1d4ed8",
            selectforeground="#f8fafc",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
        )
        self._month_listbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        lists_frame.grid_columnconfigure(0, weight=1)
        lists_frame.grid_columnconfigure(1, weight=1)
        lists_frame.grid_rowconfigure(0, weight=1)

        recent_card = ctk.CTkFrame(container, fg_color=card_color, corner_radius=14)
        recent_card.pack(fill="both", pady=(0, 12))

        recent_header = ctk.CTkFrame(recent_card, fg_color="transparent")
        recent_header.pack(fill="x", padx=14, pady=(10, 6))

        recent_lbl = ctk.CTkLabel(
            recent_header,
            text="Recent Entries Worksheet Table",
            font=("Segoe UI Semibold", 14),
            text_color="#e2e8f0",
        )
        recent_lbl.pack(side="left")

        def _on_manual_refresh():
            import threading
            try:
                threading.Thread(target=self._refresh_remote_hour_entries, daemon=True).start()
            except Exception:
                try:
                    self._refresh_remote_hour_entries()
                except Exception:
                    pass

        header_actions = ctk.CTkFrame(recent_header, fg_color="transparent")
        header_actions.pack(side="right")

        modal_btn = ctk.CTkButton(
            header_actions,
            text="Open Table",
            width=110,
            command=self._open_hour_entries_table_modal,
            font=("Segoe UI Semibold", 13),
            fg_color="#0f766e",
            hover_color="#115e59",
        )
        modal_btn.pack(side="right", padx=(8, 0))

        refresh_btn = ctk.CTkButton(
            header_actions,
            text="Refresh",
            width=110,
            command=_on_manual_refresh,
            font=("Segoe UI Semibold", 13),
            fg_color=theme_mod.SIMPLE_PALETTE.get("primary", "#2563eb"),
            hover_color="#1d4ed8",
        )
        refresh_btn.pack(side="right")

        table_shell = ctk.CTkFrame(recent_card, fg_color="#0b1220", corner_radius=10)
        table_shell.pack(fill="both", expand=True, padx=14, pady=(0, 12))

        columns = ("machine", "opening", "closing", "reading", "daily", "weekly", "monthly")
        self._hour_recent_columns = columns
        self._hour_recent_entries: List[Dict[str, Any]] = []
        self._recent_tree = ttk.Treeview(
            table_shell,
            columns=columns,
            show="headings",
            height=8,
            style=worksheet_tree_style,
        )
        self._recent_tree.heading("machine", text="Machine")
        self._recent_tree.heading("opening", text="Open")
        self._recent_tree.heading("closing", text="Close")
        self._recent_tree.heading("reading", text="Reading")
        self._recent_tree.heading("daily", text="Daily h")
        self._recent_tree.heading("weekly", text="Weekly h")
        self._recent_tree.heading("monthly", text="Monthly h")
        self._recent_tree.column("machine", width=220, anchor="w")
        self._recent_tree.column("opening", width=78, anchor="center")
        self._recent_tree.column("closing", width=78, anchor="center")
        self._recent_tree.column("reading", width=90, anchor="center")
        self._recent_tree.column("daily", width=90, anchor="center")
        self._recent_tree.column("weekly", width=90, anchor="center")
        self._recent_tree.column("monthly", width=95, anchor="center")
        self._recent_tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        try:
            self._recent_tree.tag_configure("worksheet_even", background="#0f172a", foreground="#e2e8f0")
            self._recent_tree.tag_configure("worksheet_odd", background="#111827", foreground="#e2e8f0")
        except Exception:
            pass

        table_scroll = tk.Scrollbar(table_shell, orient="vertical", command=self._recent_tree.yview)
        table_scroll.pack(side="right", fill="y", padx=(4, 8), pady=8)
        self._recent_tree.configure(yscrollcommand=table_scroll.set)
        self._recent_tree.bind("<<TreeviewSelect>>", lambda _e: self._on_recent_hour_entry_selected())
        self._render_recent_hour_entries([])
        try:
            self._render_recent_hour_entries(self._load_hour_history_entries())
        except Exception:
            pass

        prediction_card = ctk.CTkFrame(container, fg_color=card_color, corner_radius=14)
        prediction_card.pack(fill="x", pady=(0, 12))

        pred_header = ctk.CTkLabel(
            prediction_card,
            text="ML Performance Prediction",
            font=("Segoe UI Semibold", 16),
            text_color="#e2e8f0",
        )
        pred_header.pack(anchor="w", padx=14, pady=(12, 6))

        self._pred_summary_label = ctk.CTkLabel(
            prediction_card,
            text="Preparing model...",
            font=("Segoe UI", 12),
            text_color="#94a3b8",
        )
        self._pred_summary_label.pack(anchor="w", padx=14, pady=(0, 8))

        pred_metrics = ctk.CTkFrame(prediction_card, fg_color="transparent")
        pred_metrics.pack(fill="x", padx=12, pady=(0, 10))

        def _pred_box(title_text: str):
            box = ctk.CTkFrame(pred_metrics, fg_color="#0b1220", corner_radius=10)
            box.pack(side="left", fill="x", expand=True, padx=4)
            ctk.CTkLabel(box, text=title_text, font=("Segoe UI", 12), text_color="#94a3b8").pack(
                anchor="w", padx=10, pady=(8, 2)
            )
            value = ctk.CTkLabel(box, text="-", font=("Segoe UI Semibold", 15), text_color="#f8fafc")
            value.pack(anchor="w", padx=10, pady=(0, 10))
            return value

        self._pred_day_label = _pred_box("Predicted Next Day")
        self._pred_month_label = _pred_box("Predicted Monthly")
        self._pred_trend_label = _pred_box("Trend")
        self._pred_risk_label = _pred_box("Risk")

        pred_bottom = ctk.CTkFrame(prediction_card, fg_color="transparent")
        pred_bottom.pack(fill="x", padx=14, pady=(0, 12))

        self._pred_conf_label = ctk.CTkLabel(
            pred_bottom,
            text="Confidence: -",
            font=("Segoe UI", 12),
            text_color="#94a3b8",
        )
        self._pred_conf_label.pack(anchor="w", pady=(0, 6))

        self._pred_forecast_list = tk.Listbox(
            pred_bottom,
            height=5,
            font=("Segoe UI", 12),
            bg="#0b1220",
            fg="#e2e8f0",
            selectbackground="#1d4ed8",
            selectforeground="#f8fafc",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
        )
        self._pred_forecast_list.pack(fill="x")

        actions = ctk.CTkFrame(container, fg_color="transparent")
        actions.pack(fill="x", pady=(0, 2))

        calc_btn = ctk.CTkButton(
            actions,
            text="Calculate",
            command=self._hour_calculate,
            width=120,
            font=("Segoe UI Semibold", 13),
            fg_color="#334155",
            hover_color="#475569",
        )
        calc_btn.pack(side="left", padx=(0, 8))
        submit_btn = ctk.CTkButton(
            actions,
            text="Submit Entry",
            command=self._hour_submit,
            width=140,
            font=("Segoe UI Semibold", 13),
            fg_color="#059669",
            hover_color="#047857",
        )
        submit_btn.pack(side="left")

        try:
            self._hour_calculate()
        except Exception:
            pass

        # Pull remote hour entries (best-effort) and populate worksheet table
        try:
            import threading

            def _pull():
                try:
                    from api_client import sync_get_hour_entries
                    entries = sync_get_hour_entries() or []
                except Exception:
                    entries = []

                def _apply():
                    try:
                        self._render_recent_hour_entries(entries)

                        if entries:
                            last = entries[-1]
                            try:
                                if last.get("machine"):
                                    val = last.get("machine")
                                    for opt in getattr(self, "_hour_machine_values", machine_menu["values"]):
                                        if str(val) in opt:
                                            try:
                                                self._hour_machine_var.set(opt)
                                            except Exception:
                                                pass
                                            break
                                if last.get("opening"):
                                    self._hour_open_var.set(last.get("opening"))
                                if last.get("closing"):
                                    self._hour_close_var.set(last.get("closing"))
                                if last.get("hour_reading") is not None:
                                    self._hour_reading_var.set(str(last.get("hour_reading")))
                                self._hour_calculate()
                            except Exception:
                                pass
                    except Exception:
                        pass

                try:
                    self.after(0, _apply)
                except Exception:
                    _apply()

            t = threading.Thread(target=_pull, daemon=True)
            t.start()
        except Exception:
            pass
        try:
            self._refresh_ml_prediction_panel()
        except Exception:
            pass

    def _load_hour_history_entries(self) -> List[Dict[str, Any]]:
        try:
            p = self._hour_data_path()
            if p.exists():
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f) or []
                if isinstance(data, list):
                    return [d for d in data if isinstance(d, dict)]
        except Exception:
            pass
        return []

    def _render_recent_hour_entries(self, entries: List[Dict[str, Any]]) -> None:
        """Render worksheet entries into the modern table view."""
        if not hasattr(self, "_recent_tree"):
            return
        safe_entries = [e for e in (entries or []) if isinstance(e, dict)]
        self._hour_recent_entries = list(safe_entries)

        try:
            for iid in self._recent_tree.get_children():
                self._recent_tree.delete(iid)
        except Exception:
            return

        # Show latest entries first for quick operations.
        for display_idx, entry in enumerate(reversed(safe_entries[-80:])):
            machine = str(entry.get("machine", "") or "")
            opening = str(entry.get("opening", "") or "")
            closing = str(entry.get("closing", "") or "")
            reading = entry.get("hour_reading")
            per_day = entry.get("per_day_hours")
            per_week = entry.get("per_week_hours")
            per_month = entry.get("per_month_hours")

            def _fmt_num(v: Any) -> str:
                try:
                    if v is None or str(v).strip() == "":
                        return "-"
                    return f"{float(v):.2f}"
                except Exception:
                    return str(v)

            values = (
                machine,
                opening,
                closing,
                _fmt_num(reading),
                _fmt_num(per_day),
                _fmt_num(per_week),
                _fmt_num(per_month),
            )
            # Store the original index in iid for direct lookup.
            source_idx = len(safe_entries) - 1 - display_idx
            row_tag = "worksheet_even" if display_idx % 2 == 0 else "worksheet_odd"
            self._recent_tree.insert("", "end", iid=str(source_idx), values=values, tags=(row_tag,))

    def _on_recent_hour_entry_selected(self) -> None:
        """Prefill worksheet form when a table row is selected."""
        if not hasattr(self, "_recent_tree"):
            return
        try:
            selected = self._recent_tree.selection()
            if not selected:
                return
            idx = int(selected[0])
            if idx < 0 or idx >= len(getattr(self, "_hour_recent_entries", [])):
                return
            row = self._hour_recent_entries[idx]
        except Exception:
            return

        try:
            machine_val = row.get("machine")
            if machine_val:
                for opt in getattr(self, "_hour_machine_values", []):
                    if str(machine_val) in str(opt):
                        self._hour_machine_var.set(opt)
                        break
            if row.get("opening"):
                self._hour_open_var.set(str(row.get("opening")))
            if row.get("closing"):
                self._hour_close_var.set(str(row.get("closing")))
            if row.get("hour_reading") is not None:
                self._hour_reading_var.set(str(row.get("hour_reading")))
            self._hour_calculate()
        except Exception:
            pass

    def _open_hour_entries_table_modal(self) -> None:
        """Open a larger table modal for worksheet history browsing."""
        try:
            top = ctk.CTkToplevel(self)
            top.title("Worksheet History Table")
            top.geometry("980x520")
            top.transient(self)
            top.grab_set()

            modal_tree_style = self._apply_dark_treeview_style("Worksheet.Modal.Treeview")

            card = ctk.CTkFrame(top, fg_color="#0b1220", corner_radius=14)
            card.pack(fill="both", expand=True, padx=12, pady=12)

            header = ctk.CTkFrame(card, fg_color="transparent")
            header.pack(fill="x", padx=10, pady=(10, 6))
            ctk.CTkLabel(
                header,
                text="Worksheet Entries",
                font=("Segoe UI Semibold", 18),
                text_color="#f8fafc",
            ).pack(side="left")

            source_entries = list(getattr(self, "_hour_recent_entries", []) or self._load_hour_history_entries())

            cols = ("machine", "opening", "closing", "reading", "daily", "weekly", "monthly")
            tree = ttk.Treeview(card, columns=cols, show="headings", style=modal_tree_style)
            for col, label in (
                ("machine", "Machine"),
                ("opening", "Open"),
                ("closing", "Close"),
                ("reading", "Reading"),
                ("daily", "Daily h"),
                ("weekly", "Weekly h"),
                ("monthly", "Monthly h"),
            ):
                tree.heading(col, text=label)
            tree.column("machine", width=250, anchor="w")
            tree.column("opening", width=80, anchor="center")
            tree.column("closing", width=80, anchor="center")
            tree.column("reading", width=100, anchor="center")
            tree.column("daily", width=100, anchor="center")
            tree.column("weekly", width=110, anchor="center")
            tree.column("monthly", width=110, anchor="center")
            tree.pack(fill="both", expand=True, padx=10, pady=(0, 10), side="left")
            try:
                tree.tag_configure("worksheet_even", background="#0f172a", foreground="#e2e8f0")
                tree.tag_configure("worksheet_odd", background="#111827", foreground="#e2e8f0")
            except Exception:
                pass

            ybar = tk.Scrollbar(card, orient="vertical", command=tree.yview)
            ybar.pack(side="right", fill="y", padx=(0, 10), pady=(0, 10))
            tree.configure(yscrollcommand=ybar.set)

            def _fmt(v: Any) -> str:
                try:
                    if v is None or str(v).strip() == "":
                        return "-"
                    return f"{float(v):.2f}"
                except Exception:
                    return str(v)

            for idx, entry in enumerate(reversed(source_entries[-200:])):
                row_tag = "worksheet_even" if idx % 2 == 0 else "worksheet_odd"
                tree.insert(
                    "",
                    "end",
                    values=(
                        entry.get("machine", ""),
                        entry.get("opening", ""),
                        entry.get("closing", ""),
                        _fmt(entry.get("hour_reading")),
                        _fmt(entry.get("per_day_hours")),
                        _fmt(entry.get("per_week_hours")),
                        _fmt(entry.get("per_month_hours")),
                    ),
                    tags=(row_tag,),
                )

            footer = ctk.CTkFrame(top, fg_color="transparent")
            footer.pack(fill="x", padx=12, pady=(0, 10))
            ctk.CTkButton(
                footer,
                text="Close",
                width=110,
                height=34,
                font=("Segoe UI Semibold", 13),
                command=top.destroy,
            ).pack(side="right")
        except Exception:
            logger.exception("Failed to open worksheet table modal")

    def _selected_machine_keys(self) -> tuple[str, str]:
        try:
            selected = str(self._hour_machine_var.get() or "").strip()
        except Exception:
            selected = ""
        primary = selected
        machine_id = selected
        if " - " in selected:
            machine_id = selected.split(" - ", 1)[0].strip()
        return primary.lower(), machine_id.lower()

    def _per_day_from_entry(self, entry: Dict[str, Any]) -> Optional[float]:
        try:
            val = entry.get("per_day_hours")
            if val is not None:
                v = float(val)
                if v >= 0:
                    return v
        except Exception:
            pass
        try:
            opening = self._parse_time(entry.get("opening", ""))
            closing = self._parse_time(entry.get("closing", ""))
            if opening is None or closing is None:
                return None
            diff = closing - opening
            if diff < 0:
                diff += 24
            if diff < 0:
                return None
            return diff
        except Exception:
            return None

    def _compute_ml_prediction(
        self,
        values: List[float],
        horizon_days: int = 7,
    ) -> Dict[str, Any]:
        cleaned = [float(v) for v in values if isinstance(v, (int, float)) and v >= 0]
        if not cleaned:
            return {
                "ok": False,
                "reason": "No valid runtime history yet. Add at least 2 entries.",
            }

        n = len(cleaned)
        if n == 1:
            baseline = cleaned[0]
            preds = [max(0.0, baseline) for _ in range(horizon_days)]
            slope = 0.0
        else:
            x_vals = list(range(n))
            x_mean = sum(x_vals) / n
            y_mean = sum(cleaned) / n
            denom = sum((x - x_mean) ** 2 for x in x_vals)
            if denom == 0:
                slope = 0.0
            else:
                slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_vals, cleaned)) / denom
            intercept = y_mean - slope * x_mean
            preds = [max(0.0, intercept + slope * (n + i)) for i in range(1, horizon_days + 1)]

        pred_day = preds[0] if preds else 0.0
        pred_week_avg = (sum(preds) / len(preds)) if preds else pred_day
        pred_month = pred_week_avg * 30.0

        if slope > 0.25:
            trend = "Increasing load"
            trend_color = "#f59e0b"
        elif slope < -0.25:
            trend = "Reducing load"
            trend_color = "#34d399"
        else:
            trend = "Stable"
            trend_color = "#93c5fd"

        if pred_week_avg >= 18:
            risk = "High stress risk"
            risk_color = "#f87171"
        elif pred_week_avg >= 14:
            risk = "Moderate stress"
            risk_color = "#fbbf24"
        else:
            risk = "Low stress"
            risk_color = "#34d399"

        confidence = "Medium" if n < 8 else "High"
        return {
            "ok": True,
            "count": n,
            "pred_day": pred_day,
            "pred_week_avg": pred_week_avg,
            "pred_month": pred_month,
            "trend": trend,
            "trend_color": trend_color,
            "risk": risk,
            "risk_color": risk_color,
            "confidence": confidence,
            "slope": slope,
            "forecast": preds,
        }

    def _refresh_ml_prediction_panel(self, latest_runtime: Optional[float] = None) -> None:
        if not hasattr(self, "_pred_summary_label"):
            return

        try:
            all_entries = self._load_hour_history_entries()
            selected_full, selected_id = self._selected_machine_keys()
            machine_values: List[float] = []
            for entry in all_entries:
                machine_name = str(entry.get("machine", "")).strip().lower()
                if selected_full and selected_full != "(no machines loaded)":
                    if machine_name and not (
                        machine_name == selected_full
                        or machine_name.startswith(selected_id)
                        or selected_id in machine_name
                    ):
                        continue
                val = self._per_day_from_entry(entry)
                if val is not None:
                    machine_values.append(val)

            if latest_runtime is not None and latest_runtime >= 0:
                machine_values.append(float(latest_runtime))

            model = self._compute_ml_prediction(machine_values, horizon_days=7)

            self._pred_forecast_list.delete(0, "end")
            if not model.get("ok"):
                self._pred_summary_label.configure(text=model.get("reason", "Insufficient data"), text_color="#94a3b8")
                self._pred_day_label.configure(text="-")
                self._pred_month_label.configure(text="-")
                self._pred_trend_label.configure(text="-", text_color="#94a3b8")
                self._pred_risk_label.configure(text="-", text_color="#94a3b8")
                self._pred_conf_label.configure(text="Confidence: Low (need more entries)")
                return

            self._pred_summary_label.configure(
                text=f"ML trend model trained on {model.get('count', 0)} runtime entries.",
                text_color="#cbd5e1",
            )
            self._pred_day_label.configure(text=f"{model.get('pred_day', 0.0):.2f} h/day")
            self._pred_month_label.configure(text=f"{model.get('pred_month', 0.0):.1f} h/month")
            self._pred_trend_label.configure(text=str(model.get("trend", "-")), text_color=model.get("trend_color", "#93c5fd"))
            self._pred_risk_label.configure(text=str(model.get("risk", "-")), text_color=model.get("risk_color", "#34d399"))
            self._pred_conf_label.configure(text=f"Confidence: {model.get('confidence', 'Low')}")

            for i, v in enumerate(model.get("forecast", []), start=1):
                self._pred_forecast_list.insert("end", f"Day +{i}: {float(v):.2f} h")
        except Exception:
            logger.exception("Failed to refresh ML prediction panel")

    def _parse_time(self, txt: str) -> Optional[float]:
        """Parse time string like HH:MM and return hours as float from midnight."""
        try:
            txt = (txt or '').strip()
            if not txt:
                return None
            # accept H, H:M, HH:MM
            parts = txt.split(":")
            if len(parts) == 1:
                h = int(parts[0])
                m = 0
            else:
                h = int(parts[0])
                m = int(parts[1])
            if h < 0:
                h = 0
            if m < 0:
                m = 0
            return h + (m / 60.0)
        except Exception:
            return None

    def _hour_calculate(self) -> None:
        try:
            open_t = self._parse_time(self._hour_open_var.get())
            close_t = self._parse_time(self._hour_close_var.get())
            if open_t is None or close_t is None:
                per_day = None
            else:
                per_day = close_t - open_t
                if per_day < 0:
                    # assume next day close
                    per_day += 24

            per_week = per_day * 7 if per_day is not None else None
            per_month = per_day * 30 if per_day is not None else None

            self._per_day_label.configure(text=f"{per_day:.2f} h/day" if per_day is not None else "-")
            self._per_week_label.configure(text=f"{per_week:.2f} h/week" if per_week is not None else "-")
            self._per_month_label.configure(text=f"{per_month:.2f} h/month" if per_month is not None else "-")

            # Populate listboxes with repeated daily values
            self._week_listbox.delete(0, 'end')
            self._month_listbox.delete(0, 'end')
            if per_day is not None:
                for i in range(7):
                    self._week_listbox.insert('end', f"Day {i+1}: {per_day:.2f}h")
                for i in range(30):
                    self._month_listbox.insert('end', f"Day {i+1}: {per_day:.2f}h")
            try:
                self._refresh_ml_prediction_panel(latest_runtime=per_day)
            except Exception:
                pass
        except Exception:
            logger.exception('Failed to calculate hours')

    def _hour_submit(self) -> None:
        try:
            machine = (self._hour_machine_var.get() or '').strip()
            open_txt = (self._hour_open_var.get() or '').strip()
            close_txt = (self._hour_close_var.get() or '').strip()
            reading_txt = (self._hour_reading_var.get() or '').strip()

            per_day = None
            open_t = self._parse_time(open_txt)
            close_t = self._parse_time(close_txt)
            if open_t is not None and close_t is not None:
                per_day = close_t - open_t
                if per_day < 0:
                    per_day += 24

            try:
                reading = float(reading_txt)
            except Exception:
                reading = None

            resolved_machine = self._resolve_hour_entry_machine(machine)

            entry = {
                'machine': machine,
                'machine_id': str((resolved_machine or {}).get('id') or '').strip(),
                'opening': open_txt,
                'closing': close_txt,
                'hour_reading': reading,
                'per_day_hours': round(per_day, 2) if per_day is not None else None,
                'per_week_hours': round(per_day * 7, 2) if per_day is not None else None,
                'per_month_hours': round(per_day * 30, 2) if per_day is not None else None,
            }

            save_result = self._save_hour_entry(entry)
            try:
                msg = "Hour entry saved successfully."
                machine_sync = (save_result or {}).get("machine_sync") or {}
                if (save_result or {}).get("machine_runtime_synced"):
                    msg += f"\nMachine runtime updated to {machine_sync.get('hours')} hours"
                    if machine_sync.get("next_due_hours") is not None:
                        msg += f"\nNext due threshold: {machine_sync.get('next_due_hours')} hours"
                sync_info = (save_result or {}).get("pm_sync") or {}
                if (save_result or {}).get("pm_runtime_synced"):
                    eq_ids = sync_info.get("matched_equipment_ids") or []
                    if eq_ids:
                        msg += f"\nRuntime synced to PM for: {', '.join(eq_ids)}"
                tk.messagebox.showinfo('Saved', msg)
            except Exception:
                pass
            try:
                self._render_recent_hour_entries(self._load_hour_history_entries())
            except Exception:
                pass
            try:
                import threading
                threading.Thread(target=self._refresh_remote_hour_entries, daemon=True).start()
            except Exception:
                pass
            try:
                if (save_result or {}).get("machine_runtime_synced"):
                    self._launch_machine_alert_scan()
            except Exception:
                pass
            try:
                self._refresh_ml_prediction_panel(latest_runtime=per_day)
            except Exception:
                pass
        except Exception:
            logger.exception('Failed to submit hour entry')

    def _refresh_remote_hour_entries(self) -> None:
        """Fetch remote hour entries and refresh worksheet table/form prefill."""
        try:
            from api_client import sync_get_hour_entries
            entries = sync_get_hour_entries() or []
        except Exception:
            entries = []

        def _apply():
            try:
                self._render_recent_hour_entries(entries)
                if entries:
                    last = entries[-1]
                    try:
                        if last.get('machine'):
                            val = last.get('machine')
                            for opt in getattr(self, '_hour_machine_values', []):
                                if str(val) in opt:
                                    try:
                                        self._hour_machine_var.set(opt)
                                    except Exception:
                                        pass
                                    break
                        if last.get('opening'):
                            self._hour_open_var.set(last.get('opening'))
                        if last.get('closing'):
                            self._hour_close_var.set(last.get('closing'))
                        if last.get('hour_reading') is not None:
                            self._hour_reading_var.set(str(last.get('hour_reading')))
                        self._hour_calculate()
                        self._refresh_ml_prediction_panel()
                    except Exception:
                        pass
            except Exception:
                pass

        try:
            self.after(0, _apply)
        except Exception:
            _apply()

    def _open_add_component_dialog(self, area_key: str) -> None:
        try:
            top = ctk.CTkToplevel(self)
            top.title("Add Component")
            top.geometry("360x140")
            lbl = ctk.CTkLabel(top, text="Component name:")
            lbl.pack(pady=(12,4))
            entry = ctk.CTkEntry(top)
            entry.pack(fill="x", padx=12)

            def _on_add():
                name = (entry.get() or "").strip()
                if not name:
                    try:
                        tk.messagebox.showwarning("Input Required", "Please enter a component name.")
                    except Exception:
                        pass
                    return
                try:
                    item = {"name": name, "details": ""}
                    self.plant_components.setdefault(area_key, []).append(item)
                    self._refresh_area_listbox(area_key)
                    try:
                        self._save_plant_components()
                    except Exception:
                        pass
                except Exception:
                    logger.exception("Failed to add component")
                finally:
                    try:
                        top.destroy()
                    except Exception:
                        pass

            btn_frame = ctk.CTkFrame(top, fg_color="transparent")
            btn_frame.pack(fill="x", pady=12)
            ok = ctk.CTkButton(btn_frame, text="Add", command=_on_add)
            ok.pack(side="left", padx=12)
            cancel = ctk.CTkButton(btn_frame, text="Cancel", command=top.destroy)
            cancel.pack(side="left")
        except Exception:
            logger.exception("Add dialog failed")

    def _open_edit_component_dialog(self, area_key: str) -> None:
        try:
            lb = self.plant_boxes.get(area_key)
            if not lb:
                return
            sel = lb.curselection()
            if not sel:
                try:
                    tk.messagebox.showwarning("No Selection", "Please select an item to edit.")
                except Exception:
                    pass
                return
            idx = sel[0]
            current = lb.get(idx)

            # Map visible index to model index (respecting search filter)
            items = self.plant_components.get(area_key, [])
            q = (self.plant_search_vars.get(area_key) or tk.StringVar()).get().strip().lower()
            model_idx = idx
            if q:
                displayed = [it for it in items if q in (it.get('name','').lower())]
                if idx < len(displayed):
                    try:
                        model_idx = items.index(displayed[idx])
                    except Exception:
                        model_idx = idx

            model_item = None
            try:
                model_item = items[model_idx]
            except Exception:
                model_item = None

            top = ctk.CTkToplevel(self)
            top.title("Edit Component")
            top.geometry("360x180")
            lbl = ctk.CTkLabel(top, text="Component name:")
            lbl.pack(pady=(12,4))
            entry = ctk.CTkEntry(top)
            entry.insert(0, model_item.get('name') if isinstance(model_item, dict) else (model_item or current))
            entry.pack(fill="x", padx=12)
            lbl2 = ctk.CTkLabel(top, text="Details / Notes:")
            lbl2.pack(pady=(8,4))
            details = tk.Text(top, height=4)
            details.pack(fill='both', padx=12)
            try:
                details.insert('1.0', model_item.get('details','') if isinstance(model_item, dict) else '')
            except Exception:
                pass

            def _on_save():
                name = (entry.get() or "").strip()
                if not name:
                    try:
                        tk.messagebox.showwarning("Input Required", "Please enter a component name.")
                    except Exception:
                        pass
                    return
                try:
                    # update model and listbox
                    self.plant_components.setdefault(area_key, [])
                    txt = (details.get('1.0', 'end') or '').strip()
                    if model_idx < len(self.plant_components[area_key]):
                        self.plant_components[area_key][model_idx]['name'] = name
                        self.plant_components[area_key][model_idx]['details'] = txt
                    else:
                        # fallback
                        self.plant_components[area_key].append({"name": name, "details": txt})
                    self._refresh_area_listbox(area_key)
                    # persist
                    try:
                        self._save_plant_components()
                    except Exception:
                        pass
                except Exception:
                    logger.exception("Failed to save edit")
                finally:
                    try:
                        top.destroy()
                    except Exception:
                        pass

            btn_frame = ctk.CTkFrame(top, fg_color="transparent")
            btn_frame.pack(fill="x", pady=12)
            save = ctk.CTkButton(btn_frame, text="Save", command=_on_save)
            save.pack(side="left", padx=12)
            cancel = ctk.CTkButton(btn_frame, text="Cancel", command=top.destroy)
            cancel.pack(side="left")
        except Exception:
            logger.exception("Edit dialog failed")

    def _plant_data_path(self) -> "Path":
        try:
            local_data_dir = app_data_dir()
            local_data_dir.mkdir(parents=True, exist_ok=True)
            return local_data_dir / "plant_components.json"
        except Exception:
            # fallback to relative path
            return Path("plant_components.json")

    def _load_plant_components(self) -> None:
        try:
            p = self._plant_data_path()
            if p.exists():
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Normalize stored entries to dicts {name, details}
                pc = data or {}
                normalized = {}
                for k, items in pc.items():
                    normalized[k] = []
                    try:
                        for it in items or []:
                            if isinstance(it, dict):
                                name = it.get('name') or ''
                                details = it.get('details') or ''
                                normalized[k].append({'name': name, 'details': details})
                            else:
                                normalized[k].append({'name': str(it), 'details': ''})
                    except Exception:
                        pass
                self.plant_components = normalized
            else:
                self.plant_components = {}
        except Exception:
            logger.exception("Failed to load plant components")
            self.plant_components = {}

        # If API available, try to pull remote components and merge (remote wins)
        try:
            from api_client import sync_get_plant_components
            remote = sync_get_plant_components() or {}
            if remote:
                # Normalize remote entries similar to local normalization
                norm = {}
                for k, items in remote.items():
                    norm[k] = []
                    try:
                        for it in items or []:
                            if isinstance(it, dict):
                                name = it.get('name') or ''
                                details = it.get('details') or ''
                                norm[k].append({'name': name, 'details': details})
                            else:
                                norm[k].append({'name': str(it), 'details': ''})
                    except Exception:
                        pass
                # Remote wins: replace local with remote where present
                for k, v in norm.items():
                    self.plant_components[k] = v
        except Exception:
            # ignore API errors and fall back to local file
            pass

    def _save_plant_components(self) -> None:
        try:
            p = self._plant_data_path()
            with open(p, "w", encoding="utf-8") as f:
                json.dump(self.plant_components, f, indent=2)
        except Exception:
            logger.exception("Failed to save plant components")

        # Attempt to push to API asynchronously (best-effort)
        try:
            from api_client import sync_save_plant_components
            try:
                sync_save_plant_components(self.plant_components)
            except Exception:
                pass
        except Exception:
            pass

    def _refresh_area_listbox(self, area_key: str) -> None:
        try:
            lb = self.plant_boxes.get(area_key)
            if lb is None:
                return
            # Get model list
            items = self.plant_components.get(area_key, [])
            # Apply search filter if present
            q = (self.plant_search_vars.get(area_key) or tk.StringVar()).get().strip().lower()
            lb.delete(0, 'end')
            displayed = []
            for it in items:
                name = (it.get('name') if isinstance(it, dict) else str(it))
                if not q or q in name.lower():
                    displayed.append(it)
                    lb.insert('end', name)
            if not displayed:
                lb.insert('end', 'No items found')
        except Exception:
            logger.exception("Failed to refresh listbox for %s", area_key)

    def _visible_to_model_index(self, area_key: str, visible_idx: int):
        try:
            items = self.plant_components.get(area_key, [])
            q = (self.plant_search_vars.get(area_key) or tk.StringVar()).get().strip().lower()
            if not q:
                return visible_idx if visible_idx < len(items) else None
            displayed = [it for it in items if q in (it.get('name','').lower())]
            if visible_idx < len(displayed):
                try:
                    return items.index(displayed[visible_idx])
                except Exception:
                    return None
            return None
        except Exception:
            return None

    def _undo_delete(self) -> None:
        try:
            if not self._last_deleted:
                return
            area_key, model_idx, item = self._last_deleted
            items = self.plant_components.setdefault(area_key, [])
            if model_idx is None or model_idx > len(items):
                items.append(item)
            else:
                items.insert(model_idx, item)
            self._save_plant_components()
            self._refresh_area_listbox(area_key)
            self._last_deleted = None
            if getattr(self, '_undo_btn', None):
                try:
                    self._undo_btn.configure(state='disabled')
                except Exception:
                    pass
        except Exception:
            logger.exception('Undo failed')

    def _enable_drag_for_listbox(self, lb: tk.Listbox, area_key: str) -> None:
        try:
            lb._drag_data = {'start_index': None}
            ghost = {'win': None}

            def on_button_press(event, lb=lb, k=area_key):
                try:
                    idx = lb.nearest(event.y)
                    lb._drag_data['start_index'] = idx
                    # create ghost window showing the item being dragged
                    try:
                        text = lb.get(idx)
                    except Exception:
                        text = ''
                    try:
                        g = tk.Toplevel(self)
                        g.wm_overrideredirect(True)
                        g.wm_attributes('-topmost', True)
                        lbl = tk.Label(g, text=text, bg='#111827', fg='white', bd=1, relief='solid')
                        lbl.pack()
                        ghost['win'] = g
                        # position near cursor
                        g.geometry(f"+{event.x_root+10}+{event.y_root+10}")
                    except Exception:
                        ghost['win'] = None
                except Exception:
                    lb._drag_data['start_index'] = None

            def on_motion(event, lb=lb, k=area_key):
                try:
                    # move ghost with cursor
                    g = ghost.get('win')
                    if g:
                        try:
                            g.geometry(f"+{event.x_root+10}+{event.y_root+10}")
                        except Exception:
                            pass
                    # highlight potential drop index
                    try:
                        target = lb.nearest(event.y)
                        lb.selection_clear(0, 'end')
                        lb.selection_set(target)
                        lb.activate(target)
                    except Exception:
                        pass
                except Exception:
                    pass

            def on_button_release(event, lb=lb, k=area_key):
                try:
                    start = lb._drag_data.get('start_index')
                    if start is None:
                        return
                    end = lb.nearest(event.y)
                    # destroy ghost
                    try:
                        g = ghost.get('win')
                        if g:
                            g.destroy()
                    except Exception:
                        pass
                    if end == start:
                        return
                    # map visible indices to model indices
                    src_model = self._visible_to_model_index(k, start)
                    dst_model = self._visible_to_model_index(k, end)
                    if src_model is None or dst_model is None:
                        return
                    items = self.plant_components.get(k, [])
                    if src_model < 0 or src_model >= len(items) or dst_model < 0 or dst_model >= len(items):
                        return
                    item = items.pop(src_model)
                    items.insert(dst_model, item)
                    self.plant_components[k] = items
                    self._save_plant_components()
                    self._refresh_area_listbox(k)
                except Exception:
                    logger.exception('Drag reorder failed for %s', k)
                finally:
                    lb._drag_data['start_index'] = None

            lb.bind('<ButtonPress-1>', on_button_press)
            lb.bind('<B1-Motion>', on_motion)
            lb.bind('<ButtonRelease-1>', on_button_release)
        except Exception:
            pass

    def _delete_component(self, area_key: str) -> None:
        try:
            lb = self.plant_boxes.get(area_key)
            if not lb:
                return
            sel = lb.curselection()
            if not sel:
                try:
                    tk.messagebox.showwarning('No Selection', 'Please select an item to delete.')
                except Exception:
                    pass
                return
            idx = sel[0]
            # map to model index
            q = (self.plant_search_vars.get(area_key) or tk.StringVar()).get().strip().lower()
            items = self.plant_components.get(area_key, [])
            if q:
                displayed = [it for it in items if q in (it.get('name','').lower())]
                if idx < len(displayed):
                    try:
                        model_idx = items.index(displayed[idx])
                    except Exception:
                        model_idx = None
                else:
                    model_idx = None
            else:
                model_idx = idx if idx < len(items) else None

            if model_idx is None:
                # nothing to delete
                return

            try:
                del items[model_idx]
            except Exception:
                pass
            self.plant_components[area_key] = items
            self._save_plant_components()
            self._refresh_area_listbox(area_key)
        except Exception:
            logger.exception('Delete failed for %s', area_key)

    def _move_component(self, area_key: str, direction: int) -> None:
        try:
            lb = self.plant_boxes.get(area_key)
            if not lb:
                return
            sel = lb.curselection()
            if not sel:
                try:
                    tk.messagebox.showwarning('No Selection', 'Please select an item to move.')
                except Exception:
                    pass
                return
            idx = sel[0]
            q = (self.plant_search_vars.get(area_key) or tk.StringVar()).get().strip().lower()
            items = self.plant_components.get(area_key, [])
            if q:
                displayed = [it for it in items if q in (it.get('name','').lower())]
                if idx < len(displayed):
                    try:
                        model_idx = items.index(displayed[idx])
                    except Exception:
                        return
                else:
                    return
            else:
                model_idx = idx

            new_idx = model_idx + direction
            if new_idx < 0 or new_idx >= len(items):
                return
            items[model_idx], items[new_idx] = items[new_idx], items[model_idx]
            self.plant_components[area_key] = items
            self._save_plant_components()
            self._refresh_area_listbox(area_key)
            try:
                # restore selection to moved item
                lb.selection_clear(0, 'end')
                lb.selection_set(new_idx)
            except Exception:
                pass
        except Exception:
            logger.exception('Move failed for %s', area_key)

    def _open_details_dialog(self, area_key: str) -> None:
        try:
            lb = self.plant_boxes.get(area_key)
            if not lb:
                return
            sel = lb.curselection()
            if not sel:
                try:
                    tk.messagebox.showwarning('No Selection', 'Please select an item to view details.')
                except Exception:
                    pass
                return
            idx = sel[0]
            items = self.plant_components.get(area_key, [])
            q = (self.plant_search_vars.get(area_key) or tk.StringVar()).get().strip().lower()
            if q:
                displayed = [it for it in items if q in (it.get('name','').lower())]
                if idx < len(displayed):
                    try:
                        model_idx = items.index(displayed[idx])
                    except Exception:
                        return
                else:
                    return
            else:
                model_idx = idx

            item = items[model_idx]

            top = ctk.CTkToplevel(self)
            top.title('Component Details')
            top.geometry('420x260')
            lbl = ctk.CTkLabel(top, text='Name:')
            lbl.pack(anchor='w', pady=(12,2), padx=12)
            name_entry = ctk.CTkEntry(top)
            name_entry.insert(0, item.get('name','') if isinstance(item, dict) else str(item))
            name_entry.pack(fill='x', padx=12)

            lbl2 = ctk.CTkLabel(top, text='Details / Notes:')
            lbl2.pack(anchor='w', pady=(8,2), padx=12)
            details_text = tk.Text(top, height=8)
            details_text.pack(fill='both', expand=True, padx=12, pady=(0,8))
            try:
                details_text.insert('1.0', item.get('details','') if isinstance(item, dict) else '')
            except Exception:
                pass

            def _on_save_details():
                try:
                    new_name = (name_entry.get() or '').strip()
                    new_details = (details_text.get('1.0', 'end') or '').strip()
                    if not new_name:
                        try:
                            tk.messagebox.showwarning('Input Required', 'Please enter a name.')
                        except Exception:
                            pass
                        return
                    items = self.plant_components.setdefault(area_key, [])
                    if model_idx < len(items):
                        items[model_idx]['name'] = new_name
                        items[model_idx]['details'] = new_details
                    else:
                        items.append({'name': new_name, 'details': new_details})
                    self._save_plant_components()
                    self._refresh_area_listbox(area_key)
                except Exception:
                    logger.exception('Failed to save details')
                finally:
                    try:
                        top.destroy()
                    except Exception:
                        pass

            btns = ctk.CTkFrame(top, fg_color='transparent')
            btns.pack(fill='x', pady=8)
            save = ctk.CTkButton(btns, text='Save', command=_on_save_details)
            save.pack(side='left', padx=12)
            cancel = ctk.CTkButton(btns, text='Cancel', command=top.destroy)
            cancel.pack(side='left')
        except Exception:
            logger.exception('Details dialog failed for %s', area_key)

    def _ensure_reports_loaded(self) -> None:
        try:
            from .reports import ReportsFrame
            frame = self.content_frames.get('reports')
            if not frame:
                return
            # Clean placeholder
            for child in frame.winfo_children():
                child.destroy()
            reports_ui = ReportsFrame(frame)
            reports_ui.pack(fill="both", expand=True)
            self.reports_ui = reports_ui
            self._reports_loaded = True
        except Exception:
            pass

    def compute_stats(self, machines: Optional[List[Dict[str, Any]]] = None) -> Dict[str, int]:
        if machines is None:
            machines = self._load_user_machines()
        cfg = settings_ui.load_settings()
        reminder_days = max(1, int(cfg.get("machine_reminder_days", 3) or 3))
        overdue_after_days = max(1, int(cfg.get("machine_overdue_after_days", 2) or 2))
        total = len(machines)
        critical = sum(1 for m in machines if effective_machine_status(m, reminder_days=reminder_days, overdue_after_days=overdue_after_days) == "critical")
        due = sum(1 for m in machines if effective_machine_status(m, reminder_days=reminder_days, overdue_after_days=overdue_after_days) in ("maintenance", "due"))
        overdue = sum(1 for m in machines if effective_machine_status(m, reminder_days=reminder_days, overdue_after_days=overdue_after_days) == "overdue")
        return {"total": total, "critical": critical, "due": due, "overdue": overdue}

    def _dashboard_chip(self, parent: Any, text: str, *, fg: str, text_color: str = "#f8fafc") -> Any:
        chip = ctk.CTkLabel(
            parent,
            text=text,
            font=("Segoe UI Semibold", 12),
            text_color=text_color,
            fg_color=fg,
            corner_radius=8,
            padx=10,
            pady=4,
        )
        chip.pack(side="left", padx=(0, 8))
        return chip

    def _apply_section_theme(self, content_name: str) -> None:
        section = str(content_name or "").strip().lower()
        bg = SECTION_THEME.get(section, {}).get("bg", "#081520")
        try:
            self.configure(fg_color=bg)
        except Exception:
            pass
        try:
            self.main_frame.configure(fg_color=bg)
        except Exception:
            pass

    def _set_logo_on_label(self, widget: Any, logo_path: str, *, fallback_text: str = "Mine Logo") -> None:
        if widget is None:
            return
        if not logo_path or Image is None or not os.path.isfile(logo_path):
            try:
                widget._logo_image = None
                widget.configure(image=None, text=fallback_text)
            except Exception:
                pass
            return
        try:
            image = Image.open(logo_path)
            image.thumbnail((88, 88))
            logo = ctk.CTkImage(light_image=image, dark_image=image, size=image.size)
            widget._logo_image = logo
            widget.configure(image=logo, text="")
        except Exception:
            try:
                widget._logo_image = None
                widget.configure(image=None, text=fallback_text)
            except Exception:
                pass

    def _machine_status_visuals(self, machine: Dict[str, Any]) -> Dict[str, str]:
        try:
            cfg = settings_ui.load_settings()
            reminder_days = max(1, int(cfg.get("machine_reminder_days", 3) or 3))
            overdue_after_days = max(1, int(cfg.get("machine_overdue_after_days", 2) or 2))
            status_info = evaluate_machine_status(
                machine,
                reminder_days=reminder_days,
                overdue_after_days=overdue_after_days,
            )
        except Exception:
            status_info = {"status": str(machine.get("status") or "normal").lower(), "trigger": "manual"}

        status = str(status_info.get("status") or "normal").lower()
        palette = {
            "normal": {"label": "Normal", "color": "#0f766e"},
            "maintenance": {"label": "Maintenance", "color": "#d97706"},
            "due": {"label": "Due", "color": "#dc2626"},
            "overdue": {"label": "Overdue", "color": "#991b1b"},
            "critical": {"label": "Critical", "color": "#7f1d1d"},
        }
        visual = dict(palette.get(status, {"label": status.title() or "Normal", "color": "#334155"}))
        visual["trigger"] = str(status_info.get("trigger") or "manual").lower()
        visual["current_hours"] = status_info.get("current_hours")
        visual["next_due_hours"] = status_info.get("next_due_hours")
        visual["due_date"] = status_info.get("due_date")
        return visual

    def _dashboard_info_card(self, parent: Any, title: str, value: str, subtitle: str, accent: str) -> Any:
        card = ctk.CTkFrame(parent, fg_color="#0f172a", corner_radius=14, border_width=1, border_color="#172031")
        card.pack(side="left", fill="both", expand=True, padx=6)
        ctk.CTkLabel(card, text=title, font=("Segoe UI", 12), text_color="#94a3b8").pack(anchor="w", padx=12, pady=(12, 2))
        ctk.CTkLabel(card, text=value, font=("Segoe UI Semibold", 18), text_color="#f8fafc").pack(anchor="w", padx=12, pady=(0, 2))
        ctk.CTkLabel(card, text=subtitle, font=("Segoe UI", 12), text_color=accent).pack(anchor="w", padx=12, pady=(0, 12))
        return card

    def create_header(self, parent: Optional["CTkFrame"] = None) -> None:
        if parent is None:
            parent = self.main_frame
        hero = GradientPanel(
            parent,
            colors=SECTION_THEME.get("dashboard", {}).get("gradient", getattr(theme_mod, "SECTION_GRADIENTS", {}).get("dashboard", ("#0f172a", "#1d4ed8", "#0891b2"))),
            corner_radius=18,
            border_color="#1d2a3f",
        )
        hero.pack(fill="x", pady=(10, 18), padx=20)
        self.dashboard_hero = hero

        top = ctk.CTkFrame(hero.content, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(16, 8))

        left = ctk.CTkFrame(top, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True)
        ctk.CTkLabel(
            left,
            text=f"Welcome back, {self.user.get('name', 'User')}",
            font=("Segoe UI Semibold", 28),
            text_color="#f8fafc",
        ).pack(anchor="w")
        self._dashboard_subtitle_label = ctk.CTkLabel(
            left,
            text="Monitor the plant, act on due work, and keep operators informed from one control surface.",
            font=("Segoe UI", 13),
            text_color="#94a3b8",
        )
        self._dashboard_subtitle_label.pack(anchor="w", pady=(4, 0))

        right = ctk.CTkFrame(top, fg_color="transparent")
        right.pack(side="right", anchor="n")
        ctk.CTkButton(
            right,
            text="Refresh Dashboard",
            command=self.refresh_ui,
            height=38,
            font=("Segoe UI Semibold", 13),
            fg_color=theme_mod.SIMPLE_PALETTE.get("primary", "#2563eb"),
            hover_color="#1d4ed8",
        ).pack(anchor="e")

        chips = ctk.CTkFrame(hero.content, fg_color="transparent")
        chips.pack(fill="x", padx=16, pady=(0, 16))
        role = str(self.user.get("role", "operator") or "operator").title()
        active_mine = self.get_active_mine_profile() or {}
        self._dashboard_chip(chips, f"Role: {role}", fg="#1e3a8a")
        self._mine_chip = self._dashboard_chip(
            chips,
            f"Mine: {str(active_mine.get('mine_name') or 'Not Configured')}",
            fg="#0f766e" if active_mine.get("mine_name") else "#334155",
        )
        self._dashboard_chip(chips, f"Theme: {self.get_ui_mode().title()}", fg="#0f766e")
        self._dashboard_chip(chips, "Workflow First Navigation", fg="#7c3aed")

        mine_card = ctk.CTkFrame(hero.content, fg_color="#07111d", corner_radius=14, border_width=1, border_color="#1d2a3f")
        mine_card.pack(fill="x", padx=16, pady=(0, 16))
        self._mine_card = mine_card
        top_row = ctk.CTkFrame(mine_card, fg_color="transparent")
        top_row.pack(fill="x", padx=14, pady=(14, 8))
        self._mine_header_title = ctk.CTkLabel(
            top_row,
            text="Mine Context",
            font=("Segoe UI Semibold", 18),
            text_color="#f8fafc",
        )
        self._mine_header_title.pack(side="left")
        ctk.CTkButton(
            top_row,
            text="Manage Mine Details",
            command=self.open_mine_details,
            height=34,
            font=("Segoe UI Semibold", 12),
            fg_color=theme_mod.SIMPLE_PALETTE.get("primary", "#2563eb"),
            hover_color="#1d4ed8",
        ).pack(side="right")

        mine_body = ctk.CTkFrame(mine_card, fg_color="transparent")
        mine_body.pack(fill="x", padx=14, pady=(0, 14))
        mine_body.grid_columnconfigure(1, weight=1)
        self._mine_logo_label = ctk.CTkLabel(
            mine_body,
            text="Mine Logo",
            width=88,
            height=88,
            corner_radius=14,
            fg_color="#0f172a",
            text_color="#94a3b8",
            font=("Segoe UI Semibold", 13),
        )
        self._mine_logo_label.grid(row=0, column=0, rowspan=4, sticky="nw", padx=(0, 14))

        mine_text = ctk.CTkFrame(mine_body, fg_color="transparent")
        mine_text.grid(row=0, column=1, sticky="nsew")
        self._mine_header_line1 = ctk.CTkLabel(
            mine_text,
            text="No mine configured yet.",
            font=("Segoe UI Semibold", 16),
            text_color="#f8fafc",
        )
        self._mine_header_line1.pack(anchor="w")
        self._mine_header_line2 = ctk.CTkLabel(
            mine_text,
            text="Add your mine name, company, quarry type, lease area, address, and Google Maps link to ground the app in the right site.",
            font=("Segoe UI", 12),
            text_color="#94a3b8",
        )
        self._mine_header_line2.pack(anchor="w", pady=(4, 4))
        self._mine_header_line3 = ctk.CTkLabel(
            mine_text,
            text="",
            font=("Segoe UI", 12),
            text_color="#cbd5e1",
        )
        self._mine_header_line3.pack(anchor="w", pady=(0, 4))
        self._mine_header_line4 = ctk.CTkLabel(
            mine_text,
            text="",
            font=("Segoe UI", 12),
            text_color="#93c5fd",
        )
        self._mine_header_line4.pack(anchor="w")
        self._refresh_dashboard_header_context()
        self._restart_mine_card_glow()

    def create_cards(self, parent: Optional["CTkFrame"] = None) -> None:
        if parent is None:
            parent = self.main_frame
        # Start with loading state for fast UI display
        stats = {"total": "Loading...", "critical": "Loading...", "due": "Loading...", "overdue": "Loading..."}

        cards_frame = ctk.CTkFrame(parent, fg_color=theme_mod.SIMPLE_PALETTE.get('card', 'transparent'))
        cards_frame.pack(fill="x", padx=20)

        # Configure responsive grid for cards
        cards_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        # Keep references so we can update counts in-place
        self.cards_frame = cards_frame
        self.card_total = AnimatedCard(cards_frame, "Total Machines", str(stats["total"]), icon="M")
        self.card_total.grid(row=0, column=0, padx=10, pady=10)

        self.card_critical = AnimatedCard(cards_frame, "Critical Machines", str(stats["critical"]), icon="!", color="#F44336")
        self.card_critical.grid(row=0, column=1, padx=10, pady=10)

        self.card_due = AnimatedCard(cards_frame, "Due Tasks", str(stats["due"]), icon="PM", color="#FF9800")
        self.card_due.grid(row=0, column=2, padx=10, pady=10)

        self.card_overdue = AnimatedCard(cards_frame, "Overdue Tasks", str(stats["overdue"]), icon="OD", color="#F44336")
        self.card_overdue.grid(row=0, column=3, padx=10, pady=10)

        # Show loading spinners initially
        try:
            self.card_total.show_spinner()
            self.card_critical.show_spinner()
            self.card_due.show_spinner()
            self.card_overdue.show_spinner()
        except Exception:
            pass

    def create_modern_dashboard_components(self, parent: Optional["CTkFrame"] = None) -> None:
        """Create modern dashboard components with charts and gauges using responsive layout."""
        if parent is None:
            parent = self.main_frame

        modern_frame = ctk.CTkFrame(parent, fg_color=theme_mod.SIMPLE_PALETTE.get('card', 'transparent'))
        modern_frame.pack(fill="x", padx=20, pady=(10, 20))

        modern_frame.grid_columnconfigure(0, weight=1)

        machines_title = ctk.CTkLabel(modern_frame, text="Machines Overview", font=("Segoe UI Semibold", 18), text_color="#f8fafc")
        machines_title.grid(row=0, column=0, sticky="w", pady=(10, 15))

        machines_grid = ctk.CTkFrame(modern_frame, fg_color="transparent")
        machines_grid.grid(row=1, column=0, sticky="ew", pady=(0, 20))
        cols = 3
        for c in range(cols):
            machines_grid.grid_columnconfigure(c, weight=1)

        # Load machines strictly from the shared user-managed store.
        machines = self._load_user_machines()

        if not machines:
            ctk.CTkLabel(
                machines_grid,
                text="No machines added yet. Add your machines in the Machines screen.",
                font=("Segoe UI", 13),
                text_color="#94a3b8",
            ).grid(row=0, column=0, columnspan=cols, sticky="w", padx=8, pady=8)

        def create_card(i, m):
            col = i % cols
            row = i // cols
            status_info = self._machine_status_visuals(m)
            card = ctk.CTkFrame(machines_grid, fg_color="#0f172a", corner_radius=14, border_width=1, border_color="#172031")
            card.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")

            top = ctk.CTkFrame(card, fg_color="transparent")
            top.pack(fill="x", padx=12, pady=(12, 8))
            ctk.CTkLabel(
                top,
                text=f"{m.get('id') or '-'}",
                font=("Segoe UI Semibold", 17),
                text_color="#f8fafc",
            ).pack(side="left")
            ctk.CTkLabel(
                top,
                text=status_info["label"],
                font=("Segoe UI Semibold", 11),
                text_color="#ffffff",
                fg_color=status_info["color"],
                corner_radius=8,
                padx=10,
                pady=4,
            ).pack(side="right")

            ctk.CTkLabel(
                card,
                text=str(m.get("name") or m.get("type") or "Machine"),
                font=("Segoe UI", 13),
                text_color="#cbd5e1",
            ).pack(anchor="w", padx=12)

            runtime = status_info.get("current_hours")
            next_due_hours = status_info.get("next_due_hours")
            due_date = status_info.get("due_date") or (machine_due_date(m).isoformat() if machine_due_date(m) else "")
            trigger = status_info.get("trigger")
            if trigger == "hours" and next_due_hours is not None:
                subtitle = f"Runtime {runtime} h | Due at {next_due_hours} h"
            elif due_date:
                subtitle = f"Due date {due_date}"
            else:
                subtitle = "No active maintenance threshold"

            ctk.CTkLabel(
                card,
                text=subtitle,
                font=("Segoe UI", 12),
                text_color="#94a3b8",
            ).pack(anchor="w", padx=12, pady=(6, 10))

        for i, m in enumerate(machines):
            try:
                self.after(min(200, i * 25), lambda ii=i, mm=m: create_card(ii, mm))
            except Exception:
                create_card(i, m)

        self.create_due_today_panel(modern_frame, row=2)
        # Auto Incident Feed panel removed from dashboard as requested.
        self.create_predictive_risk_panel(modern_frame, row=3)

        status_title = ctk.CTkLabel(modern_frame, text="Operations Snapshot", font=("Segoe UI Semibold", 18), text_color="#f8fafc")
        status_title.grid(row=4, column=0, sticky="w", pady=(8, 12))

        status_frame = ctk.CTkFrame(modern_frame, fg_color="transparent")
        status_frame.grid(row=5, column=0, sticky="ew")

        machines = self._load_user_machines()
        statuses = [self._machine_status_visuals(m)["label"].lower() for m in machines]
        operational_count = sum(1 for status in statuses if status == "normal")
        maintenance_count = sum(1 for status in statuses if status == "maintenance")
        critical_count = sum(1 for status in statuses if status == "critical")
        overdue_count = sum(1 for status in statuses if status == "overdue")

        self._dashboard_info_card(status_frame, "Operational", str(operational_count), "Healthy fleet running", "#86efac")
        self._dashboard_info_card(status_frame, "Maintenance", str(maintenance_count), "Planned interventions pending", "#fbbf24")
        self._dashboard_info_card(status_frame, "Critical", str(critical_count), "Immediate action required", "#f87171")
        self._dashboard_info_card(status_frame, "Overdue", str(overdue_count), "Delayed maintenance items", "#f97316")

    def create_bwe_status(self, parent: Optional["CTkFrame"] = None) -> None:
        if parent is None:
            parent = self.main_frame
        frame = ctk.CTkFrame(parent, corner_radius=16, fg_color=theme_mod.SIMPLE_PALETTE.get("card", "#111827"))
        frame.pack(fill="x", padx=20, pady=(0, 18))
        self._bwe_status_frame = frame

        title = ctk.CTkLabel(frame, text="Plant Status Summary", font=("Segoe UI Semibold", 18), text_color="#f8fafc")
        title.pack(anchor="w", padx=16, pady=(14, 8))

        machines = self._load_user_machines()
        overall_status = "OPERATIONAL"
        effective_statuses = [self._machine_status_visuals(m)["label"].lower() for m in machines]
        if any(status == "critical" for status in effective_statuses):
            overall_status = "CRITICAL"
            color = "#ef4444"
        elif any(status in {"maintenance", "due", "overdue"} for status in effective_statuses):
            overall_status = "MAINTENANCE"
            color = "#f59e0b"
        else:
            color = "#22c55e"

        body = ctk.CTkFrame(frame, fg_color="transparent")
        body.pack(fill="x", padx=16, pady=(0, 14))
        self._dashboard_chip(body, f"Overall: {overall_status}", fg=color)
        self._dashboard_chip(body, f"Machines: {len(machines)}", fg="#0f766e")
        self._dashboard_chip(body, "Live dashboard monitoring", fg="#334155")

    def create_due_today_panel(self, parent: Any, *, row: int) -> None:
        frame = ctk.CTkFrame(parent, fg_color="#0f172a", corner_radius=16, border_width=1, border_color="#172031")
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 20))

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(14, 10))
        ctk.CTkLabel(
            header,
            text="Maintenance Due Today",
            font=("Segoe UI Semibold", 18),
            text_color="#f8fafc",
        ).pack(side="left")
        ctk.CTkLabel(
            header,
            text="Live priority queue from date and runtime rules",
            font=("Segoe UI", 12),
            text_color="#94a3b8",
        ).pack(side="right")

        body = ctk.CTkFrame(frame, fg_color="transparent")
        body.pack(fill="x", padx=16, pady=(0, 14))

        machines = self._load_user_machines()
        focus_rows = []
        for machine in machines:
            visual = self._machine_status_visuals(machine)
            status = visual["label"].lower()
            if status not in {"maintenance", "due", "overdue", "critical"}:
                continue
            focus_rows.append((machine, visual))

        if not focus_rows:
            ctk.CTkLabel(
                body,
                text="No machines are currently due. The system is monitoring date and hour thresholds automatically.",
                font=("Segoe UI", 13),
                text_color="#94a3b8",
            ).pack(anchor="w")
            return

        for machine, visual in focus_rows[:6]:
            row_card = ctk.CTkFrame(body, fg_color="#111827", corner_radius=12)
            row_card.pack(fill="x", pady=4)
            top = ctk.CTkFrame(row_card, fg_color="transparent")
            top.pack(fill="x", padx=12, pady=(10, 4))
            ctk.CTkLabel(
                top,
                text=f"{machine.get('id') or '-'} - {machine.get('name') or machine.get('type') or 'Machine'}",
                font=("Segoe UI Semibold", 14),
                text_color="#f8fafc",
            ).pack(side="left")
            ctk.CTkLabel(
                top,
                text=visual["label"],
                font=("Segoe UI Semibold", 11),
                text_color="#ffffff",
                fg_color=visual["color"],
                corner_radius=8,
                padx=10,
                pady=4,
            ).pack(side="right")

            if visual.get("trigger") == "hours" and visual.get("next_due_hours") is not None:
                detail = f"Runtime trigger: {visual.get('current_hours')} h now, due at {visual.get('next_due_hours')} h"
            else:
                detail = f"Date trigger: due on {visual.get('due_date') or machine.get('next_maintenance') or machine.get('due_date') or 'not set'}"

            ctk.CTkLabel(
                row_card,
                text=detail,
                font=("Segoe UI", 12),
                text_color="#94a3b8",
            ).pack(anchor="w", padx=12, pady=(0, 10))

    def create_incident_feed_panel(self, parent: Any, *, row: int) -> None:
        frame = ctk.CTkFrame(parent, fg_color="#0f172a", corner_radius=16, border_width=1, border_color="#172031")
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 20))

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(14, 10))
        ctk.CTkLabel(
            header,
            text="Auto Incident Feed",
            font=("Segoe UI Semibold", 18),
            text_color="#f8fafc",
        ).pack(side="left")
        ctk.CTkLabel(
            header,
            text="Hour, date, manual, spare, follow-up, checklist, rule-engine, and predictive triggers",
            font=("Segoe UI", 12),
            text_color="#94a3b8",
        ).pack(side="right")

        body = ctk.CTkFrame(frame, fg_color="transparent")
        body.pack(fill="x", padx=16, pady=(0, 14))

        incidents = load_incidents(limit=8)
        if not incidents:
            ctk.CTkLabel(
                body,
                text="No incidents yet. Automation will populate this feed in real time.",
                font=("Segoe UI", 13),
                text_color="#94a3b8",
            ).pack(anchor="w")
            return

        severity_colors = {
            "critical": "#dc2626",
            "warning": "#d97706",
            "info": "#1d4ed8",
        }

        for incident in incidents:
            severity = str(incident.get("severity") or "info").strip().lower()
            trigger = str(incident.get("trigger") or "system").strip().lower()
            stamp = str(incident.get("created_at") or "").replace("T", " ")
            title = str(incident.get("title") or "Incident").strip()
            message = str(incident.get("message") or "").strip()
            machine_id = str(incident.get("machine_id") or "").strip()

            row_card = ctk.CTkFrame(body, fg_color="#111827", corner_radius=12)
            row_card.pack(fill="x", pady=4)

            top = ctk.CTkFrame(row_card, fg_color="transparent")
            top.pack(fill="x", padx=12, pady=(10, 4))
            ctk.CTkLabel(
                top,
                text=f"{title}" + (f" | {machine_id}" if machine_id else ""),
                font=("Segoe UI Semibold", 14),
                text_color="#f8fafc",
            ).pack(side="left")
            ctk.CTkLabel(
                top,
                text=severity.upper(),
                font=("Segoe UI Semibold", 11),
                text_color="#ffffff",
                fg_color=severity_colors.get(severity, "#1d4ed8"),
                corner_radius=8,
                padx=10,
                pady=4,
            ).pack(side="right")

            ctk.CTkLabel(
                row_card,
                text=message or "No message",
                font=("Segoe UI", 12),
                text_color="#cbd5e1",
                wraplength=980,
                justify="left",
            ).pack(anchor="w", padx=12, pady=(0, 4))

            ctk.CTkLabel(
                row_card,
                text=f"{stamp or '-'} | Trigger: {trigger}",
                font=("Segoe UI", 11),
                text_color="#94a3b8",
            ).pack(anchor="w", padx=12, pady=(0, 10))

    def create_predictive_risk_panel(self, parent: Any, *, row: int) -> None:
        frame = ctk.CTkFrame(parent, fg_color="#0f172a", corner_radius=16, border_width=1, border_color="#172031")
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 20))

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(14, 10))
        ctk.CTkLabel(
            header,
            text="Predictive Risk Board",
            font=("Segoe UI Semibold", 18),
            text_color="#f8fafc",
        ).pack(side="left")
        ctk.CTkLabel(
            header,
            text="Rule engine context + risk scores (0-100)",
            font=("Segoe UI", 12),
            text_color="#94a3b8",
        ).pack(side="right")

        body = ctk.CTkFrame(frame, fg_color="transparent")
        body.pack(fill="x", padx=16, pady=(0, 14))

        settings = settings_ui.load_settings()
        machines = self._load_user_machines()
        ranked = rank_machine_risk(
            machines,
            reminder_days=int(settings.get("machine_reminder_days", 3) or 3),
            overdue_after_days=int(settings.get("machine_overdue_after_days", 2) or 2),
        )
        focus = [row for row in ranked if int(row.get("risk_score") or 0) >= 40][:6]
        if not focus:
            ctk.CTkLabel(
                body,
                text="No machine currently crosses the predictive watch threshold.",
                font=("Segoe UI", 13),
                text_color="#94a3b8",
            ).pack(anchor="w")
            return

        level_colors = {
            "critical": "#dc2626",
            "high": "#f97316",
            "watch": "#d97706",
            "normal": "#1d4ed8",
        }
        for row_data in focus:
            machine_id = str(row_data.get("machine_id") or "-")
            machine_name = str(row_data.get("machine_name") or machine_id)
            score = int(row_data.get("risk_score") or 0)
            level = str(row_data.get("risk_level") or "normal").strip().lower()
            reasons = row_data.get("reasons") or []
            reason_text = "; ".join(str(item) for item in reasons[:2]) if reasons else "Risk factors stable."
            due_hint = ""
            if row_data.get("hours_to_due") is not None:
                due_hint = f"Hours to due: {row_data.get('hours_to_due')}"
            elif row_data.get("days_to_due") is not None:
                due_hint = f"Days to due: {row_data.get('days_to_due')}"
            else:
                due_hint = "No due marker available"

            row_card = ctk.CTkFrame(body, fg_color="#111827", corner_radius=12)
            row_card.pack(fill="x", pady=4)
            top = ctk.CTkFrame(row_card, fg_color="transparent")
            top.pack(fill="x", padx=12, pady=(10, 4))
            ctk.CTkLabel(
                top,
                text=f"{machine_id} - {machine_name}",
                font=("Segoe UI Semibold", 14),
                text_color="#f8fafc",
            ).pack(side="left")
            ctk.CTkLabel(
                top,
                text=f"{score} | {level.upper()}",
                font=("Segoe UI Semibold", 11),
                text_color="#ffffff",
                fg_color=level_colors.get(level, "#1d4ed8"),
                corner_radius=8,
                padx=10,
                pady=4,
            ).pack(side="right")

            ctk.CTkLabel(
                row_card,
                text=f"{reason_text}",
                font=("Segoe UI", 12),
                text_color="#cbd5e1",
                wraplength=980,
                justify="left",
            ).pack(anchor="w", padx=12, pady=(0, 4))
            ctk.CTkLabel(
                row_card,
                text=due_hint,
                font=("Segoe UI", 11),
                text_color="#94a3b8",
            ).pack(anchor="w", padx=12, pady=(0, 10))

    def create_machine_list(self, parent: Optional["CTkFrame"] = None) -> None:
        # machine overview removed; placeholder kept to avoid missing-call errors
        self.machines = []
        self.alert_status = ctk.CTkLabel(self.main_frame, text="")

    def _refresh_dashboard_header_context(self) -> None:
        mine = self.get_active_mine_profile()
        if not hasattr(self, "_mine_header_line1"):
            return
        if not mine:
            try:
                self._mine_header_title.configure(text="Mine Context")
                self._mine_header_line1.configure(text="No mine configured yet.")
                self._mine_header_line2.configure(
                    text="Add your mine details before daily operations so the dashboard, reports, and alerts stay tied to the correct site."
                )
                self._mine_header_line3.configure(text="")
                self._mine_header_line4.configure(text="")
                if hasattr(self, "_mine_chip"):
                    self._mine_chip.configure(text="Mine: Not Configured", fg_color="#334155")
                if hasattr(self, "_mine_logo_label"):
                    self._set_logo_on_label(self._mine_logo_label, "", fallback_text="Mine Logo")
                self._dashboard_subtitle_label.configure(
                    text="Monitor the plant, act on due work, and keep operators informed from one control surface."
                )
                self._mine_glow_accent = "#475569"
            except Exception:
                pass
            self._restart_mine_card_glow()
            return

        mine_name = str(mine.get("mine_name") or mine.get("id") or "Configured Mine")
        company_name = str(mine.get("company_name") or "").strip()
        quarry_type = str(mine.get("quarry_type") or "").strip()
        lease_area = str(mine.get("lease_area") or "").strip()
        address = str(mine.get("address") or "").strip()
        logo_path = str(mine.get("logo_path") or "").strip()
        maps_link = str(mine.get("google_maps_link") or "").strip()
        try:
            self._mine_header_title.configure(text="Active Mine")
            if hasattr(self, "_mine_chip"):
                self._mine_chip.configure(text=f"Mine: {mine_name}", fg_color="#0f766e")
            if hasattr(self, "_mine_logo_label"):
                self._set_logo_on_label(self._mine_logo_label, logo_path)
            self._mine_header_line1.configure(
                text=f"{mine_name}" + (f"  |  {company_name}" if company_name else "")
            )
            detail_bits = [part for part in (quarry_type, f"Lease Area: {lease_area}" if lease_area else "") if part]
            self._mine_header_line2.configure(
                text="  |  ".join(detail_bits) if detail_bits else "Mine profile ready for daily operations."
            )
            self._mine_header_line3.configure(
                text=f"Address: {address}" if address else "Address not added yet."
            )
            self._mine_header_line4.configure(
                text=f"Google Maps: {maps_link}" if maps_link else "Google Maps link not added yet."
            )
            self._dashboard_subtitle_label.configure(
                text=f"Current operational site: {mine_name}. Monitor the plant, act on due work, and keep operators informed from one control surface."
            )
            self._mine_glow_accent = "#14b8a6"
        except Exception:
            pass
        self._restart_mine_card_glow()

    def _blend_hex(self, color1: str, color2: str, ratio: float) -> str:
        ratio = max(0.0, min(1.0, float(ratio)))
        try:
            c1 = color1.lstrip("#")
            c2 = color2.lstrip("#")
            r1, g1, b1 = int(c1[0:2], 16), int(c1[2:4], 16), int(c1[4:6], 16)
            r2, g2, b2 = int(c2[0:2], 16), int(c2[2:4], 16), int(c2[4:6], 16)
            r = round(r1 + (r2 - r1) * ratio)
            g = round(g1 + (g2 - g1) * ratio)
            b = round(b1 + (b2 - b1) * ratio)
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return color1

    def _restart_mine_card_glow(self) -> None:
        if getattr(self, "_mine_card_glow_after_id", None):
            try:
                self.after_cancel(self._mine_card_glow_after_id)
            except Exception:
                pass
        self._mine_card_glow_after_id = None
        self._mine_glow_phase = 0
        self._animate_mine_card_glow()

    def _stop_mine_card_glow(self) -> None:
        if getattr(self, "_mine_card_glow_after_id", None):
            try:
                self.after_cancel(self._mine_card_glow_after_id)
            except Exception:
                pass
        self._mine_card_glow_after_id = None

    def _animate_mine_card_glow(self) -> None:
        card = getattr(self, "_mine_card", None)
        if card is None:
            return
        try:
            if not card.winfo_exists():
                return
        except Exception:
            return

        phase = int(getattr(self, "_mine_glow_phase", 0))
        triangle = 1.0 - abs(phase - 12) / 12.0
        intensity = 0.14 + (triangle * 0.24)
        surface_mix = 0.04 + (triangle * 0.06)
        accent = getattr(self, "_mine_glow_accent", "#14b8a6")

        try:
            card.configure(
                border_color=self._blend_hex(self._mine_glow_base, accent, intensity),
                fg_color=self._blend_hex(self._mine_glow_surface, accent, surface_mix),
            )
            if hasattr(self, "_mine_logo_label") and self._mine_logo_label is not None:
                self._mine_logo_label.configure(
                    fg_color=self._blend_hex("#0f172a", accent, 0.05 + (triangle * 0.1))
                )
        except Exception:
            return
        if getattr(self, "current_content", None) != "dashboard":
            self._mine_card_glow_after_id = None
            return

        self._mine_glow_phase = (phase + 1) % 24
        try:
            self._mine_card_glow_after_id = self.after(140, self._animate_mine_card_glow)
        except Exception:
            self._mine_card_glow_after_id = None

    def notify_mines_updated(self) -> None:
        try:
            self._refresh_dashboard_header_context()
        except Exception:
            pass
        try:
            if getattr(self, "current_content", None) == "dashboard":
                self.refresh_ui()
        except Exception:
            pass

    def refresh_ui(self) -> None:
        # reload machines and update list and cards asynchronously
        try:
            self._refresh_dashboard_header_context()
        except Exception:
            pass
        try:
            if getattr(self, "current_content", None) == "dashboard":
                if hasattr(self, "modern_container") and self.modern_container is not None:
                    for child in self.modern_container.winfo_children():
                        try:
                            child.destroy()
                        except Exception:
                            pass
                    self.create_modern_dashboard_components(self.modern_container)
                if hasattr(self, "content_frames") and self.content_frames.get("dashboard") is not None:
                    dashboard_frame = self.content_frames.get("dashboard")
                    if hasattr(self, "_bwe_status_frame") and self._bwe_status_frame is not None:
                        try:
                            self._bwe_status_frame.destroy()
                        except Exception:
                            pass
                    self.create_bwe_status(dashboard_frame)
        except Exception:
            logger.exception("Failed to rebuild dashboard panels during refresh")
        self._load_data_async()

    def get_ui_mode(self) -> str:
        return _normalize_ui_mode(getattr(self, "_ui_mode", _load_ui_mode_setting()))

    def _persist_ui_mode(self, mode: str) -> None:
        mode = _normalize_ui_mode(mode)
        try:
            cfg = settings_ui.load_settings()
            cfg["ui_mode"] = mode
            settings_ui.save_settings(cfg)
        except Exception:
            pass
        try:
            os.environ["UI_MODE"] = mode
        except Exception:
            pass

    def toggle_ui_mode(self) -> str:
        current = self.get_ui_mode()
        next_mode = "light" if current == "dark" else "dark"
        self._ui_mode = _apply_ui_mode(next_mode)
        self._persist_ui_mode(self._ui_mode)
        try:
            if hasattr(self, "sidebar") and self.sidebar is not None:
                self.sidebar.update_theme_toggle_label(self._ui_mode)
        except Exception:
            pass
        try:
            if hasattr(self, "sms_status_label"):
                self.sms_status_label.configure(text=f"Theme changed to {self._ui_mode.title()} mode")
        except Exception:
            pass
        return self._ui_mode

    def open_settings(self) -> None:
        try:
            self.show_content("settings")
            if hasattr(self, "sidebar") and self.sidebar is not None:
                self.sidebar._activate_by_name("Settings")
        except Exception:
            try:
                settings_ui.SettingsWindow(self, dashboard=self)
            except Exception:
                from .settings import SettingsWindow
                SettingsWindow(self, dashboard=self)

    def open_mine_details(self) -> None:
        try:
            self.show_content("mine_details")
            if hasattr(self, "sidebar") and self.sidebar is not None:
                self.sidebar._activate_by_name("Mine Details")
        except Exception:
            pass

    def send_alert_for_selected(self) -> None:
        if not hasattr(self, "machine_listbox") or not hasattr(self, "send_btn"):
            try:
                self.sms_status_label.configure(text="SMS Status: Sending a general fleet alert...")
            except Exception:
                pass
            self._send_sms_to_operators("ALERT: Please review the current plant status.")
            return

        sel = self.machine_listbox.curselection()
        if not sel:
            self.alert_status.configure(text="Select a machine first")
            return
        idx = sel[0]
        machine = self.machines[idx]

        # Check if machine has assigned operator phone
        if machine.get('operator_phone'):
            operators = [{'phone': machine['operator_phone'], 'name': 'Machine Operator'}]
        else:
            # load operators
            ops_file = data_path("operators.json")
            operators = []
            if ops_file.exists():
                with open(ops_file, "r", encoding="utf-8") as f:
                    operators = json.load(f)

        if not operators:
            self.alert_status.configure(text="No operator phone configured for this machine")
            return

        message_template = f"ALERT: Please check {machine.get('id')} ({machine.get('type')})."
        self.alert_status.configure(text="Sending...")
        self.send_btn.configure(state="disabled")

        total = 0
        completed = 0
        success_count = 0
        failure_count = 0

        # prepare list and send async per operator with UI-safe callback
        ops_to_send = [op for op in operators if op.get('phone')]
        total = len(ops_to_send)

        if total == 0:
            self.alert_status.configure(text="No operator phone numbers configured")
            self.send_btn.configure(state="normal")
            return

        def make_callback(op):
            def _cb(result: dict):
                nonlocal completed, success_count, failure_count
                try:
                    if result.get('success'):
                        success_count += 1
                    else:
                        failure_count += 1
                        # record failure detail for retry dialog
                        try:
                            self._last_send_failures.append((op, result))
                        except Exception:
                            self._last_send_failures = [(op, result)]
                except Exception:
                    failure_count += 1
                completed += 1

                # update UI on main thread
                def _update():
                    if completed < total:
                        self.alert_status.configure(text=f"Sending: {completed}/{total} - ok:{success_count} failed:{failure_count}")
                    else:
                        if failure_count:
                            self.alert_status.configure(text=f"Sent: {success_count}/{total} - {failure_count} failed")
                        else:
                            self.alert_status.configure(text=f"Sent: {success_count}/{total}")
                        self.send_btn.configure(state="normal")

                try:
                    self.after(0, _update)
                except Exception:
                    pass

            return _cb

        for op in ops_to_send:
            phone = op.get('phone')
            try:
                msg = message_template.format(**op)
            except Exception:
                msg = message_template
            cb = make_callback(op)
            try:
                default_sms_service.send_async(phone, msg, callback=cb)
            except Exception as e:
                try:
                    logger.exception('send_async scheduling failed')
                except Exception:
                    pass
                # schedule UI update for failure
                try:
                    cb({'success': False, 'error': str(e)})
                except Exception:
                    pass

        # after scheduling all sends, when finished we may show retry dialog
        def _maybe_show_retry():
            # wait until all are complete
            def _wait_then_show():
                # poll completed
                while True:
                    if completed >= total:
                        break
                # now show dialog if failures present
                if getattr(self, '_last_send_failures', None):
                    try:
                        self.after(50, lambda: self._show_send_retry_dialog(self._last_send_failures))
                    except Exception:
                        pass

            # spawn light background wait to avoid blocking UI
            try:
                import threading
                t = threading.Thread(target=_wait_then_show, daemon=True)
                t.start()
            except Exception:
                # fallback: directly check once
                if getattr(self, '_last_send_failures', None):
                    try:
                        self._show_send_retry_dialog(self._last_send_failures)
                    except Exception:
                        pass

        _maybe_show_retry()

    def _show_send_retry_dialog(self, failures: list) -> None:
        """Show a dialog listing failed operator sends and allow retry."""
        try:
            dlg = ctk.CTkToplevel(self)
            dlg.title("Retry failed sends")
            dlg.geometry("560x360")
            dlg.transient(self)
            dlg.grab_set()

            lbl = ctk.CTkLabel(dlg, text=f"{len(failures)} failed sends", font=(None, 14, "bold"))
            lbl.pack(anchor="w", padx=12, pady=(12, 6))

            list_frame = ctk.CTkFrame(dlg)
            list_frame.pack(fill="both", expand=True, padx=12, pady=6)

            # Treeview for richer columns: operator, phone, error, status
            cols = ("operator", "phone", "error", "status")
            tree = ttk.Treeview(list_frame, columns=cols, show='headings', selectmode='extended')
            tree.heading('operator', text='Operator')
            tree.heading('phone', text='Phone')
            tree.heading('error', text='Error')
            tree.heading('status', text='Status')
            tree.column('operator', width=160)
            tree.column('phone', width=120)
            tree.column('error', width=220)
            tree.column('status', width=100)
            tree.pack(fill='both', expand=True, side='left')

            scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
            scrollbar.pack(side="right", fill="y")
            tree.config(yscrollcommand=scrollbar.set)

            # map item ids to operator
            item_map = {}
            for (op, res) in failures:
                name = op.get('name') or op.get('username') or ''
                phone = op.get('phone') or ''
                msg = res.get('error') or res.get('response_text') or str(res.get('response') or '')
                item_id = tree.insert('', 'end', values=(name, phone, msg, 'Failed'))
                item_map[item_id] = op

            btn_frame = ctk.CTkFrame(dlg)
            btn_frame.pack(fill="x", padx=12, pady=8)

            def _retry_selected():
                sel = tree.selection()
                if not sel:
                    return
                to_retry = [item_map[i] for i in sel if i in item_map]
                _do_retry(to_retry, tree, item_map)

            def _retry_all():
                to_retry = [op for op, _ in failures]
                _do_retry(to_retry, tree, item_map)

            def _do_retry(to_retry_ops, tree_widget, item_map_local):
                # disable buttons during retry
                retry_btn.configure(state='disabled')
                retry_all_btn.configure(state='disabled')
                # helper to find tree item ids matching an operator
                def _find_items_for_op(op):
                    return [iid for iid, o in item_map_local.items() if o is op or (o.get('phone') == op.get('phone') and o.get('name') == op.get('name'))]

                # update tree row status when a result arrives
                def _on_result(op, res):
                    try:
                        def _ui_update():
                            items = _find_items_for_op(op)
                            for iid in items:
                                status = 'Success' if res.get('success') else 'Failed'
                                err = '' if res.get('success') else (res.get('error') or res.get('response_text') or '')
                                tree_widget.set(iid, 'status', status)
                                tree_widget.set(iid, 'error', err)
                                if res.get('success'):
                                    # optionally remove successful rows
                                    tree_widget.delete(iid)
                        try:
                            self.after(0, _ui_update)
                        except Exception:
                            _ui_update()
                    except Exception:
                        pass

                # schedule retries using helper to make the flow testable
                schedule_retries(to_retry_ops, default_sms_service, "ALERT: please check", callback=_on_result)

                # re-enable buttons after a short delay to avoid spamming
                def _reenable():
                    try:
                        retry_btn.configure(state='normal')
                        retry_all_btn.configure(state='normal')
                    except Exception:
                        pass

                try:
                    self.after(4000, _reenable)
                except Exception:
                    pass

            retry_btn = ctk.CTkButton(btn_frame, text="Retry Selected", command=_retry_selected)
            retry_btn.pack(side="left", padx=6)
            retry_all_btn = ctk.CTkButton(btn_frame, text="Retry All", command=_retry_all)
            retry_all_btn.pack(side="left", padx=6)
            export_btn = ctk.CTkButton(btn_frame, text="Export Errors", command=lambda: _export_errors(tree))
            export_btn.pack(side="left", padx=6)
            close_btn = ctk.CTkButton(btn_frame, text="Close", command=dlg.destroy)
            close_btn.pack(side="right", padx=6)

            def _export_errors(tree_widget):
                try:
                    path = filedialog.asksaveasfilename(defaultextension='.csv', filetypes=[('CSV', '*.csv')])
                    if not path:
                        return
                    with open(path, 'w', newline='', encoding='utf-8') as f:
                        writer = csv.writer(f)
                        writer.writerow(['operator', 'phone', 'error', 'status'])
                        for iid in tree_widget.get_children():
                            vals = tree_widget.item(iid, 'values')
                            writer.writerow(vals)
                except Exception:
                    logger.exception('Export failed')

        except Exception:
            logger.exception("Failed to show retry dialog")

    def create_sms_controls(self, parent: Optional["CTkFrame"] = None) -> None:
        """Create SMS sending controls for the dashboard."""
        if parent is None:
            parent = self.main_frame

        sms_frame = ctk.CTkFrame(parent, fg_color=theme_mod.SIMPLE_PALETTE.get("card", "#111827"), corner_radius=16)
        sms_frame.pack(fill="x", padx=20, pady=(0, 10))

        sms_title = ctk.CTkLabel(sms_frame, text="SMS Control Center", font=("Segoe UI Semibold", 18), text_color="#f8fafc")
        sms_title.pack(anchor="w", padx=16, pady=(14, 4))
        ctk.CTkLabel(
            sms_frame,
            text="Push critical alerts, maintenance reminders, and fleet-wide notifications to verified operators.",
            font=("Segoe UI", 13),
            text_color="#94a3b8",
        ).pack(anchor="w", padx=16, pady=(0, 12))

        controls_frame = ctk.CTkFrame(sms_frame, fg_color="transparent")
        controls_frame.pack(fill="x", padx=12, pady=(0, 10))

        for _col in (0, 1, 2):
            try:
                controls_frame.grid_columnconfigure(_col, weight=1)
            except Exception:
                pass

        self.send_critical_btn = ctk.CTkButton(
            controls_frame, text="Send Critical Alerts",
            command=self.send_critical_alerts,
            height=44, font=("Segoe UI Semibold", 13), fg_color="#b91c1c", hover_color="#991b1b"
        )
        self.send_critical_btn.grid(row=0, column=0, padx=10, pady=5, sticky="ew")

        self.send_maintenance_btn = ctk.CTkButton(
            controls_frame, text="Send Maintenance Reminders",
            command=self.send_maintenance_reminders,
            height=44, font=("Segoe UI Semibold", 13), fg_color="#d97706", hover_color="#b45309"
        )
        self.send_maintenance_btn.grid(row=0, column=1, padx=10, pady=5, sticky="ew")

        self.send_all_btn = ctk.CTkButton(
            controls_frame, text="Send All Notifications",
            command=self.send_all_notifications,
            height=44, font=("Segoe UI Semibold", 13), fg_color=theme_mod.SIMPLE_PALETTE.get("primary", "#2563eb"), hover_color="#1d4ed8"
        )
        self.send_all_btn.grid(row=0, column=2, padx=10, pady=5, sticky="ew")

        status_frame = ctk.CTkFrame(sms_frame, fg_color="#0f172a", corner_radius=12)
        status_frame.pack(fill="x", padx=16, pady=(4, 14))

        self.sms_status_label = ctk.CTkLabel(
            status_frame, text="SMS Status: Ready",
            font=("Segoe UI", 13),
            text_color="#cbd5e1",
        )
        self.sms_status_label.pack(anchor="w", padx=12, pady=12)

    def send_critical_alerts(self) -> None:
        """Send SMS alerts for critical machines."""
        try:
            self.sms_status_label.configure(text="SMS Status: Sending critical alerts...")
            self.update()

            # Get critical machines
            machines = self._load_user_machines()
            critical_machines = [m for m in machines if (m.get("status") or "").lower() == "critical"]

            if not critical_machines:
                self.sms_status_label.configure(text="SMS Status: No critical machines found")
                return

            # Send SMS to operators
            message = "CRITICAL ALERT: {} machines require immediate attention!".format(len(critical_machines))
            self._send_sms_to_operators(message)

        except Exception as e:
            logger.exception("Failed to send critical alerts")
            self.sms_status_label.configure(text=f"SMS Status: Error - {str(e)}")

    def send_maintenance_reminders(self) -> None:
        """Send maintenance reminder SMS."""
        try:
            self.sms_status_label.configure(text="SMS Status: Sending maintenance reminders...")
            self.update()

            cfg = settings_ui.load_settings()
            reminder_days = max(1, int(cfg.get("machine_reminder_days", 3) or 3))
            overdue_after_days = max(1, int(cfg.get("machine_overdue_after_days", 2) or 2))
            machines = self._load_user_machines()
            due_machines = [
                m for m in machines
                if effective_machine_status(m, reminder_days=reminder_days, overdue_after_days=overdue_after_days) in ("maintenance", "due")
            ]

            if not due_machines:
                self.sms_status_label.configure(text="SMS Status: No maintenance due")
                return

            # Send SMS to operators
            message = "MAINTENANCE REMINDER: {} machines due for maintenance".format(len(due_machines))
            self._send_sms_to_operators(message)

        except Exception as e:
            logger.exception("Failed to send maintenance reminders")
            self.sms_status_label.configure(text=f"SMS Status: Error - {str(e)}")

    def send_all_notifications(self) -> None:
        """Send all types of notifications."""
        try:
            self.sms_status_label.configure(text="SMS Status: Sending all notifications...")
            self.update()

            # Get all machines with issues
            machines = self._load_user_machines()
            issues = []

            critical = [m for m in machines if (m.get("status") or "").lower() == "critical"]
            maintenance = [m for m in machines if (m.get("status") or "").lower() in ("maintenance", "due")]
            overdue = [m for m in machines if (m.get("status") or "").lower() == "overdue"]

            if critical:
                issues.append(f"{len(critical)} critical")
            if maintenance:
                issues.append(f"{len(maintenance)} maintenance due")
            if overdue:
                issues.append(f"{len(overdue)} overdue")

            if not issues:
                self.sms_status_label.configure(text="SMS Status: All systems operational")
                return

            # Send SMS to operators
            message = f"SYSTEM STATUS: {', '.join(issues)} machines need attention"
            self._send_sms_to_operators(message)

        except Exception as e:
            logger.exception("Failed to send all notifications")
            self.sms_status_label.configure(text=f"SMS Status: Error - {str(e)}")

    def _resolve_sms_operators(self) -> List[Dict[str, str]]:
        """Collect valid recipient numbers from API, local file, and machine assignments."""
        recipients_by_phone: Dict[str, Dict[str, str]] = {}

        try:
            for op in collect_sms_recipients(sync_get_operators(active_only=True) or [], source="api"):
                recipients_by_phone.setdefault(op["phone"], op)
        except Exception:
            logger.exception("Failed to load operators from API for dashboard SMS")

        try:
            ops_file = data_path("operators.json")
            if ops_file.exists():
                with open(ops_file, "r", encoding="utf-8") as f:
                    payload = json.load(f) or []
                if isinstance(payload, list):
                    for op in collect_sms_recipients(payload, source="file"):
                        recipients_by_phone.setdefault(op["phone"], op)
        except Exception:
            logger.exception("Failed to load operators.json for dashboard SMS")

        try:
            machine_rows = getattr(self, "machines", None) or self._load_user_machines()
            machine_candidates = [
                {
                    "name": machine.get("operator_name") or machine.get("operator") or "Machine Operator",
                    "operator_phone": machine.get("operator_phone"),
                }
                for machine in machine_rows
                if isinstance(machine, dict)
            ]
            for op in collect_sms_recipients(machine_candidates, source="machines", default_name="Machine Operator"):
                recipients_by_phone.setdefault(op["phone"], op)
        except Exception:
            logger.exception("Failed to collect machine operator phones for dashboard SMS")

        return list(recipients_by_phone.values())

    def _send_sms_to_operators(self, message: str) -> None:
        """Send SMS to all operators."""
        try:
            operators = self._resolve_sms_operators()
            if not operators:
                self.sms_status_label.configure(
                    text="SMS Status: No valid operator numbers found. Update Operators and save."
                )
                return

            stats = {"sent": 0, "failed": 0, "skipped": 0, "total": len(operators)}

            def _make_callback(op):
                def _cb(result):
                    try:
                        if result.get("skipped"):
                            stats["skipped"] += 1
                        elif result.get("success"):
                            stats["sent"] += 1
                        else:
                            stats["failed"] += 1
                    except Exception:
                        stats["failed"] += 1

                    # show provider response briefly if present
                    try:
                        resp = result.get("response_text")
                    except Exception:
                        resp = None

                    # update status label on main thread
                    def _update():
                        try:
                            summary = (
                                f"SMS Status: Sent {stats['sent']}/{stats['total']} "
                                f"(Failed {stats['failed']}, Skipped {stats['skipped']})"
                            )
                            if resp:
                                # show provider response for a short while
                                self.sms_status_label.configure(text=f"SMS Provider: {resp}")
                                try:
                                    self.after(8000, lambda: self.sms_status_label.configure(text=summary))
                                except Exception:
                                    pass
                            else:
                                self.sms_status_label.configure(text=summary)
                        except Exception:
                            pass

                    try:
                        self.after(10, _update)
                    except Exception:
                        _update()

                return _cb

            for op in operators:
                try:
                    default_sms_service.send_async(op["phone"], message, callback=_make_callback(op))
                except Exception as e:
                    logger.error(f"Failed to send SMS to {op['name']}: {e}")
                    stats["failed"] += 1

            # initial status
            try:
                self.sms_status_label.configure(text=f"SMS Status: Sending to {stats['total']} operators...")
            except Exception:
                pass

        except Exception as e:
            logger.exception("Failed to send SMS")
            self.sms_status_label.configure(text=f"SMS Status: Error - {str(e)}")




