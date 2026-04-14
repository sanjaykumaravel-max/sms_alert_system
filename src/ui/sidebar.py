import customtkinter as ctk
import logging
import tkinter as tk
from typing import Optional, Callable, Any, TYPE_CHECKING

from .theme import SIMPLE_PALETTE, SECTION_COLORS
from .gradient import GradientPanel

PALETTE = SIMPLE_PALETTE
logger = logging.getLogger(__name__)

NAV_SECTION_KEYS = {
    "Dashboard": "dashboard",
    "Mine Details": "mine_details",
    "Checklist": "checklist",
    "Hour Entry": "hour_entry",
    "Machines": "machines",
    "Plant Maintenance": "plant_maintenance",
    "Schedules": "schedules",
    "Alerts": "alerts",
    "Rule Engine": "rule_engine",
    "Operators": "operators",
    "Operator Records": "operator_records",
    "Maintenance History": "maintenance_history",
    "Reports": "reports",
    "Settings": "settings",
}

if TYPE_CHECKING:
    from customtkinter import CTkFrame
    from __main__ import Dashboard


class Tooltip:
    def __init__(self, widget: Any, text: str) -> None:
        self.widget = widget
        self.text = text
        self.tooltip = None
        widget.bind("<Enter>", self.show_tooltip)
        widget.bind("<Leave>", self.hide_tooltip)

    def show_tooltip(self, event: Any) -> None:
        if self.tooltip:
            return
        x, y = event.x_root + 10, event.y_root + 10
        self.tooltip = tk.Toplevel(self.widget)
        self.tooltip.wm_overrideredirect(True)
        self.tooltip.wm_geometry(f"+{x}+{y}")
        label = tk.Label(self.tooltip, text=self.text, background="#111827", fg="#f8fafc", relief="solid", borderwidth=1)
        label.pack(ipadx=6, ipady=2)

    def hide_tooltip(self, event: Any) -> None:
        if self.tooltip:
            self.tooltip.destroy()
            self.tooltip = None


