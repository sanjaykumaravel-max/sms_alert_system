import os
import pandas as pd
import datetime
import tkinter as tk
import customtkinter as ctk
from pathlib import Path
from shutil import copy2
from .scroll import enable_mousewheel_scroll
from .theme import SIMPLE_PALETTE
from . import theme as theme_mod
from .gradient import GradientPanel

try:
    from ..app_paths import data_path, exports_dir
except Exception:
    from app_paths import data_path, exports_dir

try:
    from ..machine_alert_runner import collect_pending_machine_alerts
    from ..machine_store import load_machines
    from ..settings_store import load_settings
except Exception:
    from machine_alert_runner import collect_pending_machine_alerts
    from machine_store import load_machines
    from settings_store import load_settings

try:
    from authz import has_role
except Exception:
    def has_role(_user, _role):
        return True

ALERTS_FILE = data_path("alerts.xlsx")
LEGACY_ALERTS_FILE = Path(__file__).resolve().parents[1] / "data" / "alerts.xlsx"
DATA_DIR = ALERTS_FILE.parent
SHEET = "Alerts"
PALETTE = SIMPLE_PALETTE


def _blank_alerts_df() -> pd.DataFrame:
    return pd.DataFrame(columns=["timestamp", "level", "message"])


def _load_alerts_df() -> pd.DataFrame:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not ALERTS_FILE.exists() and LEGACY_ALERTS_FILE.exists():
            copy2(LEGACY_ALERTS_FILE, ALERTS_FILE)
        if ALERTS_FILE.exists():
            try:
                return pd.read_excel(ALERTS_FILE, sheet_name=SHEET)
            except Exception:
                return _blank_alerts_df()
        df = _blank_alerts_df()
        _save_alerts_df(df)
        return df
    except Exception:
        return _blank_alerts_df()


def _save_alerts_df(df: pd.DataFrame) -> None:
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        df.to_excel(ALERTS_FILE, sheet_name=SHEET, index=False)
    except Exception as e:
        print("Failed to save alerts:", e)


def _severity_to_level(value: str) -> str:
    raw = str(value or "").strip().lower()
    if raw == "critical":
        return "Critical"
    if raw in {"overdue", "due"}:
        return "Warning"
    if raw == "maintenance":
        return "Info"
    if raw == "warning":
        return "Warning"
    return "Info"


def _machine_status_palette(status: str) -> dict[str, str]:
    raw = str(status or "").strip().lower()
    palette = {
        "normal": {"label": "Normal", "fg": "#0f766e", "soft_fg": "#0b3b34", "text": "#f0fdfa"},
        "maintenance": {"label": "Maintenance", "fg": "#d97706", "soft_fg": "#4a2b08", "text": "#fff7ed"},
        "due": {"label": "Due", "fg": "#dc2626", "soft_fg": "#4c1113", "text": "#fef2f2"},
        "overdue": {"label": "Overdue", "fg": "#991b1b", "soft_fg": "#450a0a", "text": "#fef2f2"},
        "critical": {"label": "Critical", "fg": "#7f1d1d", "soft_fg": "#3f0b0b", "text": "#fef2f2"},
    }
    return dict(palette.get(raw, {"label": raw.title() or "Alert", "fg": "#334155", "soft_fg": "#1e293b", "text": "#e2e8f0"}))


def _live_stage_label(row: dict) -> str:
    role = str(row.get("escalation_role") or "").strip().lower()
    try:
        day = int(row.get("escalation_day"))
    except Exception:
        day = None
    trigger = str(row.get("trigger") or "").strip().lower()

    if trigger == "hours":
        return "Hour-Based Alert"
    if role == "operator" and day == 0:
        return "Due-2 Operator"
    if role == "supervisor" and day == 1:
        return "Due-1 Supervisor"
    if role == "manager" and day == 2:
        return "Due Day Manager"
    if role:
        return role.title()
    return "Machine Alert"


