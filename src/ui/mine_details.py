from __future__ import annotations

import webbrowser
from typing import Any, Callable, Dict, List, Optional

import customtkinter as ctk
from tkinter import messagebox, ttk

try:
    from ..mine_store import get_active_mine, get_active_mine_id, load_mines, save_mines, set_active_mine
except Exception:
    from mine_store import get_active_mine, get_active_mine_id, load_mines, save_mines, set_active_mine

from . import theme as theme_mod
from .gradient import GradientPanel
from .scroll import enable_mousewheel_scroll
from .validation import validate_required


def _valid_google_maps_link(value: str) -> bool:
    raw = str(value or "").strip().lower()
    if not raw:
        return True
    return (
        "google.com/maps" in raw
        or "maps.app.goo.gl" in raw
        or "goo.gl/maps" in raw
    )


class MineDetailsFrame(ctk.CTkFrame):
    def __init__(
        self,
        parent,
        dashboard: object | None = None,
        on_state_change: Optional[Callable[[], None]] = None,
    ):
        super().__init__(parent, fg_color="transparent")
        self.dashboard = dashboard
        self.on_state_change = on_state_change
        self._surface = "#060d19"
        self._surface_alt = "#050a14"
        self._text_primary = "#f1f5f9"
        self._text_muted = "#9fb0c9"
        self._accent = "#22d3ee"
        self._rows: List[Dict[str, Any]] = []
        self._selected_mine_id: str = ""
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        hero = GradientPanel(
            self,
            colors=getattr(theme_mod, "SECTION_GRADIENTS", {}).get("mine_details", ("#0f172a", "#1d4ed8", "#0891b2")),
            corner_radius=18,
            border_color="#1d2a3f",
        )
        hero.pack(fill="x", padx=18, pady=(18, 12))
        ctk.CTkLabel(
            hero.content,
            text="Mine Details",
            font=("Segoe UI Semibold", 24),
            text_color=self._text_primary,
        ).pack(anchor="w", padx=18, pady=(16, 4))
        ctk.CTkLabel(
            hero.content,
            text="Set up the active mine profile once, manage multiple mines, and keep the dashboard tied to the correct site.",
            font=("Segoe UI", 13),
            text_color="#dbeafe",
        ).pack(anchor="w", padx=18, pady=(0, 14))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        body.grid_columnconfigure(0, weight=5)
        body.grid_columnconfigure(1, weight=7)
        body.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(body, fg_color=self._surface, corner_radius=16, border_width=1, border_color="#15243b")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 4), pady=0)
        right = ctk.CTkFrame(body, fg_color=self._surface, corner_radius=16, border_width=1, border_color="#15243b")
        right.grid(row=0, column=1, sticky="nsew", padx=(4, 0), pady=0)

        self.summary_label = ctk.CTkLabel(left, text="0 mines", font=("Segoe UI", 12), text_color=self._text_muted)
        self.summary_label.pack(anchor="w", padx=16, pady=(16, 6))

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(
            "MineDetails.Treeview",
            font=("Segoe UI", 12),
            rowheight=34,
            background=self._surface_alt,
            fieldbackground=self._surface_alt,
            foreground=self._text_primary,
            borderwidth=0,
            relief="flat",
        )
        style.configure(
            "MineDetails.Treeview.Heading",
            font=("Segoe UI Semibold", 12),
            background="#0f172a",
            foreground=self._text_primary,
            borderwidth=0,
            relief="flat",
            padding=(8, 8),
        )
        style.map("MineDetails.Treeview", background=[("selected", self._accent)], foreground=[("selected", "#ffffff")])
        style.map("MineDetails.Treeview.Heading", background=[("active", "#17233a")], foreground=[("active", "#ffffff")])

        columns = ("mine_name", "company_name", "quarry_type", "lease_area", "active")
        tree_shell = ctk.CTkFrame(left, fg_color="transparent")
        tree_shell.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        self.tree = ttk.Treeview(tree_shell, columns=columns, show="headings", style="MineDetails.Treeview", height=11)
        headings = {
            "mine_name": "Mine Name",
            "company_name": "Company",
            "quarry_type": "Quarry Type",
            "lease_area": "Lease Area",
            "active": "Active",
        }
        widths = {
            "mine_name": 180,
            "company_name": 160,
            "quarry_type": 120,
            "lease_area": 110,
            "active": 70,
        }
        for key in columns:
            self.tree.heading(key, text=headings[key])
            self.tree.column(key, width=widths[key], anchor="w")
        tree_scroll = ttk.Scrollbar(tree_shell, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._load_selected_into_form())
        self.tree.bind("<MouseWheel>", self._on_tree_wheel, add="+")
        self.tree.bind("<Button-4>", self._on_tree_wheel, add="+")
        self.tree.bind("<Button-5>", self._on_tree_wheel, add="+")

        left_buttons = ctk.CTkFrame(left, fg_color="transparent")
        left_buttons.pack(fill="x", padx=16, pady=(0, 16))
        ctk.CTkButton(left_buttons, text="New Mine", command=self._clear_form, width=104, height=32, fg_color=self._accent, hover_color="#1d4ed8").pack(side="left")
        ctk.CTkButton(left_buttons, text="Set Active", command=self._set_selected_active, width=104, height=32).pack(side="left", padx=(8, 0))
        ctk.CTkButton(left_buttons, text="Delete", command=self._delete_selected, width=84, height=32, fg_color="#b91c1c", hover_color="#991b1b").pack(side="left", padx=(8, 0))
        ctk.CTkButton(left_buttons, text="Refresh", command=self.refresh, width=84, height=32, fg_color="#334155", hover_color="#475569").pack(side="right")

        right.grid_rowconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)

        form_sheet = ctk.CTkScrollableFrame(
            right,
            fg_color="#040913",
            scrollbar_button_color="#334155",
            scrollbar_button_hover_color="#475569",
        )
        form_sheet.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        try:
            enable_mousewheel_scroll(form_sheet)
        except Exception:
            pass

        ctk.CTkLabel(
            form_sheet,
            text="Mine Profile",
            font=("Segoe UI Semibold", 20),
            text_color=self._text_primary,
        ).pack(anchor="w", padx=18, pady=(16, 6))
        ctk.CTkLabel(
            form_sheet,
            text="Vertical detail sheet for site identity and location context.",
            font=("Segoe UI", 12),
            text_color=self._text_muted,
        ).pack(anchor="w", padx=18, pady=(0, 14))

        self.form_vars: Dict[str, ctk.StringVar] = {}
        fields = [
            ("Mine Name", "mine_name", "Enter mine name"),
            ("Company Name", "company_name", "Enter company name"),
            ("Quarry Type", "quarry_type", "Granite / Blue metal / etc."),
            ("Lease Area", "lease_area", "e.g. 12 acres"),
            ("Google Maps Link", "google_maps_link", "https://maps.google.com/..."),
        ]
        for idx, (label, key, placeholder) in enumerate(fields):
            # Keep the first two boxes compact per UX request.
            compact = idx < 2
            card = ctk.CTkFrame(
                form_sheet,
                fg_color="#07111d",
                corner_radius=10 if compact else 12,
                border_width=1,
                border_color="#1d2a3f",
            )
            card.pack(fill="x", padx=12, pady=(0, 4 if compact else 8))
            ctk.CTkLabel(card, text=label, font=("Segoe UI Semibold", 13), text_color=self._text_primary).pack(
                anchor="w",
                padx=12,
                pady=(6 if compact else 10, 3 if compact else 6),
            )
            var = ctk.StringVar(value="")
            self.form_vars[key] = var
            ctk.CTkEntry(
                card,
                textvariable=var,
                placeholder_text=placeholder,
                font=("Segoe UI", 13),
                height=30 if compact else 34,
                fg_color="#0b1423",
                text_color="#f8fafc",
                border_color="#1f324d",
            ).pack(fill="x", padx=12, pady=(0, 7 if compact else 12))
            try:
                var.trace_add("write", lambda *_args: self._refresh_preview_cards())
            except Exception:
                pass

        address_card = ctk.CTkFrame(form_sheet, fg_color="#07111d", corner_radius=12, border_width=1, border_color="#1d2a3f")
        address_card.pack(fill="x", padx=14, pady=(0, 8))
        ctk.CTkLabel(address_card, text="Mine Address", font=("Segoe UI Semibold", 13), text_color=self._text_primary).pack(anchor="w", padx=12, pady=(10, 6))
        self.address_box = ctk.CTkTextbox(
            address_card,
            height=86,
            font=("Segoe UI", 13),
            fg_color="#0b1423",
            text_color="#f8fafc",
            border_color="#1f324d",
            border_width=1,
        )
        self.address_box.pack(fill="x", padx=12, pady=(0, 12))
        self.address_box.bind("<KeyRelease>", lambda _event: self._refresh_preview_cards())

        identity_card = ctk.CTkFrame(form_sheet, fg_color="#07111d", corner_radius=12, border_width=1, border_color="#1d2a3f")
        identity_card.pack(fill="x", padx=14, pady=(0, 8))
        ctk.CTkLabel(identity_card, text="Site Identity Preview", font=("Segoe UI Semibold", 15), text_color=self._text_primary).pack(anchor="w", padx=14, pady=(12, 4))
        self.brand_title = ctk.CTkLabel(
            identity_card,
            text="Company name will appear here",
            font=("Segoe UI Semibold", 17),
            text_color="#f8fafc",
            wraplength=420,
            justify="left",
        )
        self.brand_title.pack(anchor="w", padx=14, pady=(0, 2))
        self.brand_subtitle = ctk.CTkLabel(
            identity_card,
            text="Mine name and quarry identity preview",
            font=("Segoe UI", 12),
            text_color="#94a3b8",
            wraplength=420,
            justify="left",
        )
        self.brand_subtitle.pack(anchor="w", padx=14, pady=(0, 12))

        map_card = ctk.CTkFrame(form_sheet, fg_color="#07111d", corner_radius=12, border_width=1, border_color="#1d2a3f")
        map_card.pack(fill="x", padx=14, pady=(0, 8))
        ctk.CTkLabel(map_card, text="Map Preview", font=("Segoe UI Semibold", 15), text_color=self._text_primary).pack(anchor="w", padx=14, pady=(12, 4))
        self.map_title = ctk.CTkLabel(
            map_card,
            text="Google Maps link not added yet",
            font=("Segoe UI Semibold", 15),
            text_color="#f8fafc",
            wraplength=420,
            justify="left",
        )
        self.map_title.pack(anchor="w", padx=14, pady=(0, 4))
        self.map_address = ctk.CTkLabel(
            map_card,
            text="Add the mine address to preview the site context here.",
            font=("Segoe UI", 12),
            text_color="#94a3b8",
            wraplength=420,
            justify="left",
        )
        self.map_address.pack(anchor="w", padx=14, pady=(0, 6))
        self.map_link = ctk.CTkLabel(
            map_card,
            text="No map link available",
            font=("Segoe UI", 12),
            text_color="#93c5fd",
            wraplength=420,
            justify="left",
        )
        self.map_link.pack(anchor="w", padx=14, pady=(0, 8))
        ctk.CTkButton(
            map_card,
            text="Open Map Link",
            command=self._open_map,
            width=130,
            height=34,
            fg_color="#1d4ed8",
            hover_color="#1e40af",
        ).pack(anchor="w", padx=14, pady=(0, 12))

        self.form_status = ctk.CTkLabel(form_sheet, text="", font=("Segoe UI", 12), text_color=self._text_muted)
        self.form_status.pack(anchor="w", padx=14, pady=(4, 8))

        actions = ctk.CTkFrame(form_sheet, fg_color="transparent")
        actions.pack(fill="x", padx=14, pady=(0, 14))
        ctk.CTkButton(actions, text="Save Mine", command=self._save_form, width=130, height=36, fg_color="#059669", hover_color="#047857").pack(side="left")
        ctk.CTkButton(actions, text="Open in Browser", command=self._open_map, width=140, height=36, fg_color="#1d4ed8", hover_color="#1e40af").pack(side="left", padx=(8, 0))
        ctk.CTkButton(actions, text="Clear", command=self._clear_form, width=90, height=36, fg_color="#334155", hover_color="#475569").pack(side="left", padx=(8, 0))

        self._refresh_preview_cards()

    def _on_tree_wheel(self, event: Any) -> str:
        try:
            num = getattr(event, "num", None)
            if num == 4:
                delta = -1
            elif num == 5:
                delta = 1
            else:
                wheel_delta = int(getattr(event, "delta", 0) or 0)
                delta = -1 if wheel_delta > 0 else (1 if wheel_delta < 0 else 0)
            if delta:
                self.tree.yview_scroll(delta, "units")
                return "break"
        except Exception:
            pass
        return ""

    def refresh(self) -> None:
        self._rows = load_mines()
        active_id = get_active_mine_id()
        active_name = ""
        for row in self._rows:
            if str(row.get("id") or "") == active_id:
                active_name = str(row.get("mine_name") or active_id)
                break
        self.summary_label.configure(
            text=f"{len(self._rows)} mine profile(s) configured"
            + (f"  |  Active: {active_name or active_id}" if active_id else "")
        )
        for item in self.tree.get_children():
            self.tree.delete(item)
        for row in self._rows:
            mine_id = str(row.get("id") or "")
            active = "Yes" if mine_id and mine_id == active_id else ""
            self.tree.insert(
                "",
                "end",
                iid=mine_id,
                values=(
                    row.get("mine_name") or "",
                    row.get("company_name") or "",
                    row.get("quarry_type") or "",
                    row.get("lease_area") or "",
                    active,
                ),
            )
        if self._selected_mine_id and any(str(row.get("id") or "") == self._selected_mine_id for row in self._rows):
            try:
                self.tree.selection_set(self._selected_mine_id)
                self.tree.focus(self._selected_mine_id)
            except Exception:
                pass
            self._load_selected_into_form()
        elif self._rows:
            first_id = str(self._rows[0].get("id") or "")
            self._selected_mine_id = first_id
            try:
                self.tree.selection_set(first_id)
                self.tree.focus(first_id)
            except Exception:
                pass
            self._load_selected_into_form()
        else:
            self._clear_form(reset_status=False)
        self._notify_dashboard()

    def _selected_row(self) -> Optional[Dict[str, Any]]:
        target = self._selected_mine_id
        for row in self._rows:
            if str(row.get("id") or "") == target:
                return row
        return None

    def _load_selected_into_form(self) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        self._selected_mine_id = str(selected[0])
        row = self._selected_row()
        if not row:
            return
        for key, var in self.form_vars.items():
            var.set(str(row.get(key) or ""))
        self.address_box.delete("1.0", "end")
        self.address_box.insert("1.0", str(row.get("address") or ""))
        self.form_status.configure(text=f"Editing mine profile: {row.get('mine_name') or row.get('id')}")
        self._refresh_preview_cards()

    def _clear_form(self, *, reset_status: bool = True) -> None:
        self._selected_mine_id = ""
        try:
            self.tree.selection_remove(self.tree.selection())
        except Exception:
            pass
        for var in self.form_vars.values():
            var.set("")
        self.address_box.delete("1.0", "end")
        self._refresh_preview_cards()
        if reset_status:
            self.form_status.configure(text="Enter the mine details, save them, and set the active mine for the dashboard.")

    def _save_form(self) -> None:
        mine_name = str(self.form_vars["mine_name"].get() or "").strip()
        company_name = str(self.form_vars["company_name"].get() or "").strip()
        quarry_type = str(self.form_vars["quarry_type"].get() or "").strip()
        lease_area = str(self.form_vars["lease_area"].get() or "").strip()
        google_maps_link = str(self.form_vars["google_maps_link"].get() or "").strip()
        address = str(self.address_box.get("1.0", "end") or "").strip()
        was_empty = not bool(self._rows)

        if not validate_required(mine_name, "Mine Name"):
            return
        if not validate_required(company_name, "Company Name"):
            return
        if not validate_required(quarry_type, "Quarry Type"):
            return
        if not validate_required(address, "Mine Address"):
            return
        if google_maps_link and not _valid_google_maps_link(google_maps_link):
            messagebox.showerror("Validation", "Google Maps Link must be a valid Google Maps URL")
            return

        rows = list(self._rows)
        existing_index = None
        for idx, row in enumerate(rows):
            if str(row.get("id") or "") == self._selected_mine_id:
                existing_index = idx
                break

        payload = {
            "id": self._selected_mine_id,
            "mine_name": mine_name,
            "company_name": company_name,
            "quarry_type": quarry_type,
            "lease_area": lease_area,
            "address": address,
            "google_maps_link": google_maps_link,
            "logo_path": "",
            "notes": "",
        }
        if existing_index is None:
            rows.append(payload)
        else:
            created_at = rows[existing_index].get("created_at")
            if created_at:
                payload["created_at"] = created_at
            rows[existing_index] = payload

        active_id = get_active_mine_id()
        result = save_mines(rows, active_mine_id=active_id or self._selected_mine_id)
        saved_rows = result.get("mines") or []
        matched_id = ""
        for row in saved_rows:
            if (
                str(row.get("mine_name") or "") == mine_name
                and str(row.get("company_name") or "") == company_name
                and str(row.get("address") or "") == address
            ):
                matched_id = str(row.get("id") or "")
                break
        if not result.get("active_mine_id") and matched_id:
            set_active_mine(matched_id)
        self._selected_mine_id = matched_id or self._selected_mine_id
        self.form_status.configure(text=f"Saved mine profile for {mine_name}")
        self.refresh()
        if matched_id:
            try:
                self.tree.selection_set(matched_id)
                self.tree.focus(matched_id)
            except Exception:
                pass
        if was_empty and self.dashboard and not getattr(self.dashboard, "current_content", None) == "dashboard":
            try:
                self.dashboard.show_content("dashboard")
                if hasattr(self.dashboard, "sidebar") and self.dashboard.sidebar is not None:
                    self.dashboard.sidebar._activate_by_name("Dashboard")
            except Exception:
                pass

    def _set_selected_active(self) -> None:
        row = self._selected_row()
        if not row:
            messagebox.showwarning("Mine Details", "Select a mine profile first")
            return
        set_active_mine(str(row.get("id") or ""))
        self.form_status.configure(text=f"Active mine set to {row.get('mine_name') or row.get('id')}")
        self.refresh()

    def _delete_selected(self) -> None:
        row = self._selected_row()
        if not row:
            messagebox.showwarning("Mine Details", "Select a mine profile first")
            return
        name = str(row.get("mine_name") or row.get("id") or "this mine")
        if not messagebox.askyesno("Delete Mine", f"Delete mine profile '{name}'?"):
            return
        keep_rows = [item for item in self._rows if str(item.get("id") or "") != str(row.get("id") or "")]
        active_id = get_active_mine_id()
        if active_id == str(row.get("id") or ""):
            active_id = str(keep_rows[0].get("id") or "") if keep_rows else ""
        save_mines(keep_rows, active_mine_id=active_id)
        self._clear_form()
        self.refresh()

    def _open_map(self) -> None:
        url = str(self.form_vars["google_maps_link"].get() or "").strip()
        if not url:
            messagebox.showinfo("Google Maps", "Add a Google Maps link for this mine first")
            return
        if not _valid_google_maps_link(url):
            messagebox.showerror("Google Maps", "The saved link is not a valid Google Maps URL")
            return
        try:
            webbrowser.open(url, new=2)
            self.form_status.configure(text="Opened the Google Maps link for this mine")
        except Exception:
            messagebox.showerror("Google Maps", "Could not open the Google Maps link")

    def _notify_dashboard(self) -> None:
        try:
            if callable(self.on_state_change):
                self.on_state_change()
        except Exception:
            pass
        if not self.dashboard:
            return
        try:
            if hasattr(self.dashboard, "notify_mines_updated"):
                self.dashboard.notify_mines_updated()
        except Exception:
            pass

    def _refresh_preview_cards(self) -> None:
        mine_name = str(self.form_vars.get("mine_name").get() or "").strip() if "mine_name" in self.form_vars else ""
        company_name = str(self.form_vars.get("company_name").get() or "").strip() if "company_name" in self.form_vars else ""
        quarry_type = str(self.form_vars.get("quarry_type").get() or "").strip() if "quarry_type" in self.form_vars else ""
        lease_area = str(self.form_vars.get("lease_area").get() or "").strip() if "lease_area" in self.form_vars else ""
        maps_link = str(self.form_vars.get("google_maps_link").get() or "").strip() if "google_maps_link" in self.form_vars else ""
        address = str(self.address_box.get("1.0", "end") or "").strip() if hasattr(self, "address_box") else ""

        if hasattr(self, "brand_title"):
            self.brand_title.configure(text=company_name or "Company name will appear here")
        if hasattr(self, "brand_subtitle"):
            subtitle = " | ".join(part for part in (mine_name, quarry_type, f"Lease Area: {lease_area}" if lease_area else "") if part)
            self.brand_subtitle.configure(text=subtitle or "Mine name and quarry identity preview")

        if hasattr(self, "map_title"):
            self.map_title.configure(text=mine_name or "Google Maps link not added yet")
        if hasattr(self, "map_address"):
            self.map_address.configure(text=address or "Add the mine address to preview the site context here.")
        if hasattr(self, "map_link"):
            self.map_link.configure(text=maps_link or "No map link available")