class Sidebar(ctk.CTkFrame):
    """Primary navigation focused on day-to-day operator workflow."""

    def __init__(self, parent: "CTkFrame", dashboard: "Dashboard" = None) -> None:
        super().__init__(parent, width=240, corner_radius=0, fg_color=PALETTE["bg"])
        self.dashboard = dashboard
        self.active_index: Optional[int] = None
        self.nav_buttons: list[Any] = []
        self._next_row = 1
        self._glow_after_id = None
        self._glow_phase = 0
        self._active_button = None
        self._active_accent = PALETTE.get("primary")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(999, weight=1)

        hero = GradientPanel(
            self,
            colors=("#0f172a", "#1d4ed8", "#0891b2"),
            corner_radius=16,
            border_color="#1d2a3f",
        )
        hero.grid(row=0, column=0, padx=16, pady=(16, 10), sticky="ew")
        hero.content.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            hero.content,
            text="MINING PMS",
            font=("Segoe UI Semibold", 22),
            text_color="#f8fafc",
        )
        title.grid(row=0, column=0, padx=14, pady=(12, 2), sticky="w")

        subtitle = ctk.CTkLabel(
            hero.content,
            text="Task-based operations workspace",
            font=("Segoe UI", 12),
            text_color="#dbeafe",
        )
        subtitle.grid(row=1, column=0, padx=14, pady=(0, 8), sticky="w")

        try:
            role = str(getattr(self.dashboard, "user", {}).get("role", "admin") or "admin").title()
        except Exception:
            role = "Admin"
        role_chip = ctk.CTkLabel(
            hero.content,
            text=f"{role} Access",
            font=("Segoe UI Semibold", 12),
            text_color="#dbeafe",
            fg_color="#0f172a",
            corner_radius=8,
            padx=8,
            pady=4,
        )
        role_chip.grid(row=2, column=0, padx=14, pady=(0, 12), sticky="w")

        nav_label = ctk.CTkLabel(
            self,
            text="Daily Flow",
            font=("Segoe UI Semibold", 12),
            text_color="#64748b",
        )
        nav_label.grid(row=1, column=0, padx=20, pady=(0, 8), sticky="w")

        self._next_row = 2

        # Daily workflow order (left-to-right mental flow made vertical):
        # Monitor -> Inspect -> Log -> Plan -> Notify -> Team -> Analyze
        self.add_nav_button("Dashboard", self.show_dashboard)
        self.add_nav_button("Mine Details", self.show_mine_details)
        self.add_nav_button("Checklist", self.show_checklist)
        self.add_nav_button("Hour Entry", self.show_hour_entry)
        self.add_nav_button("Machines", self.show_machines)
        self.add_nav_button("Plant Maintenance", self.show_plant_maintenance)
        self.add_nav_button("Schedules", self.show_schedules)
        self.add_nav_button("Alerts", self.show_alerts)
        self.add_nav_button("Rule Engine", self.show_rule_engine)
        self.add_nav_button("Operators", self.show_operators)
        self.add_nav_button("Operator Records", self.show_operator_records)
        self.add_nav_button("Maintenance History", self.show_maintenance_history)
        self.add_nav_button("Reports", self.show_reports)
        self.add_nav_button("Settings", self.open_settings, compact=True)

        # Admin nav intentionally removed for now (page is empty).
        # Keep admin backend/UI code in place for future re-enable.

        # Permanently removed from sidebar to reduce visual clutter:
        # Parts, Scheduler.
        self.add_nav_button("Logout", self.logout, compact=True)

    def add_nav_button(self, text: str, command: Callable[[], None], *, compact: bool = False) -> Any:
        row = self._next_row
        self._next_row += 1
        btn = ctk.CTkButton(
            self,
            text=text,
            command=command,
            anchor="w",
            height=42 if compact else 50,
            font=("Segoe UI Semibold", 13 if compact else 15),
            corner_radius=12,
            border_width=1,
            border_color="#172031",
            fg_color="transparent",
            hover_color="#172031",
            text_color="#cbd5e1",
        )
        btn.grid(row=row, column=0, padx=16, pady=4, sticky="ew")

        if text == "Logout":
            try:
                btn.configure(
                    text_color="#fecaca",
                    hover_color="#3f1d1d",
                    border_color="#3f1d1d",
                )
            except Exception:
                pass

        idx = len(self.nav_buttons)
        btn._nav_index = idx
        btn._nav_name = text
        self.nav_buttons.append(btn)
        Tooltip(btn, text)
        return btn

    def _set_active(self, index: Optional[int]) -> None:
        self.active_index = index
        for btn in self.nav_buttons:
            try:
                if getattr(btn, "_nav_index", None) == index:
                    nav_name = str(getattr(btn, "_nav_name", "") or "")
                    section_key = NAV_SECTION_KEYS.get(nav_name, "")
                    accent = SECTION_COLORS.get(section_key, {}).get("accent", PALETTE.get("primary"))
                    self._active_button = btn
                    self._active_accent = accent
                    btn.configure(
                        fg_color=accent,
                        hover_color=accent,
                        border_color=accent,
                        text_color="#ffffff",
                    )
                else:
                    btn.configure(
                        fg_color="transparent",
                        hover_color="#172031",
                        border_color="#172031",
                        text_color="#cbd5e1",
                    )
            except Exception:
                pass
        self._restart_active_glow()

    def _restart_active_glow(self) -> None:
        try:
            if self._glow_after_id is not None:
                self.after_cancel(self._glow_after_id)
        except Exception:
            pass
        self._glow_after_id = None
        self._glow_phase = 0
        self._animate_active_glow()

    def _blend_hex(self, a: str, b: str, t: float) -> str:
        def _rgb(value: str) -> tuple[int, int, int]:
            raw = str(value or "").strip().lstrip("#")
            if len(raw) != 6:
                return (34, 211, 238)
            return tuple(int(raw[i:i + 2], 16) for i in (0, 2, 4))
        ca = _rgb(a)
        cb = _rgb(b)
        mixed = tuple(int(ca[i] + (cb[i] - ca[i]) * t) for i in range(3))
        return "#{:02x}{:02x}{:02x}".format(*mixed)

    def _animate_active_glow(self) -> None:
        btn = self._active_button
        if btn is None:
            return
        try:
            pulse = (self._glow_phase % 6) / 5.0
            if pulse > 0.5:
                pulse = 1.0 - pulse
            pulse = pulse * 2.0
            accent = self._active_accent or PALETTE.get("primary")
            border = self._blend_hex(accent, "#ffffff", 0.12 + (0.22 * pulse))
            hover = self._blend_hex(accent, "#0f172a", 0.10)
            btn.configure(border_color=border, hover_color=hover)
            self._glow_phase += 1
        except Exception:
            return
        try:
            self._glow_after_id = self.after(280, self._animate_active_glow)
        except Exception:
            self._glow_after_id = None

    def _activate_by_name(self, name: str) -> None:
        for btn in self.nav_buttons:
            if getattr(btn, "_nav_name", "") == name:
                self._set_active(getattr(btn, "_nav_index", None))
                return

    def _show(self, content_key: str, nav_name: str) -> None:
        if not self.dashboard:
            return
        try:
            self.dashboard.show_content(content_key)
        except Exception:
            logger.exception("dashboard.show_content('%s') raised", content_key)
        self._activate_by_name(nav_name)

    def show_dashboard(self) -> None:
        self._show("dashboard", "Dashboard")

    def show_machines(self) -> None:
        self._show("machines", "Machines")

    def show_mine_details(self) -> None:
        self._show("mine_details", "Mine Details")

    def show_plant_maintenance(self) -> None:
        self._show("plant_maintenance", "Plant Maintenance")

    def show_operators(self) -> None:
        self._show("operators", "Operators")

    def show_operator_records(self) -> None:
        self._show("operator_records", "Operator Records")

    def show_alerts(self) -> None:
        self._show("alerts", "Alerts")

    def show_rule_engine(self) -> None:
        self._show("rule_engine", "Rule Engine")

    def show_schedules(self) -> None:
        self._show("schedules", "Schedules")

    def show_reports(self) -> None:
        self._show("reports", "Reports")

    def show_maintenance_history(self) -> None:
        self._show("maintenance_history", "Maintenance History")

    def show_hour_entry(self) -> None:
        self._show("hour_entry", "Hour Entry")

    def show_checklist(self) -> None:
        self._show("checklist", "Checklist")

    def show_admin(self) -> None:
        self._show("admin", "Admin")

    def open_settings(self) -> None:
        self._show("settings", "Settings")

    def _theme_label_text(self) -> str:
        mode = "dark"
        try:
            if self.dashboard and hasattr(self.dashboard, "get_ui_mode"):
                mode = str(self.dashboard.get_ui_mode() or "dark").lower()
        except Exception:
            mode = "dark"
        if mode not in ("dark", "light", "system"):
            mode = "dark"
        return f"Theme: {mode.title()}"

    def update_theme_toggle_label(self, mode: Optional[str] = None) -> None:
        if mode is None:
            text = self._theme_label_text()
        else:
            current = str(mode).strip().lower()
            if current not in ("dark", "light", "system"):
                current = "dark"
            text = f"Theme: {current.title()}"
        try:
            if hasattr(self, "theme_toggle_btn") and self.theme_toggle_btn is not None:
                self.theme_toggle_btn.configure(text=text)
        except Exception:
            pass

    def toggle_theme_mode(self) -> None:
        if not self.dashboard:
            return
        try:
            if hasattr(self.dashboard, "toggle_ui_mode"):
                new_mode = self.dashboard.toggle_ui_mode()
                self.update_theme_toggle_label(new_mode)
            else:
                self.update_theme_toggle_label()
        except Exception:
            logger.exception("Failed to toggle theme mode")

    def logout(self) -> None:
        try:
            root = self.winfo_toplevel()

            def on_login_success(user):
                for widget in root.winfo_children():
                    try:
                        widget.destroy()
                    except Exception:
                        pass
                try:
                    from .mine_details import MineSetupFrame
                except Exception:
                    return

                def _open_dashboard(current_user):
                    for child in root.winfo_children():
                        try:
                            child.destroy()
                        except Exception:
                            pass
                    dashboard_cls = self.dashboard.__class__ if self.dashboard is not None else None
                    if dashboard_cls is None:
                        return
                    new_dashboard = dashboard_cls(root, current_user)
                    new_dashboard.pack(fill="both", expand=True)

                mine_setup = MineSetupFrame(
                    root,
                    user=user,
                    on_complete=_open_dashboard,
                )
                mine_setup.pack(fill="both", expand=True)

            # Replace current dashboard with login screen instead of quitting app.
            for widget in root.winfo_children():
                try:
                    widget.destroy()
                except Exception:
                    pass

            from .login import LoginWindow
            login = LoginWindow(root, on_success=on_login_success)
            login.pack(fill="both", expand=True)
        except Exception:
            try:
                self.master.quit()
            except Exception:
                pass
