import json
import tkinter as tk
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from tkinter import messagebox

import customtkinter as ctk

try:
    from ..app_paths import data_path
except Exception:
    from app_paths import data_path
from .theme import SIMPLE_PALETTE
from . import theme as theme_mod
from .gradient import GradientPanel

PALETTE = SIMPLE_PALETTE


class ChecklistFrame(ctk.CTkFrame):
    """Daily inspection checklist with CRUD controls and live monitoring."""

    DEFAULT_ITEMS = [
        "Oil level",
        "Leakage",
        "Hydraulic condition",
        "Filter condition",
        "Noise/Vibration",
    ]

    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.data_path = data_path("checklists.json")
        self.data_path.parent.mkdir(parents=True, exist_ok=True)

        self.entries: List[Dict[str, Any]] = []
        self.template_items: List[str] = []

        self.vars: List[tuple[str, tk.BooleanVar]] = []
        self.item_rows: List[ctk.CTkFrame] = []
        self._selected_index: Optional[int] = None

        self._saved_status = None
        self._progress_label = None
        self._monitor_label = None
        self._live_status_label = None
        self._clock_label = None

        self._checks_rows_container = None
        self.notes = None
        self._edit_item_btn = None
        self._delete_item_btn = None

        self._load()
        self._build()
        self._rebuild_check_rows()
        self._prefill_from_last_entry()
        self._update_progress()
        self._start_clock_tick()

    def _normalize_template(self, items: List[Any]) -> List[str]:
        normalized: List[str] = []
        seen = set()
        for raw in items or []:
            name = str(raw or "").strip()
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(name)
        return normalized or list(self.DEFAULT_ITEMS)

    def _load(self):
        self.entries = []
        self.template_items = list(self.DEFAULT_ITEMS)
        try:
            if not self.data_path.exists():
                return
            with open(self.data_path, "r", encoding="utf-8") as f:
                payload = json.load(f) or []
            if isinstance(payload, dict):
                self.entries = [e for e in (payload.get("entries") or []) if isinstance(e, dict)]
                self.template_items = self._normalize_template(payload.get("template_items") or self.DEFAULT_ITEMS)
            elif isinstance(payload, list):
                # Backward-compatible: older versions stored only entry list.
                self.entries = [e for e in payload if isinstance(e, dict)]
                self.template_items = list(self.DEFAULT_ITEMS)
        except Exception:
            self.entries = []
            self.template_items = list(self.DEFAULT_ITEMS)

    def _save_payload(self):
        payload = {
            "template_items": self._normalize_template(self.template_items),
            "entries": self.entries,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        try:
            with open(self.data_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception:
            pass

    def _build(self):
        shell = ctk.CTkFrame(self, fg_color="transparent")
        shell.pack(fill="both", expand=True, padx=18, pady=18)

        header = GradientPanel(
            shell,
            colors=getattr(theme_mod, "SECTION_GRADIENTS", {}).get("checklist", ("#1a1308", "#b45309", "#f59e0b")),
            corner_radius=16,
            border_color="#3b2410",
        )
        header.pack(fill="x", pady=(0, 12))

        title = ctk.CTkLabel(
            header.content,
            text="Daily Inspection Checklist",
            font=("Segoe UI Semibold", 23),
            text_color="#f8fafc",
        )
        title.pack(anchor="w", padx=14, pady=(12, 2))

        subtitle = ctk.CTkLabel(
            header.content,
            text="Add, edit, delete, and save checklist controls with live monitoring.",
            font=("Segoe UI", 13),
            text_color="#fde68a",
        )
        subtitle.pack(anchor="w", padx=14, pady=(0, 10))

        status_row = ctk.CTkFrame(header.content, fg_color="transparent")
        status_row.pack(fill="x", padx=14, pady=(0, 12))

        self._progress_label = ctk.CTkLabel(
            status_row,
            text="0/0 Complete",
            font=("Segoe UI Semibold", 13),
            text_color="#dbeafe",
            fg_color="#1e3a8a",
            corner_radius=8,
            padx=8,
            pady=4,
        )
        self._progress_label.pack(side="left")

        self._monitor_label = ctk.CTkLabel(
            status_row,
            text="Pending: 0 | Completed: 0 | 0%",
            font=("Segoe UI", 13),
            text_color="#a5f3fc",
        )
        self._monitor_label.pack(side="left", padx=(10, 0))

        self._clock_label = ctk.CTkLabel(
            status_row,
            text="",
            font=("Segoe UI", 13),
            text_color="#cbd5e1",
        )
        self._clock_label.pack(side="right")

        content = ctk.CTkScrollableFrame(
            shell,
            fg_color=PALETTE.get("card", "#0f172a"),
            corner_radius=14,
        )
        content.pack(fill="both", expand=True)

        checks_card = ctk.CTkFrame(content, fg_color="transparent")
        checks_card.pack(fill="x", padx=12, pady=(12, 8))

        checks_header = ctk.CTkFrame(checks_card, fg_color="transparent")
        checks_header.pack(fill="x", pady=(0, 8))

        checks_title = ctk.CTkLabel(
            checks_header,
            text="Checks",
            font=("Segoe UI Semibold", 16),
            text_color="#e2e8f0",
        )
        checks_title.pack(side="left")

        item_actions = ctk.CTkFrame(checks_header, fg_color="transparent")
        item_actions.pack(side="right")

        add_btn = ctk.CTkButton(
            item_actions,
            text="Add",
            width=72,
            height=34,
            command=self._add_item,
            fg_color="#2563eb",
            hover_color="#1d4ed8",
            font=("Segoe UI Semibold", 13),
        )
        add_btn.pack(side="left", padx=(0, 6))

        self._edit_item_btn = ctk.CTkButton(
            item_actions,
            text="Edit",
            width=72,
            height=34,
            command=self._edit_selected_item,
            fg_color="#0f766e",
            hover_color="#115e59",
            font=("Segoe UI Semibold", 13),
        )
        self._edit_item_btn.pack(side="left", padx=6)

        self._delete_item_btn = ctk.CTkButton(
            item_actions,
            text="Delete",
            width=72,
            height=34,
            command=self._delete_selected_item,
            fg_color="#b91c1c",
            hover_color="#991b1b",
            font=("Segoe UI Semibold", 13),
        )
        self._delete_item_btn.pack(side="left", padx=6)

        save_template_btn = ctk.CTkButton(
            item_actions,
            text="Save",
            width=72,
            height=34,
            command=self._save_template,
            fg_color="#7c3aed",
            hover_color="#6d28d9",
            font=("Segoe UI Semibold", 13),
        )
        save_template_btn.pack(side="left", padx=(6, 0))

        self._checks_rows_container = ctk.CTkFrame(checks_card, fg_color="transparent")
        self._checks_rows_container.pack(fill="x")

        monitor_card = ctk.CTkFrame(content, fg_color="#0b1220", corner_radius=10)
        monitor_card.pack(fill="x", padx=12, pady=(8, 8))
        ctk.CTkLabel(
            monitor_card,
            text="Real-Time Monitoring",
            font=("Segoe UI Semibold", 15),
            text_color="#e2e8f0",
        ).pack(anchor="w", padx=12, pady=(10, 4))
        self._live_status_label = ctk.CTkLabel(
            monitor_card,
            text="Live: Ready",
            font=("Segoe UI", 13),
            text_color="#94a3b8",
        )
        self._live_status_label.pack(anchor="w", padx=12, pady=(0, 10))

        notes_card = ctk.CTkFrame(content, fg_color="#0b1220", corner_radius=10)
        notes_card.pack(fill="both", expand=True, padx=12, pady=(8, 12))

        notes_lbl = ctk.CTkLabel(
            notes_card,
            text="Notes",
            font=("Segoe UI Semibold", 16),
            text_color="#e2e8f0",
        )
        notes_lbl.pack(anchor="w", padx=12, pady=(10, 6))

        self.notes = ctk.CTkTextbox(
            notes_card,
            height=150,
            font=("Segoe UI", 14),
            fg_color="#111827",
            border_color="#1f2937",
            border_width=1,
            text_color="#e2e8f0",
        )
        self.notes.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        actions = ctk.CTkFrame(shell, fg_color="transparent")
        actions.pack(fill="x", pady=(12, 0))

        save_entry_btn = ctk.CTkButton(
            actions,
            text="Save Checklist Entry",
            command=self._save_today,
            fg_color=PALETTE.get("primary", "#2563eb"),
            hover_color="#1d4ed8",
            font=("Segoe UI Semibold", 14),
            width=170,
            height=38,
        )
        save_entry_btn.pack(side="left", padx=(0, 8))

        clear_btn = ctk.CTkButton(
            actions,
            text="Clear",
            command=self._clear,
            fg_color="#334155",
            hover_color="#475569",
            font=("Segoe UI Semibold", 14),
            width=96,
            height=38,
        )
        clear_btn.pack(side="left")

        self._saved_status = ctk.CTkLabel(
            actions,
            text="Not saved yet",
            font=("Segoe UI", 13),
            text_color="#94a3b8",
        )
        self._saved_status.pack(side="right")

    def _start_clock_tick(self):
        def _tick():
            try:
                if self._clock_label is not None:
                    self._clock_label.configure(text=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                self.after(1000, _tick)
            except Exception:
                pass

        _tick()

    def _record_live_event(self, message: str, color: str = "#93c5fd"):
        ts = datetime.now().strftime("%H:%M:%S")
        if self._live_status_label is not None:
            self._live_status_label.configure(text=f"Live: {message} ({ts})", text_color=color)

    def _set_action_state(self):
        has_selection = self._selected_index is not None and 0 <= self._selected_index < len(self.template_items)
        state = "normal" if has_selection else "disabled"
        try:
            if self._edit_item_btn is not None:
                self._edit_item_btn.configure(state=state)
            if self._delete_item_btn is not None:
                self._delete_item_btn.configure(state=state)
        except Exception:
            pass

    def _select_row(self, index: Optional[int]):
        if index is None or index < 0 or index >= len(self.item_rows):
            self._selected_index = None
        else:
            self._selected_index = index
        for row_index, row in enumerate(self.item_rows):
            try:
                if self._selected_index == row_index:
                    row.configure(fg_color="#1e293b")
                else:
                    row.configure(fg_color="#0b1220")
            except Exception:
                pass
        self._set_action_state()

    def _bind_row_selection(self, widget: Any, index: int):
        try:
            widget.bind("<Button-1>", lambda _e, i=index: self._select_row(i), add="+")
        except Exception:
            pass

    def _rebuild_check_rows(self, preserve: Optional[Dict[str, bool]] = None):
        previous = preserve
        if previous is None:
            previous = {name: bool(var.get()) for name, var in self.vars}

        self.vars = []
        self.item_rows = []
        self.template_items = self._normalize_template(self.template_items)

        for child in self._checks_rows_container.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass

        for idx, item in enumerate(self.template_items):
            row = ctk.CTkFrame(self._checks_rows_container, fg_color="#0b1220", corner_radius=10)
            row.pack(fill="x", pady=4)

            var = tk.BooleanVar(value=bool(previous.get(item, False)))
            cb = ctk.CTkCheckBox(
                row,
                text=item,
                variable=var,
                command=lambda i=idx: self._on_item_toggle(i),
                font=("Segoe UI", 14),
                text_color="#f1f5f9",
            )
            cb.pack(side="left", padx=12, pady=10)

            tag = ctk.CTkLabel(
                row,
                text="Pending",
                font=("Segoe UI", 11),
                text_color="#fef3c7",
                fg_color="#92400e",
                corner_radius=8,
                padx=8,
                pady=2,
            )
            tag.pack(side="right", padx=12)

            row._status_tag = tag
            row._var = var
            self.item_rows.append(row)
            self.vars.append((item, var))

            self._bind_row_selection(row, idx)
            self._bind_row_selection(cb, idx)
            self._bind_row_selection(tag, idx)

        if self.template_items:
            if self._selected_index is None or self._selected_index >= len(self.template_items):
                self._selected_index = 0
        self._select_row(self._selected_index)
        self._update_progress()

    def _item_dialog(self, title: str, initial: str = "") -> Optional[str]:
        result = {"value": None}

        top = ctk.CTkToplevel(self)
        top.title(title)
        top.geometry("380x160")
        top.transient(self.winfo_toplevel())
        top.grab_set()

        ctk.CTkLabel(top, text="Checklist item name", font=("Segoe UI", 13)).pack(anchor="w", padx=14, pady=(14, 6))
        text_var = tk.StringVar(value=initial)
        entry = ctk.CTkEntry(top, textvariable=text_var, height=34)
        entry.pack(fill="x", padx=14, pady=(0, 12))
        try:
            entry.focus_set()
        except Exception:
            pass

        actions = ctk.CTkFrame(top, fg_color="transparent")
        actions.pack(fill="x", padx=14, pady=(0, 12))

        def _confirm():
            value = str(text_var.get() or "").strip()
            if not value:
                try:
                    messagebox.showwarning("Input Required", "Please enter an item name.")
                except Exception:
                    pass
                return
            result["value"] = value
            try:
                top.destroy()
            except Exception:
                pass

        def _cancel():
            try:
                top.destroy()
            except Exception:
                pass

        ctk.CTkButton(actions, text="Save", width=90, command=_confirm).pack(side="left")
        ctk.CTkButton(actions, text="Cancel", width=90, command=_cancel, fg_color="#334155", hover_color="#475569").pack(
            side="left", padx=(8, 0)
        )

        self.wait_window(top)
        return result["value"]

    def _add_item(self):
        value = self._item_dialog("Add Checklist Item")
        if not value:
            return
        if value.lower() in {it.lower() for it in self.template_items}:
            try:
                messagebox.showwarning("Duplicate", "This checklist item already exists.")
            except Exception:
                pass
            return
        self.template_items.append(value)
        self._selected_index = len(self.template_items) - 1
        self._rebuild_check_rows()
        self._record_live_event(f"Added item: {value}", "#86efac")

    def _edit_selected_item(self):
        if self._selected_index is None or self._selected_index >= len(self.template_items):
            self._record_live_event("No item selected for edit", "#fbbf24")
            return
        current = self.template_items[self._selected_index]
        value = self._item_dialog("Edit Checklist Item", initial=current)
        if not value:
            return
        duplicate = {it.lower() for idx, it in enumerate(self.template_items) if idx != self._selected_index}
        if value.lower() in duplicate:
            try:
                messagebox.showwarning("Duplicate", "Another item already uses that name.")
            except Exception:
                pass
            return
        states = {name: bool(var.get()) for name, var in self.vars}
        states[value] = states.pop(current, False)
        self.template_items[self._selected_index] = value
        self._rebuild_check_rows(preserve=states)
        self._record_live_event(f"Edited item: {current} -> {value}", "#93c5fd")

    def _delete_selected_item(self):
        if self._selected_index is None or self._selected_index >= len(self.template_items):
            self._record_live_event("No item selected for delete", "#fbbf24")
            return
        if len(self.template_items) <= 1:
            self._record_live_event("At least one checklist item is required", "#f87171")
            return
        item = self.template_items[self._selected_index]
        try:
            confirm = messagebox.askyesno("Delete Item", f"Delete '{item}' from checklist template?")
        except Exception:
            confirm = True
        if not confirm:
            return
        states = {name: bool(var.get()) for name, var in self.vars}
        states.pop(item, None)
        del self.template_items[self._selected_index]
        if self._selected_index >= len(self.template_items):
            self._selected_index = len(self.template_items) - 1
        self._rebuild_check_rows(preserve=states)
        self._record_live_event(f"Deleted item: {item}", "#fbbf24")

    def _save_template(self):
        self.template_items = self._normalize_template(self.template_items)
        self._save_payload()
        if self._saved_status is not None:
            self._saved_status.configure(text="Template saved", text_color="#86efac")
        self._record_live_event("Checklist template saved", "#86efac")

    def _on_item_toggle(self, index: int):
        self._select_row(index)
        self._update_progress()
        if 0 <= index < len(self.template_items):
            name, var = self.vars[index]
            status = "OK" if bool(var.get()) else "Pending"
            self._record_live_event(f"{name}: {status}", "#93c5fd")

    def _prefill_from_last_entry(self):
        if not self.entries:
            return
        try:
            last = self.entries[-1]
            values = {it.get("name"): bool(it.get("ok")) for it in last.get("items", []) if isinstance(it, dict)}
            for name, var in self.vars:
                if name in values:
                    var.set(values[name])
            note = str(last.get("notes", "")).strip()
            if note and self.notes is not None:
                self.notes.delete("1.0", "end")
                self.notes.insert("1.0", note)
            ts = last.get("saved_at")
            if ts and self._saved_status is not None:
                self._saved_status.configure(text=f"Loaded last entry ({ts})")
            self._record_live_event("Loaded latest checklist entry", "#a5b4fc")
        except Exception:
            pass

    def _update_progress(self):
        total = len(self.vars)
        completed = sum(1 for _, var in self.vars if bool(var.get()))
        pending = max(0, total - completed)
        pct = int((completed * 100) / total) if total else 0

        if self._progress_label:
            self._progress_label.configure(text=f"{completed}/{total} Complete")
        if self._monitor_label:
            self._monitor_label.configure(text=f"Pending: {pending} | Completed: {completed} | {pct}%")

        for row in self.item_rows:
            try:
                done = bool(row._var.get())
                tag = row._status_tag
                if done:
                    tag.configure(text="OK", fg_color="#14532d", text_color="#dcfce7")
                else:
                    tag.configure(text="Pending", fg_color="#92400e", text_color="#fef3c7")
            except Exception:
                pass

    def _save_today(self):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = {
            "saved_at": ts,
            "items": [{"name": name, "ok": bool(var.get())} for name, var in self.vars],
            "notes": self.notes.get("1.0", "end").strip() if self.notes is not None else "",
        }
        self.entries.append(entry)
        self._save_payload()
        if self._saved_status:
            self._saved_status.configure(text=f"Saved at {ts}", text_color="#86efac")
        self._record_live_event("Checklist entry saved", "#86efac")

    def _clear(self):
        for _, var in self.vars:
            var.set(False)
        try:
            if self.notes is not None:
                self.notes.delete("1.0", "end")
        except Exception:
            pass
        self._update_progress()
        if self._saved_status:
            self._saved_status.configure(text="Cleared (not saved)", text_color="#fbbf24")
        self._record_live_event("Checklist cleared", "#fbbf24")
