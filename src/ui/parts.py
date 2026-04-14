import json
import tkinter as tk
from pathlib import Path

import customtkinter as ctk

try:
    from ..app_paths import data_path
except Exception:
    from app_paths import data_path
from authz import has_role
from .theme import SIMPLE_PALETTE

PALETTE = SIMPLE_PALETTE


class PartsFrame(ctk.CTkFrame):
    """Simple Parts / Wear Items inventory UI (scaffold)."""

    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.data_path = data_path("parts.json")
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        self.parts = []
        self._status_label = None
        self.listbox = None
        self._load()
        self._build()
        self._refresh_list()

    def _load(self):
        try:
            if self.data_path.exists():
                with open(self.data_path, "r", encoding="utf-8") as f:
                    self.parts = json.load(f) or []
            else:
                self.parts = []
        except Exception:
            self.parts = []

    def _save(self):
        try:
            with open(self.data_path, "w", encoding="utf-8") as f:
                json.dump(self.parts, f, indent=2)
        except Exception:
            pass

    def _build(self):
        shell = ctk.CTkFrame(self, fg_color="transparent")
        shell.pack(fill="both", expand=True, padx=18, pady=18)

        header = ctk.CTkFrame(shell, fg_color=PALETTE.get("card", "#111827"), corner_radius=14)
        header.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(
            header,
            text="Spare Parts & Wear Items",
            font=("Segoe UI Semibold", 23),
            text_color="#f8fafc",
        ).pack(anchor="w", padx=14, pady=(12, 2))
        ctk.CTkLabel(
            header,
            text="Track stock, edit quantities, and keep critical wear parts ready.",
            font=("Segoe UI", 13),
            text_color="#94a3b8",
        ).pack(anchor="w", padx=14, pady=(0, 10))

        frame = ctk.CTkFrame(shell, fg_color=PALETTE.get("card", "#0f172a"), corner_radius=14)
        frame.pack(fill="both", expand=True)

        list_card = ctk.CTkFrame(frame, fg_color="#0b1220", corner_radius=12)
        list_card.pack(side="left", fill="both", expand=True, padx=(12, 8), pady=12)

        ctk.CTkLabel(
            list_card,
            text="Inventory",
            font=("Segoe UI Semibold", 16),
            text_color="#e2e8f0",
        ).pack(anchor="w", padx=12, pady=(10, 6))

        self.listbox = tk.Listbox(
            list_card,
            height=12,
            font=("Segoe UI", 13),
            bg="#0b1220",
            fg="#e2e8f0",
            selectbackground="#1d4ed8",
            selectforeground="#f8fafc",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
        )
        self.listbox.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        controls = ctk.CTkFrame(frame, fg_color="#0b1220", corner_radius=12)
        controls.pack(side="left", fill="y", padx=(0, 12), pady=12)

        btn_font = ("Segoe UI Semibold", 13)
        ctk.CTkButton(
            controls,
            text='Add',
            height=34,
            font=btn_font,
            fg_color=PALETTE.get("primary", "#2563eb"),
            hover_color="#1d4ed8",
            command=self._add_dialog,
        ).pack(fill="x", padx=10, pady=(10, 6))
        ctk.CTkButton(
            controls,
            text='Edit',
            height=34,
            font=btn_font,
            fg_color="#0f766e",
            hover_color="#115e59",
            command=self._edit_dialog,
        ).pack(fill="x", padx=10, pady=6)
        ctk.CTkButton(
            controls,
            text='Delete',
            height=34,
            font=btn_font,
            fg_color="#b91c1c",
            hover_color="#991b1b",
            command=self._delete,
        ).pack(fill="x", padx=10, pady=6)

        self._status_label = ctk.CTkLabel(
            shell,
            text="Inventory ready",
            font=("Segoe UI", 13),
            text_color="#94a3b8",
        )
        self._status_label.pack(anchor="w", padx=4, pady=(8, 0))

    def _refresh_list(self):
        if self.listbox is None:
            return
        self.listbox.delete(0, 'end')
        for part in self.parts:
            self.listbox.insert('end', f"{part.get('name')} | Qty: {part.get('quantity_on_hand', 0)}")
        if self._status_label is not None:
            self._status_label.configure(text=f"{len(self.parts)} parts loaded")

    def _open_editor(self, title: str, initial_name: str = "", initial_qty: int = 0):
        result = {"name": None, "qty": None}
        top = ctk.CTkToplevel(self)
        top.title(title)
        top.geometry("380x220")
        panel = ctk.CTkFrame(top, fg_color=PALETTE.get("card", "#111827"), corner_radius=14)
        panel.pack(fill="both", expand=True, padx=12, pady=12)

        ctk.CTkLabel(panel, text="Part Name", font=("Segoe UI", 13)).pack(anchor="w", padx=12, pady=(12, 4))
        name = ctk.CTkEntry(panel, height=36, font=("Segoe UI", 13))
        name.insert(0, initial_name)
        name.pack(fill="x", padx=12, pady=(0, 8))
        ctk.CTkLabel(panel, text="Quantity On Hand", font=("Segoe UI", 13)).pack(anchor="w", padx=12, pady=(4, 4))
        qty = ctk.CTkEntry(panel, height=36, font=("Segoe UI", 13))
        qty.insert(0, str(initial_qty))
        qty.pack(fill="x", padx=12, pady=(0, 10))

        def _save():
            result["name"] = name.get().strip()
            try:
                result["qty"] = int(qty.get())
            except Exception:
                result["qty"] = 0
            top.destroy()

        ctk.CTkButton(panel, text='Save', width=100, height=34, font=("Segoe UI Semibold", 13), command=_save).pack(anchor="w", padx=12, pady=(0, 12))
        self.wait_window(top)
        return result["name"], result["qty"]

    def _add_dialog(self):
        name, qty = self._open_editor("Add Part", "", 0)
        if name:
            self.parts.append({'name': name, 'quantity_on_hand': qty})
            self._save()
            self._refresh_list()
            if self._status_label is not None:
                self._status_label.configure(text=f"Added part: {name}", text_color="#86efac")

    def _edit_dialog(self):
        sel = self.listbox.curselection() if self.listbox is not None else ()
        if not sel:
            return
        idx = sel[0]
        item = self.parts[idx]
        name, qty = self._open_editor("Edit Part", item.get('name', ''), item.get('quantity_on_hand', 0))
        if name:
            item['name'] = name
            item['quantity_on_hand'] = qty
            self._save()
            self._refresh_list()
            if self._status_label is not None:
                self._status_label.configure(text=f"Updated part: {name}", text_color="#93c5fd")

    def _delete(self):
        sel = self.listbox.curselection() if self.listbox is not None else ()
        if not sel:
            return
        idx = sel[0]
        try:
            user = getattr(self, 'dashboard', None) and getattr(self.dashboard, 'user', None)
            if not user or not has_role(user, 'admin'):
                tk.messagebox.showerror('Permission denied', 'Only administrators may delete parts.')
                return
        except Exception:
            tk.messagebox.showerror('Permission denied', 'Unable to verify permissions.')
            return
        try:
            deleted = self.parts[idx].get("name", "part")
            del self.parts[idx]
            self._save()
            self._refresh_list()
            if self._status_label is not None:
                self._status_label.configure(text=f"Deleted part: {deleted}", text_color="#fbbf24")
        except Exception:
            pass