class MineSetupFrame(ctk.CTkFrame):
    """Dedicated post-login mine setup step shown before dashboard access."""

    def __init__(self, parent, user: Dict[str, str], on_complete: Callable[[Dict[str, str]], None]):
        super().__init__(parent, fg_color=theme_mod.SIMPLE_PALETTE.get("bg", "#07121f"))
        self.user = user
        self.on_complete = on_complete
        self._text_primary = "#e2e8f0"
        self._text_muted = "#94a3b8"
        self._accent = theme_mod.SIMPLE_PALETTE.get("primary", "#22D3EE")
        self._build_ui()
        self._refresh_continue_state()

    def _build_ui(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        scroll_shell = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            scrollbar_button_color="#334155",
            scrollbar_button_hover_color="#475569",
        )
        scroll_shell.grid(row=0, column=0, sticky="nsew", padx=14, pady=14)
        try:
            enable_mousewheel_scroll(scroll_shell)
        except Exception:
            pass

        shell = ctk.CTkFrame(scroll_shell, fg_color="transparent")
        shell.pack(fill="both", expand=True)
        shell.grid_rowconfigure(1, weight=1)
        shell.grid_columnconfigure(0, weight=1)

        hero = GradientPanel(
            shell,
            colors=getattr(theme_mod, "SECTION_GRADIENTS", {}).get("mine_setup", ("#0f172a", "#1d4ed8", "#0891b2")),
            corner_radius=20,
            border_color="#1d2a3f",
        )
        hero.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        ctk.CTkLabel(
            hero.content,
            text="Mine Setup",
            font=("Segoe UI Semibold", 24),
            text_color=self._text_primary,
        ).pack(anchor="w", padx=18, pady=(14, 4))
        ctk.CTkLabel(
            hero.content,
            text=(
                f"Welcome {self.user.get('name', 'User')}. Confirm the mine details for this session before entering the dashboard."
            ),
            font=("Segoe UI", 13),
            text_color="#dbeafe",
            wraplength=730,
            justify="left",
        ).pack(anchor="w", padx=18, pady=(0, 8))
        ctk.CTkLabel(
            hero.content,
            text="Login -> Mine Details -> Dashboard",
            font=("Segoe UI Semibold", 12),
            text_color="#fef3c7",
            fg_color="#0f172a",
            corner_radius=10,
            padx=10,
            pady=5,
        ).pack(anchor="w", padx=18, pady=(0, 12))

        content = ctk.CTkFrame(shell, fg_color="transparent")
        content.grid(row=1, column=0, sticky="nsew")
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=1)

        self.mine_details = MineDetailsFrame(content, dashboard=None, on_state_change=self._refresh_continue_state)
        self.mine_details.grid(row=0, column=0, sticky="nsew")

        footer = ctk.CTkFrame(shell, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        self.status_label = ctk.CTkLabel(
            footer,
            text="Save or confirm the active mine, then continue to the dashboard.",
            font=("Segoe UI", 12),
            text_color=self._text_muted,
        )
        self.status_label.pack(side="left")
        self.continue_btn = ctk.CTkButton(
            footer,
            text="Continue to Dashboard",
            command=self._continue,
            height=40,
            font=("Segoe UI Semibold", 14),
            fg_color=self._accent,
            hover_color="#06b6d4",
        )
        self.continue_btn.pack(side="right")
        self.skip_btn = ctk.CTkButton(
            footer,
            text="Skip with Current Active Mine",
            command=self._skip_with_active,
            height=40,
            font=("Segoe UI Semibold", 13),
            fg_color="#334155",
            hover_color="#475569",
        )
        self.skip_btn.pack(side="right", padx=(0, 10))

    def _refresh_continue_state(self) -> None:
        active = get_active_mine() or {}
        active_name = str(active.get("mine_name") or "").strip()
        if active_name:
            try:
                self.status_label.configure(text=f"Active mine ready: {active_name}")
                self.continue_btn.configure(state="normal")
                self.skip_btn.configure(state="normal")
            except Exception:
                pass
        else:
            try:
                self.status_label.configure(text="Set an active mine profile before continuing to the dashboard.")
                self.continue_btn.configure(state="disabled")
                self.skip_btn.configure(state="disabled")
            except Exception:
                pass

    def _continue(self) -> None:
        active = get_active_mine() or {}
        if not str(active.get("mine_name") or "").strip():
            self._refresh_continue_state()
            return
        try:
            self.on_complete(self.user)
        except Exception:
            pass

    def _skip_with_active(self) -> None:
        active = get_active_mine() or {}
        if not str(active.get("mine_name") or "").strip():
            self._refresh_continue_state()
            return
        try:
            self.on_complete(self.user)
        except Exception:
            pass


