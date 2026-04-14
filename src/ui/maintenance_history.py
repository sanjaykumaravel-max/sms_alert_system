from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any, Dict, List

import customtkinter as ctk
import pandas as pd
from tkinter import ttk
from tkinter import messagebox

try:
    from ..app_paths import exports_dir
    from ..machine_store import (
        delete_maintenance_history_entry,
        load_machines,
        machine_history,
        rollback_maintenance_history_entry,
        update_maintenance_history_entry,
    )
except Exception:
    from app_paths import exports_dir
    from machine_store import (
        delete_maintenance_history_entry,
        load_machines,
        machine_history,
        rollback_maintenance_history_entry,
        update_maintenance_history_entry,
    )

from . import theme as theme_mod
from .gradient import GradientPanel
from .dialogs import create_dialog


class MaintenanceHistoryFrame(ctk.CTkFrame):
    def __init__(self, parent, dashboard: object | None = None):
        super().__init__(parent, fg_color="transparent")
        self.dashboard = dashboard
        self._surface = theme_mod.SIMPLE_PALETTE.get("card", "#111827")
        self._surface_alt = "#0b1220"
        self._text_primary = "#e2e8f0"
        self._text_muted = "#94a3b8"
        self._accent = theme_mod.SIMPLE_PALETTE.get("primary", "#2563eb")
        self._rows: List[Dict[str, Any]] = []
        self._display_rows: List[Dict[str, Any]] = []
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        header = GradientPanel(
            self,
            colors=getattr(theme_mod, "SECTION_GRADIENTS", {}).get("maintenance_history", ("#0f172a", "#1d4ed8", "#0891b2")),
            corner_radius=16,
            border_color="#1d2a3f",
        )
        header.pack(fill="x", padx=18, pady=(18, 12))
        ctk.CTkLabel(
            header.content,
            text="Maintenance History",
            font=("Segoe UI Semibold", 24),
            text_color=self._text_primary,
        ).pack(anchor="w", padx=16, pady=(14, 4))
        ctk.CTkLabel(
            header.content,
            text="Review all completed maintenance events in one place across every machine in the app.",
            font=("Segoe UI", 13),
            text_color="#dbeafe",
        ).pack(anchor="w", padx=16, pady=(0, 12))

        controls = ctk.CTkFrame(self, fg_color=self._surface, corner_radius=14)
        controls.pack(fill="x", padx=18, pady=(0, 12))
        controls.grid_columnconfigure(1, weight=1)
        controls.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(controls, text="Search", font=("Segoe UI Semibold", 13), text_color=self._text_primary).grid(row=0, column=0, padx=(14, 10), pady=12, sticky="w")
        self.search_var = ctk.StringVar(value="")
        self.search_entry = ctk.CTkEntry(
            controls,
            textvariable=self.search_var,
            placeholder_text="Search by machine ID, machine name, or completed by",
            font=("Segoe UI", 13),
            height=36,
        )
        self.search_entry.grid(row=0, column=1, padx=(0, 10), pady=12, sticky="ew")
        self.search_entry.bind("<KeyRelease>", lambda _event: self._render())

        ctk.CTkLabel(controls, text="Range", font=("Segoe UI Semibold", 13), text_color=self._text_primary).grid(row=0, column=2, padx=(0, 10), pady=12, sticky="w")
        self.range_menu = ctk.CTkOptionMenu(
            controls,
            values=["All Time", "Last 7 Days", "Last 30 Days", "This Year"],
            command=lambda _value: self._render(),
            height=36,
            font=("Segoe UI", 13),
            fg_color=self._accent,
            button_color="#1e40af",
            button_hover_color="#1d4ed8",
        )
        self.range_menu.grid(row=0, column=3, padx=(0, 14), pady=12, sticky="ew")
        self.range_menu.set("All Time")

        table_wrap = ctk.CTkFrame(self, fg_color=self._surface, corner_radius=16)
        table_wrap.pack(fill="both", expand=True, padx=18, pady=(0, 18))

        summary = ctk.CTkFrame(table_wrap, fg_color="transparent")
        summary.pack(fill="x", padx=12, pady=(12, 6))
        self.summary_label = ctk.CTkLabel(summary, text="0 records", font=("Segoe UI", 12), text_color=self._text_muted)
        self.summary_label.pack(side="left")
        ctk.CTkButton(summary, text="Print View", width=100, height=32, command=self._print_view).pack(side="right", padx=(8, 0))
        ctk.CTkButton(summary, text="Rollback", width=90, height=32, command=self._rollback_selected_record, fg_color="#b45309", hover_color="#92400e").pack(side="right", padx=(8, 0))
        ctk.CTkButton(summary, text="Delete", width=80, height=32, command=self._delete_selected_record, fg_color="#b91c1c", hover_color="#991b1b").pack(side="right", padx=(8, 0))
        ctk.CTkButton(summary, text="Export CSV", width=100, height=32, command=self._export_csv).pack(side="right", padx=(8, 0))
        ctk.CTkButton(summary, text="Export Excel", width=100, height=32, command=self._export_excel).pack(side="right", padx=(8, 0))
        ctk.CTkButton(summary, text="Open Machine", width=110, height=32, command=self._open_selected_machine).pack(side="right", padx=(8, 0))
        ctk.CTkButton(summary, text="Edit Record", width=100, height=32, command=self._edit_selected_record).pack(side="right", padx=(8, 0))
        ctk.CTkButton(summary, text="Refresh", width=90, height=32, command=self.refresh).pack(side="right")

        columns = ("completed_at", "machine_id", "machine_name", "completed_by", "previous_status", "due_severity", "current_hours", "rolled_due_date", "rolled_next_due_hours")
        style = ttk.Style()
        style.configure("MaintHistory.Treeview", font=("Segoe UI", 11), rowheight=30, background=self._surface_alt, fieldbackground=self._surface_alt, foreground=self._text_primary)
        style.configure("MaintHistory.Treeview.Heading", font=("Segoe UI Semibold", 11), background="#1f2937", foreground=self._text_primary)
        style.map("MaintHistory.Treeview", background=[("selected", self._accent)], foreground=[("selected", "#ffffff")])

        self.tree = ttk.Treeview(table_wrap, columns=columns, show="headings", style="MaintHistory.Treeview", height=16)
        headings = {
            "completed_at": "Completed At",
            "machine_id": "Machine ID",
            "machine_name": "Machine",
            "completed_by": "Completed By",
            "previous_status": "Previous Status",
            "due_severity": "Due Severity",
            "current_hours": "Runtime",
            "rolled_due_date": "Next Due Date",
            "rolled_next_due_hours": "Next Due Hours",
        }
        widths = {
            "completed_at": 150,
            "machine_id": 100,
            "machine_name": 180,
            "completed_by": 120,
            "previous_status": 110,
            "due_severity": 110,
            "current_hours": 90,
            "rolled_due_date": 110,
            "rolled_next_due_hours": 110,
        }
        for key in columns:
            self.tree.heading(key, text=headings[key])
            self.tree.column(key, width=widths[key], anchor="w")
        self.tree.tag_configure("sev_normal", foreground="#99f6e4")
        self.tree.tag_configure("sev_maintenance", foreground="#fbbf24")
        self.tree.tag_configure("sev_due", foreground="#f87171")
        self.tree.tag_configure("sev_overdue", foreground="#fb923c")
        self.tree.tag_configure("sev_critical", foreground="#fca5a5")

        yscroll = ttk.Scrollbar(table_wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=(0, 12))
        yscroll.pack(side="right", fill="y", padx=(0, 12), pady=(0, 12))
        self.tree.bind("<Double-1>", lambda _event: self._open_selected_machine())

    def _load_rows(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for machine in load_machines():
            for item in machine_history(machine):
                rows.append(
                    {
                        "event_id": item.get("event_id") or item.get("completed_at") or "",
                        "completed_at": str(item.get("completed_at") or "").replace("T", " "),
                        "machine_id": item.get("machine_id") or machine.get("id") or "",
                        "machine_name": item.get("machine_name") or machine.get("name") or machine.get("model") or "",
                        "completed_by": item.get("completed_by") or "System",
                        "previous_status": str(item.get("previous_status") or "").title(),
                        "due_severity": self._severity_badge(str(item.get("previous_status") or "")),
                        "current_hours": item.get("current_hours") or "",
                        "rolled_due_date": item.get("rolled_due_date") or "",
                        "rolled_next_due_hours": item.get("rolled_next_due_hours") or "",
                        "completion_notes": item.get("completion_notes") or "",
                    }
                )
        rows.sort(key=lambda item: str(item.get("completed_at") or ""), reverse=True)
        return rows

    def _filtered_rows(self) -> List[Dict[str, Any]]:
        rows = list(self._rows)
        query = str(self.search_var.get() or "").strip().lower()
        if query:
            rows = [
                row for row in rows
                if query in str(row.get("machine_id") or "").lower()
                or query in str(row.get("machine_name") or "").lower()
                or query in str(row.get("completed_by") or "").lower()
            ]

        choice = str(self.range_menu.get() or "All Time")
        if choice != "All Time":
            today = datetime.now().date()
            def _within(row: Dict[str, Any]) -> bool:
                raw = str(row.get("completed_at") or "").strip()
                if not raw:
                    return False
                try:
                    dt = datetime.fromisoformat(raw.replace(" ", "T"))
                except Exception:
                    try:
                        dt = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
                    except Exception:
                        return False
                delta = (today - dt.date()).days
                if choice == "Last 7 Days":
                    return 0 <= delta <= 7
                if choice == "Last 30 Days":
                    return 0 <= delta <= 30
                if choice == "This Year":
                    return dt.year == today.year
                return True
            rows = [row for row in rows if _within(row)]
        return rows

    def _render(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        rows = self._filtered_rows()
        self._display_rows = rows
        for idx, row in enumerate(rows):
            severity_key = self._severity_key(row)
            self.tree.insert(
                "",
                "end",
                iid=str(idx),
                tags=(severity_key,),
                values=(
                    row.get("completed_at", ""),
                    row.get("machine_id", ""),
                    row.get("machine_name", ""),
                    row.get("completed_by", ""),
                    f"[{row.get('previous_status', '')}]",
                    f"[{row.get('due_severity', '')}]",
                    row.get("current_hours", ""),
                    row.get("rolled_due_date", ""),
                    row.get("rolled_next_due_hours", ""),
                ),
            )
        self.summary_label.configure(text=f"{len(rows)} maintenance record{'s' if len(rows) != 1 else ''}")

    def refresh(self):
        self._rows = self._load_rows()
        self._render()

    def _selected_row(self) -> Dict[str, Any] | None:
        sel = self.tree.selection()
        if not sel:
            return None
        try:
            return dict(self._display_rows[int(sel[0])])
        except Exception:
            return None

    def _severity_badge(self, status: str) -> str:
        raw = str(status or "normal").strip().lower()
        mapping = {
            "normal": "NORMAL",
            "maintenance": "MAINTENANCE",
            "due": "DUE",
            "overdue": "OVERDUE",
            "critical": "CRITICAL",
        }
        return mapping.get(raw, raw.upper() or "NORMAL")

    def _severity_key(self, row: Dict[str, Any]) -> str:
        raw = str(row.get("previous_status") or "normal").strip().lower()
        return {
            "normal": "sev_normal",
            "maintenance": "sev_maintenance",
            "due": "sev_due",
            "overdue": "sev_overdue",
            "critical": "sev_critical",
        }.get(raw, "sev_normal")

    def _export_csv(self):
        rows = self._filtered_rows()
        if not rows:
            messagebox.showinfo("Export", "No maintenance history rows available to export.")
            return
        output = exports_dir() / f"maintenance_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        pd.DataFrame(rows).to_csv(output, index=False)
        messagebox.showinfo("Export Complete", f"Maintenance history CSV saved to:\n{output}")

    def _export_excel(self):
        rows = self._filtered_rows()
        if not rows:
            messagebox.showinfo("Export", "No maintenance history rows available to export.")
            return
        output = exports_dir() / f"maintenance_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        pd.DataFrame(rows).to_excel(output, index=False)
        messagebox.showinfo("Export Complete", f"Maintenance history Excel saved to:\n{output}")

    def _print_view(self):
        rows = self._filtered_rows()
        if not rows:
            messagebox.showinfo("Print View", "No maintenance history rows available to print.")
            return
        output = exports_dir() / f"maintenance_history_print_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        table_rows = []
        for row in rows:
            table_rows.append(
                "<tr>"
                f"<td>{escape(str(row.get('completed_at','')))}</td>"
                f"<td>{escape(str(row.get('machine_id','')))}</td>"
                f"<td>{escape(str(row.get('machine_name','')))}</td>"
                f"<td>{escape(str(row.get('completed_by','')))}</td>"
                f"<td>{escape(str(row.get('previous_status','')))}</td>"
                f"<td>{escape(str(row.get('due_severity','')))}</td>"
                f"<td>{escape(str(row.get('current_hours','')))}</td>"
                f"<td>{escape(str(row.get('rolled_due_date','')))}</td>"
                f"<td>{escape(str(row.get('rolled_next_due_hours','')))}</td>"
                "</tr>"
            )
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Maintenance History Print View</title>
  <style>
    body {{ font-family: "Segoe UI", Arial, sans-serif; background: #e2e8f0; margin: 0; color: #0f172a; }}
    .page {{ max-width: 1180px; margin: 28px auto; background: #fff; border-radius: 22px; overflow: hidden; box-shadow: 0 24px 60px rgba(15,23,42,.14); }}
    .hero {{ background: linear-gradient(135deg, #0f172a, #1d4ed8); color: #fff; padding: 28px 34px; }}
    .hero h1 {{ margin: 0 0 8px; font-size: 30px; }}
    .hero p {{ margin: 0; color: rgba(255,255,255,.82); }}
    .content {{ padding: 24px 34px 30px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; table-layout: fixed; }}
    th, td {{ border: 1px solid #dbe2ea; padding: 10px 12px; text-align: left; vertical-align: top; overflow-wrap: anywhere; word-break: break-word; }}
    th {{ background: #eff6ff; color: #1e3a8a; }}
    tr:nth-child(even) td {{ background: #f8fafc; }}
    @media print {{ body {{ background: #fff; }} .page {{ margin: 0; box-shadow: none; border-radius: 0; }} }}
  </style>
</head>
<body>
  <div class="page">
    <div class="hero">
      <h1>Maintenance History</h1>
      <p>Generated {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} from the current filtered app view.</p>
    </div>
    <div class="content">
      <table>
        <thead>
          <tr>
            <th>Completed At</th>
            <th>Machine ID</th>
            <th>Machine</th>
            <th>Completed By</th>
            <th>Previous Status</th>
            <th>Due Severity</th>
            <th>Runtime</th>
            <th>Next Due Date</th>
            <th>Next Due Hours</th>
          </tr>
        </thead>
        <tbody>
          {''.join(table_rows)}
        </tbody>
      </table>
    </div>
  </div>
</body>
</html>"""
        output.write_text(html, encoding="utf-8")
        messagebox.showinfo("Print View Ready", f"Printable maintenance history saved to:\n{output}")

    def _open_selected_machine(self):
        row = self._selected_row()
        if not row:
            messagebox.showinfo("Open Machine", "Please select a maintenance history record first.")
            return
        if not self.dashboard:
            return
        machine_id = str(row.get("machine_id") or "").strip()
        if not machine_id:
            messagebox.showerror("Open Machine", "The selected history row does not have a machine ID.")
            return
        try:
            self.dashboard.show_content("machines")
            if hasattr(self.dashboard, "sidebar") and self.dashboard.sidebar is not None:
                self.dashboard.sidebar._activate_by_name("Machines")
            machines_ui = getattr(self.dashboard, "machines_ui", None)
            if machines_ui is not None and hasattr(machines_ui, "select_machine"):
                machines_ui.select_machine(machine_id)
        except Exception:
            messagebox.showerror("Open Machine", "Could not open the machine details view.")

    def _edit_selected_record(self):
        row = self._selected_row()
        if not row:
            messagebox.showinfo("Edit Record", "Please select a maintenance history record first.")
            return

        dlg, dlg_destroy = create_dialog(self, title="Edit Maintenance Record", width=560, height=430)
        dlg.grid_columnconfigure(1, weight=1)
        fields = [
            ("Completed At", "completed_at"),
            ("Completed By", "completed_by"),
            ("Previous Status", "previous_status"),
            ("Runtime At Service", "current_hours"),
            ("Next Due Date", "rolled_due_date"),
            ("Next Due Hours", "rolled_next_due_hours"),
            ("Notes", "completion_notes"),
        ]
        vars_map = {}
        for idx, (label, key) in enumerate(fields):
            ctk.CTkLabel(dlg, text=label, font=("Segoe UI", 13)).grid(row=idx, column=0, padx=12, pady=8, sticky="w")
            value = ctk.StringVar(value=str(row.get(key) or ""))
            entry = ctk.CTkEntry(dlg, textvariable=value, font=("Segoe UI", 13), height=34)
            entry.grid(row=idx, column=1, padx=12, pady=8, sticky="ew")
            vars_map[key] = value

        def _save():
            completed_at_raw = vars_map["completed_at"].get().strip()
            if completed_at_raw:
                try:
                    datetime.fromisoformat(completed_at_raw.replace(" ", "T"))
                except Exception:
                    messagebox.showerror("Edit Record", "Completed At must be a valid date/time.")
                    return
            payload = {
                "completed_at": completed_at_raw.replace(" ", "T"),
                "completed_by": vars_map["completed_by"].get().strip(),
                "previous_status": vars_map["previous_status"].get().strip().lower(),
                "current_hours": vars_map["current_hours"].get().strip(),
                "rolled_due_date": vars_map["rolled_due_date"].get().strip(),
                "rolled_next_due_hours": vars_map["rolled_next_due_hours"].get().strip(),
                "completion_notes": vars_map["completion_notes"].get().strip(),
            }
            updated = update_maintenance_history_entry(
                str(row.get("machine_id") or ""),
                str(row.get("event_id") or ""),
                payload,
            )
            if updated is None:
                messagebox.showerror("Edit Record", "Could not save the maintenance history update.")
                return
            try:
                dlg_destroy()
            except Exception:
                pass
            self._sync_related_views()
            self.refresh()
            messagebox.showinfo("Maintenance History", "Maintenance completion log updated successfully.")

        actions = ctk.CTkFrame(dlg, fg_color="transparent")
        actions.grid(row=len(fields), column=0, columnspan=2, sticky="ew", padx=12, pady=12)
        ctk.CTkButton(actions, text="Save", width=100, command=_save).pack(side="right", padx=6)
        ctk.CTkButton(actions, text="Cancel", width=100, command=dlg_destroy, fg_color="#334155", hover_color="#475569").pack(side="right", padx=6)

    def _delete_selected_record(self):
        row = self._selected_row()
        if not row:
            messagebox.showinfo("Delete Record", "Please select a maintenance history record first.")
            return
        if not messagebox.askyesno("Delete Record", "Delete this maintenance history record from the machine log?"):
            return
        updated = delete_maintenance_history_entry(str(row.get("machine_id") or ""), str(row.get("event_id") or ""))
        if updated is None:
            messagebox.showerror("Delete Record", "Could not delete the selected maintenance history row.")
            return
        self._sync_related_views()
        self.refresh()
        messagebox.showinfo("Maintenance History", "Maintenance history record deleted.")

    def _rollback_selected_record(self):
        row = self._selected_row()
        if not row:
            messagebox.showinfo("Rollback", "Please select a maintenance history record first.")
            return
        if not messagebox.askyesno(
            "Rollback Completion",
            "Rollback will restore the machine state from this completion entry and remove it from history.\n\nUse this only for the latest wrong completion record.",
        ):
            return
        updated = rollback_maintenance_history_entry(str(row.get("machine_id") or ""), str(row.get("event_id") or ""))
        if updated is None:
            messagebox.showerror("Rollback", "Rollback is only available for the latest maintenance completion record of a machine.")
            return
        self._sync_related_views()
        self.refresh()
        messagebox.showinfo("Maintenance History", "Maintenance completion was rolled back successfully.")

    def _sync_related_views(self):
        try:
            if self.dashboard is not None:
                machines_ui = getattr(self.dashboard, "machines_ui", None)
                if machines_ui is not None:
                    machines_ui._load_machines()
                    machines_ui._refresh_view()
                reports_ui = getattr(self.dashboard, "reports_ui", None)
                if reports_ui is not None:
                    reports_ui._refresh_overview()
        except Exception:
            pass