def _stage_chip_colors(row: dict) -> tuple[str, str]:
    status_palette = _machine_status_palette(str(row.get("machine_status") or ""))
    label = str(_live_stage_label(row) or "").strip().lower()
    if "hour-based" in label:
        return "#ccfbf1", "#0f766e"
    return status_palette["text"], status_palette["fg"]


def _trigger_chip_colors(row: dict) -> tuple[str, str]:
    status_palette = _machine_status_palette(str(row.get("machine_status") or ""))
    trigger = str(row.get("trigger") or "").strip().lower()
    if trigger == "hours":
        return "#ccfbf1", "#115e59"
    return status_palette["text"], status_palette["soft_fg"]

class AlertsWindow(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Alerts")
        self.geometry("920x720")
        self.parent = parent

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._load_alerts()

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        header = GradientPanel(
            self,
            colors=getattr(theme_mod, "SECTION_GRADIENTS", {}).get("alerts", ("#220c0c", "#b91c1c", "#f87171")),
            corner_radius=14,
            border_color="#3b1616",
        )
        header.grid(row=0, column=0, padx=12, pady=(12, 8), sticky="ew")
        ctk.CTkLabel(
            header.content,
            text="Alerts",
            font=("Segoe UI Semibold", 22),
            text_color="#f8fafc",
        ).pack(anchor="w", padx=14, pady=(14, 2))
        ctk.CTkLabel(
            header.content,
            text="Track operational alerts, review warning levels, and keep the alert feed clean and visible.",
            font=("Segoe UI", 13),
            text_color="#fecaca",
            wraplength=860,
            justify="left",
        ).pack(anchor="w", padx=14, pady=(0, 12))

        self.container = ctk.CTkScrollableFrame(
            self,
            corner_radius=12,
            fg_color=PALETTE.get("card", "#111827"),
            height=560,
        )
        self.container.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="nsew")
        try:
            enable_mousewheel_scroll(self.container)
        except Exception:
            pass

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=2, column=0, sticky="ew", padx=12, pady=(0,12))
        btn_frame.grid_columnconfigure((0,1,2), weight=1)

        self.add_btn = ctk.CTkButton(btn_frame, text="Add Alert", height=34, font=("Segoe UI Semibold", 13), fg_color=PALETTE.get("primary", "#2563eb"), hover_color="#1d4ed8", command=self._open_add_dialog)
        self.add_btn.grid(row=0, column=0, padx=6, pady=6, sticky="ew")
        self.refresh_btn = ctk.CTkButton(btn_frame, text="Refresh", height=34, font=("Segoe UI Semibold", 13), fg_color="#334155", hover_color="#475569", command=self._refresh_view)
        self.refresh_btn.grid(row=0, column=1, padx=6, pady=6, sticky="ew")
        self.close_btn = ctk.CTkButton(btn_frame, text="Close", height=34, font=("Segoe UI Semibold", 13), fg_color="#334155", hover_color="#475569", command=self.destroy)
        self.close_btn.grid(row=0, column=2, padx=6, pady=6, sticky="ew")

        self._refresh_view()

    def _load_alerts(self):
        self.df = _load_alerts_df()

    def _save_alerts(self):
        _save_alerts_df(self.df)

    def _refresh_view(self):
        for child in self.container.winfo_children():
            child.destroy()

        if self.df.empty:
            lbl = ctk.CTkLabel(self.container, text="No alerts.", anchor="w", font=("Segoe UI", 13), text_color="#94a3b8")
            lbl.pack(fill="x", padx=8, pady=8)
            return

        for idx, row in self.df.iterrows():
            frame = ctk.CTkFrame(self.container, corner_radius=10, fg_color="#0b1220")
            frame.pack(fill="x", padx=6, pady=6)

            left = ctk.CTkFrame(frame, fg_color="transparent")
            left.pack(side="left", fill="both", expand=True, padx=(8,4), pady=8)

            ts = ctk.CTkLabel(left, text=str(row.get("timestamp")), anchor="w", font=("Segoe UI", 12), text_color="#94a3b8")
            ts.pack(fill="x")
            lvl = ctk.CTkLabel(left, text=f"Level: {row.get('level')}", anchor="w", font=("Segoe UI Semibold", 13), text_color="#e2e8f0")
            lvl.pack(fill="x")
            msg = ctk.CTkLabel(left, text=row.get("message"), anchor="w", justify="left", font=("Segoe UI", 13), text_color="#f8fafc")
            msg.pack(fill="x", pady=(4,0))

            btn_frame = ctk.CTkFrame(frame, width=120, fg_color="transparent")
            btn_frame.pack(side="right", padx=8, pady=8)
            del_btn = ctk.CTkButton(btn_frame, text="Delete", width=90, height=34, font=("Segoe UI Semibold", 13), fg_color="#b91c1c",
                                    command=lambda i=idx: self._delete_alert(i))
            del_btn.pack()

    def _delete_alert(self, index):
        # Only admin may delete alerts
        try:
            from authz import has_role
            user = getattr(self, 'winfo_toplevel', None) and getattr(self, 'winfo_toplevel')()
        except Exception:
            user = None
        try:
            # try to read dashboard user if available
            if hasattr(self, 'parent') and getattr(self.parent, 'dashboard', None):
                user = getattr(self.parent.dashboard, 'user', None)
        except Exception:
            pass
        try:
            if not user or not has_role(user, 'admin'):
                tk.messagebox.showerror('Permission denied', 'Only administrators may delete alerts.')
                return
        except Exception:
            tk.messagebox.showerror('Permission denied', 'Unable to verify permissions.')
            return
        self.df = self.df.drop(index).reset_index(drop=True)
        self._save_alerts()
        self._refresh_view()

    def _open_add_dialog(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("Add Alert")
        dlg.geometry("400x220")
        dlg.transient(self)
        dlg.grab_set()

        dlg.grid_rowconfigure((0,1,2,3), weight=1)
        dlg.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(dlg, text="Level:", font=("Segoe UI", 13)).grid(row=0, column=0, padx=12, pady=6, sticky="w")
        level_var = ctk.StringVar(value="Info")
        level_menu = ctk.CTkOptionMenu(dlg, values=["Info", "Warning", "Critical"], variable=level_var)
        level_menu.grid(row=0, column=1, padx=12, pady=6, sticky="ew")

        ctk.CTkLabel(dlg, text="Message:", font=("Segoe UI", 13)).grid(row=1, column=0, padx=12, pady=6, sticky="nw")
        msg_entry = ctk.CTkTextbox(dlg, height=6, font=("Segoe UI", 13))
        msg_entry.grid(row=1, column=1, padx=12, pady=6, sticky="ew")

        def on_add():
            msg = msg_entry.get("0.0", "end").strip()
            if not msg:
                return
            ts = datetime.datetime.now().isoformat(sep=" ", timespec="seconds")
            new = {"timestamp": ts, "level": level_var.get(), "message": msg}
            self.df = pd.concat([self.df, pd.DataFrame([new])], ignore_index=True)
            self._save_alerts()
            dlg.destroy()
            self._refresh_view()

        btn_frame = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_frame.grid(row=3, column=0, columnspan=2, sticky="ew", padx=12, pady=8)
        add_btn = ctk.CTkButton(btn_frame, text="Add", height=34, font=("Segoe UI Semibold", 13), command=on_add)
        add_btn.pack(side="right", padx=6)
        cancel_btn = ctk.CTkButton(btn_frame, text="Cancel", height=34, font=("Segoe UI Semibold", 13), fg_color="#334155", hover_color="#475569", command=dlg.destroy)
        cancel_btn.pack(side="right", padx=6)


class AlertsFrame(ctk.CTkFrame):
    def __init__(self, parent, dashboard=None):
        super().__init__(parent, fg_color="transparent")
        self.parent = parent
        self.dashboard = dashboard
        self.user = getattr(dashboard, "user", None) if dashboard is not None else None
        self.df = _blank_alerts_df()
        self.live_machine_alerts: list[dict] = []
        self.level_filter_var = ctk.StringVar(value="All")
        self.source_filter_var = ctk.StringVar(value="Live Machine")
        self.search_var = ctk.StringVar(value="")
        self.status_var = ctk.StringVar(value="")

        self._load_alerts()

        self.grid_rowconfigure(2, weight=1, minsize=680)
        self.grid_columnconfigure(0, weight=1)

        header = GradientPanel(
            self,
            colors=getattr(theme_mod, "SECTION_GRADIENTS", {}).get("alerts", ("#220c0c", "#b91c1c", "#f87171")),
            corner_radius=14,
            border_color="#3b1616",
        )
        header.grid(row=0, column=0, padx=12, pady=(12, 8), sticky="ew")
        ctk.CTkLabel(
            header.content,
            text="Alerts Feed",
            font=("Segoe UI Semibold", 22),
            text_color="#f8fafc",
        ).pack(anchor="w", padx=14, pady=(14, 2))
        ctk.CTkLabel(
            header.content,
            text="Monitor live machine due alerts and keep manual notices in one fast, focused workspace.",
            font=("Segoe UI", 13),
            text_color="#fecaca",
            wraplength=860,
            justify="left",
        ).pack(anchor="w", padx=14, pady=(0, 6))
        mode = "Administrator edit mode" if self._is_admin() else "View-only mode"
        mode_color = "#22c55e" if self._is_admin() else "#f59e0b"
        ctk.CTkLabel(
            header.content,
            text=mode,
            font=("Segoe UI Semibold", 12),
            text_color="#ffffff",
            fg_color=mode_color,
            corner_radius=8,
            padx=8,
            pady=4,
        ).pack(anchor="w", padx=14, pady=(0, 12))

        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))
        toolbar.grid_columnconfigure(8, weight=1)

        self.add_btn = ctk.CTkButton(
            toolbar,
            text="Add Alert",
            width=110,
            height=36,
            font=("Segoe UI Semibold", 13),
            fg_color=PALETTE.get("primary", "#2563eb"),
            hover_color="#1d4ed8",
            command=self._open_add_dialog,
        )
        self.add_btn.grid(row=0, column=0, padx=(0, 6), pady=4)

        self.refresh_btn = ctk.CTkButton(
            toolbar,
            text="Refresh",
            width=95,
            height=36,
            font=("Segoe UI Semibold", 13),
            fg_color="#334155",
            hover_color="#475569",
            command=self._refresh_view,
        )
        self.refresh_btn.grid(row=0, column=1, padx=6, pady=4)

        self.export_btn = ctk.CTkButton(
            toolbar,
            text="Export CSV",
            width=110,
            height=36,
            font=("Segoe UI Semibold", 13),
            fg_color="#1e3a8a",
            hover_color="#1d4ed8",
            command=self._export_csv,
        )
        self.export_btn.grid(row=0, column=2, padx=6, pady=4)

        self.clear_btn = ctk.CTkButton(
            toolbar,
            text="Clear Manual",
            width=105,
            height=36,
            font=("Segoe UI Semibold", 13),
            fg_color="#7f1d1d",
            hover_color="#991b1b",
            command=self._clear_all,
        )
        self.clear_btn.grid(row=0, column=3, padx=6, pady=4)

        self.level_menu = ctk.CTkOptionMenu(
            toolbar,
            values=["All", "Info", "Warning", "Critical"],
            variable=self.level_filter_var,
            width=120,
            height=36,
            command=lambda _v: self._refresh_view(),
        )
        self.level_menu.grid(row=0, column=4, padx=(10, 6), pady=4)

        self.source_menu = ctk.CTkOptionMenu(
            toolbar,
            values=["Live Machine", "Manual", "All"],
            variable=self.source_filter_var,
            width=130,
            height=36,
            command=lambda _v: self._refresh_view(),
        )
        self.source_menu.grid(row=0, column=5, padx=6, pady=4)

        self.search_entry = ctk.CTkEntry(
            toolbar,
            textvariable=self.search_var,
            width=240,
            height=36,
            font=("Segoe UI", 13),
            placeholder_text="Search message or timestamp",
        )
        self.search_entry.grid(row=0, column=6, padx=6, pady=4, sticky="ew")
        self.search_entry.bind("<KeyRelease>", lambda _e: self._refresh_view())

        self.status_label = ctk.CTkLabel(
            toolbar,
            textvariable=self.status_var,
            font=("Segoe UI", 12),
            text_color="#94a3b8",
        )
        self.status_label.grid(row=0, column=7, padx=(10, 0), pady=4, sticky="e")

        self.container = ctk.CTkScrollableFrame(
            self,
            corner_radius=12,
            fg_color=PALETTE.get("card", "#111827"),
            height=640,
        )
        self.container.grid(row=2, column=0, padx=12, pady=(0, 12), sticky="nsew")
        try:
            enable_mousewheel_scroll(self.container)
        except Exception:
            pass

        if not self._is_admin():
            try:
                self.add_btn.configure(state="disabled")
                self.clear_btn.configure(state="disabled")
            except Exception:
                pass

        self._refresh_view()

    def _is_admin(self) -> bool:
        user = self.user
        try:
            if self.dashboard is not None:
                user = getattr(self.dashboard, "user", user)
        except Exception:
            pass
        if user is None:
            return True
        try:
            return bool(has_role(user, "admin"))
        except Exception:
            return False

    def _set_status(self, text: str, color: str = "#94a3b8") -> None:
        try:
            self.status_var.set(text)
            self.status_label.configure(text_color=color)
        except Exception:
            pass

    def _load_alerts(self):
        self.df = _load_alerts_df()
        try:
            machines = [dict(row) for row in (load_machines() or []) if isinstance(row, dict)]
            self.live_machine_alerts = collect_pending_machine_alerts(
                machines,
                settings=load_settings(),
                now=datetime.datetime.now(),
                persist_state=False,
            )
        except Exception:
            self.live_machine_alerts = []

    def _save_alerts(self):
        _save_alerts_df(self.df)

    def _combined_rows(self) -> list[dict]:
        rows: list[dict] = []
        for idx, row in self.df.iterrows():
            rows.append(
                {
                    "kind": "manual",
                    "manual_index": int(idx),
                    "timestamp": str(row.get("timestamp") or ""),
                    "level": str(row.get("level") or "Info"),
                    "title": "Manual Alert",
                    "message": str(row.get("message") or ""),
                    "source": "manual",
                    "trigger": "manual",
                    "machine_id": "",
                }
            )

        for alert in (self.live_machine_alerts or []):
            if not isinstance(alert, dict):
                continue
            ctx = dict(alert.get("context") or {})
            recipients = [
                str(item.get("phone") or "").strip()
                for item in (alert.get("recipients") or [])
                if isinstance(item, dict) and str(item.get("phone") or "").strip()
            ]
            rows.append(
                {
                    "kind": "live_machine",
                    "timestamp": str(datetime.datetime.now().isoformat(sep=" ", timespec="seconds")),
                    "level": _severity_to_level(str(alert.get("status") or "")),
                    "machine_status": str(alert.get("status") or ""),
                    "title": f"Machine {str(alert.get('status') or 'alert').title()}",
                    "message": str(alert.get("message") or ""),
                    "source": "automation",
                    "trigger": str(ctx.get("trigger") or "machine"),
                    "machine_id": str(alert.get("machine_id") or ""),
                    "recipients_text": ", ".join(recipients),
                    "escalation_role": str(alert.get("escalation_role") or ctx.get("escalation_role") or ""),
                    "escalation_day": alert.get("escalation_day"),
                }
            )

        rows.sort(key=lambda r: str(r.get("timestamp") or ""), reverse=True)
        return rows

    def _filtered_rows(self):
        rows = self._combined_rows()
        level = str(self.level_filter_var.get() or "All").strip().lower()
        source = str(self.source_filter_var.get() or "Live Machine").strip().lower()
        query = str(self.search_var.get() or "").strip().lower()
        out: list[dict] = []
        for row in rows:
            kind = str(row.get("kind") or "").strip().lower()
            if source == "live machine" and kind != "live_machine":
                continue
            if source == "manual" and kind != "manual":
                continue
            row_level = str(row.get("level") or "").strip().lower()
            if level != "all" and row_level != level:
                continue
            if query:
                blob = " ".join(
                    [
                        str(row.get("timestamp") or ""),
                        str(row.get("title") or ""),
                        str(row.get("message") or ""),
                        str(row.get("source") or ""),
                        str(row.get("trigger") or ""),
                        str(row.get("machine_id") or ""),
                        str(row.get("recipients_text") or ""),
                    ]
                ).lower()
                if query not in blob:
                    continue
            out.append(row)
        return out

    def _refresh_view(self):
        for child in self.container.winfo_children():
            child.destroy()

        rows = self._filtered_rows()
        if not rows:
            text = "No alerts match filter." if (not self.df.empty or len(self.live_machine_alerts) > 0) else "No alerts."
            lbl = ctk.CTkLabel(self.container, text=text, anchor="w", font=("Segoe UI", 13), text_color="#94a3b8")
            lbl.pack(fill="x", padx=8, pady=8)
            self._set_status("0 alerts shown", "#94a3b8")
            return

        manual_count = 0
        live_count = 0
        for row in rows:
            frame = ctk.CTkFrame(self.container, corner_radius=10, fg_color="#0b1220")
            frame.pack(fill="x", padx=6, pady=6)

            left = ctk.CTkFrame(frame, fg_color="transparent")
            left.pack(side="left", fill="both", expand=True, padx=(8, 4), pady=8)

            ts = ctk.CTkLabel(left, text=str(row.get("timestamp")), anchor="w", font=("Segoe UI", 12), text_color="#94a3b8")
            ts.pack(fill="x")
            lvl = ctk.CTkLabel(left, text=f"Level: {row.get('level')}", anchor="w", font=("Segoe UI Semibold", 13), text_color="#e2e8f0")
            lvl.pack(fill="x")
            subtitle = str(row.get("title") or "").strip()
            if subtitle:
                ctk.CTkLabel(left, text=subtitle, anchor="w", font=("Segoe UI Semibold", 12), text_color="#cbd5e1").pack(fill="x")
            msg = ctk.CTkLabel(left, text=row.get("message"), anchor="w", justify="left", font=("Segoe UI", 13), text_color="#f8fafc")
            msg.pack(fill="x", pady=(4, 0))
            src = str(row.get("source") or "")
            trig = str(row.get("trigger") or "")
            mid = str(row.get("machine_id") or "")
            details = f"Source: {src} | Trigger: {trig}" + (f" | Machine: {mid}" if mid else "")
            recipients_text = str(row.get("recipients_text") or "").strip()
            escalation_role = str(row.get("escalation_role") or "").strip()
            if recipients_text:
                details += f" | To: {recipients_text}"
            if escalation_role:
                details += f" | Stage: {escalation_role.title()}"
            ctk.CTkLabel(left, text=details, anchor="w", font=("Segoe UI", 11), text_color="#94a3b8").pack(fill="x", pady=(2, 0))

            btn_frame = ctk.CTkFrame(frame, width=220, fg_color="transparent")
            btn_frame.pack(side="right", padx=8, pady=8)
            if str(row.get("kind") or "") == "manual":
                manual_count += 1
                edit_btn = ctk.CTkButton(
                    btn_frame,
                    text="Edit",
                    width=92,
                    height=34,
                    font=("Segoe UI Semibold", 13),
                    fg_color="#334155",
                    hover_color="#475569",
                    command=lambda i=row.get("manual_index"): self._open_edit_dialog(int(i)),
                )
                edit_btn.pack(side="left", padx=(0, 6))
                del_btn = ctk.CTkButton(
                    btn_frame,
                    text="Delete",
                    width=92,
                    height=34,
                    font=("Segoe UI Semibold", 13),
                    fg_color="#b91c1c",
                    hover_color="#991b1b",
                    command=lambda i=row.get("manual_index"): self._delete_alert(int(i)),
                )
                del_btn.pack(side="left")
                if not self._is_admin():
                    try:
                        edit_btn.configure(state="disabled")
                        del_btn.configure(state="disabled")
                    except Exception:
                        pass
            else:
                live_count += 1
                status_palette = _machine_status_palette(str(row.get("machine_status") or ""))
                live_chip = ctk.CTkLabel(
                    btn_frame,
                    text=f"{status_palette['label']} Machine Alert",
                    font=("Segoe UI Semibold", 12),
                    text_color=status_palette["text"],
                    fg_color=status_palette["fg"],
                    corner_radius=8,
                    padx=10,
                    pady=5,
                )
                live_chip.pack(anchor="e", pady=(0, 6))

                stage_label = _live_stage_label(row)
                stage_text_color, stage_fg = _stage_chip_colors(row)
                stage_chip = ctk.CTkLabel(
                    btn_frame,
                    text=stage_label,
                    font=("Segoe UI Semibold", 12),
                    text_color=stage_text_color,
                    fg_color=stage_fg,
                    corner_radius=8,
                    padx=10,
                    pady=5,
                )
                stage_chip.pack(anchor="e", pady=(0, 6))

                trigger = str(row.get("trigger") or "").strip().lower()
                trigger_label = "Date Rule" if trigger == "date" else "Hour Rule" if trigger == "hours" else "Machine Rule"
                trigger_text_color, trigger_fg = _trigger_chip_colors(row)
                trigger_chip = ctk.CTkLabel(
                    btn_frame,
                    text=trigger_label,
                    font=("Segoe UI Semibold", 12),
                    text_color=trigger_text_color,
                    fg_color=trigger_fg,
                    corner_radius=8,
                    padx=10,
                    pady=5,
                )
                trigger_chip.pack(anchor="e")

        self._set_status(f"{len(rows)} alerts shown (manual {manual_count}, live {live_count})", "#94a3b8")

    def _delete_alert(self, index):
        if not self._is_admin():
            tk.messagebox.showerror("Permission denied", "Only administrators may delete alerts.")
            return
        if not tk.messagebox.askyesno("Delete Alert", "Delete this alert from history?"):
            return
        self.df = self.df.drop(index).reset_index(drop=True)
        self._save_alerts()
        self._refresh_view()
        self._set_status("Alert deleted", "#22c55e")

    def _clear_all(self):
        if not self._is_admin():
            tk.messagebox.showerror("Permission denied", "Only administrators may clear alert history.")
            return
        if self.df.empty:
            self._set_status("No manual alerts to clear", "#94a3b8")
            return
        if not tk.messagebox.askyesno("Clear Manual Alerts", "This will remove only manual alerts. Live machine alerts will remain. Continue?"):
            return
        self.df = _blank_alerts_df()
        self._save_alerts()
        self._refresh_view()
        self._set_status("Manual alerts cleared", "#22c55e")

    def _export_csv(self):
        rows = self._combined_rows()
        if not rows:
            tk.messagebox.showinfo("Export Alerts", "No alerts available to export.")
            return
        try:
            out = exports_dir() / f"alerts_export_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            pd.DataFrame(rows).to_csv(out, index=False, encoding="utf-8-sig")
            self._set_status(f"Exported alerts to {out.name}", "#22c55e")
            tk.messagebox.showinfo("Export Alerts", f"Alerts exported:\n{out}")
        except Exception as exc:
            self._set_status(f"Export failed: {exc}", "#ef4444")
            tk.messagebox.showerror("Export Alerts", f"Could not export alerts.\n\n{exc}")

    def _open_add_dialog(self):
        if not self._is_admin():
            tk.messagebox.showerror("Permission denied", "Only administrators may add alerts.")
            return
        self._open_alert_dialog()

    def _open_edit_dialog(self, index: int):
        if not self._is_admin():
            tk.messagebox.showerror("Permission denied", "Only administrators may edit alerts.")
            return
        self._open_alert_dialog(edit_index=index)

    def _open_alert_dialog(self, edit_index: int | None = None):
        dlg = ctk.CTkToplevel(self)
        dlg.title("Edit Alert" if edit_index is not None else "Add Alert")
        dlg.geometry("440x260")
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()

        dlg.grid_rowconfigure((0, 1, 2, 3), weight=1)
        dlg.grid_columnconfigure(1, weight=1)

        current = {}
        if edit_index is not None and 0 <= edit_index < len(self.df):
            try:
                current = self.df.iloc[int(edit_index)].to_dict()
            except Exception:
                current = {}

        ctk.CTkLabel(dlg, text="Level:", font=("Segoe UI", 13)).grid(row=0, column=0, padx=12, pady=8, sticky="w")
        level_var = ctk.StringVar(value=str(current.get("level") or "Info"))
        level_menu = ctk.CTkOptionMenu(dlg, values=["Info", "Warning", "Critical"], variable=level_var, height=36)
        level_menu.grid(row=0, column=1, padx=12, pady=8, sticky="ew")

        ctk.CTkLabel(dlg, text="Message:", font=("Segoe UI", 13)).grid(row=1, column=0, padx=12, pady=8, sticky="nw")
        msg_entry = ctk.CTkTextbox(dlg, height=120, font=("Segoe UI", 13))
        msg_entry.grid(row=1, column=1, padx=12, pady=8, sticky="ew")
        if current.get("message"):
            msg_entry.insert("0.0", str(current.get("message")))

        def on_save():
            msg = msg_entry.get("0.0", "end").strip()
            if not msg:
                tk.messagebox.showerror("Validation", "Message cannot be blank.")
                return
            if edit_index is None:
                ts = datetime.datetime.now().isoformat(sep=" ", timespec="seconds")
                new = {"timestamp": ts, "level": level_var.get(), "message": msg}
                self.df = pd.concat([self.df, pd.DataFrame([new])], ignore_index=True)
                self._set_status("Alert added", "#22c55e")
            else:
                try:
                    self.df.at[int(edit_index), "level"] = level_var.get()
                    self.df.at[int(edit_index), "message"] = msg
                    self._set_status("Alert updated", "#22c55e")
                except Exception:
                    self._set_status("Could not update alert", "#ef4444")
                    tk.messagebox.showerror("Edit Alert", "Could not update the selected alert.")
                    return
            self._save_alerts()
            dlg.destroy()
            self._refresh_view()

        btn_frame = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_frame.grid(row=3, column=0, columnspan=2, sticky="ew", padx=12, pady=8)
        save_text = "Save Changes" if edit_index is not None else "Add Alert"
        add_btn = ctk.CTkButton(btn_frame, text=save_text, height=34, font=("Segoe UI Semibold", 13), command=on_save)
        add_btn.pack(side="right", padx=6)
        cancel_btn = ctk.CTkButton(btn_frame, text="Cancel", height=34, font=("Segoe UI Semibold", 13), fg_color="#334155", hover_color="#475569", command=dlg.destroy)
        cancel_btn.pack(side="right", padx=6)
