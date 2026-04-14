from __future__ import annotations

import json
import os
import shutil
import tkinter as tk
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, List, Optional

import customtkinter as ctk
try:
    from PIL import Image
except Exception:
    Image = None

try:
    from ..app_paths import data_path
    from ..sms_contacts import normalize_sms_phone
except Exception:
    from app_paths import data_path
    from sms_contacts import normalize_sms_phone
from .theme import SIMPLE_PALETTE

PALETTE = SIMPLE_PALETTE
MAX_CERT_IMAGE_BYTES = 500 * 1024


def _try_parse_date(raw: Any) -> Optional[date]:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text).date()
    except Exception:
        pass
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except Exception:
            continue
    return None


def _add_years_safe(source: date, years: int) -> date:
    try:
        return source.replace(year=source.year + years)
    except ValueError:
        # Leap-year fallback: move Feb-29 anniversaries to Feb-28.
        return source.replace(month=2, day=28, year=source.year + years)


def _operator_row_id(index: int) -> str:
    return f"OPR-{index + 1:04d}"


class OperatorRecordsFrame(ctk.CTkFrame):
    """Worksheet-style operator records with expiry monitoring fields."""

    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self.data_path = data_path("operators_extended.json")
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        self.operators: List[Dict[str, Any]] = []
        self._count_label = None
        self._expiry_label = None
        self._status_label = None
        self.tree: Optional[ttk.Treeview] = None
        self._selected_id: str = ""
        self._is_editing: bool = False
        self._form_vars: Dict[str, tk.StringVar] = {}
        self._cert_image_dir: Path = data_path("operator_cert_images")
        self._cert_image_dir.mkdir(parents=True, exist_ok=True)
        self._certificate_file_label = None
        self._cert_preview_label = None
        self._cert_preview_image = None

        self._load()
        self._build()
        self._refresh_table()

    def _load(self) -> None:
        try:
            if self.data_path.exists():
                payload = json.loads(self.data_path.read_text(encoding="utf-8")) or []
                if isinstance(payload, list):
                    self.operators = [self._normalize_record(row, idx) for idx, row in enumerate(payload) if isinstance(row, dict)]
                else:
                    self.operators = []
            else:
                self.operators = []
        except Exception:
            self.operators = []

    def _save(self) -> None:
        try:
            self.data_path.parent.mkdir(parents=True, exist_ok=True)
            self.data_path.write_text(json.dumps(self.operators, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _normalize_record(self, row: Dict[str, Any], index: int) -> Dict[str, Any]:
        rid = str(row.get("id") or row.get("_id") or "").strip() or _operator_row_id(index)
        license_expiry = (
            str(row.get("license_expiry") or row.get("licence_expiry") or "").strip()
        )
        medical_end = (
            str(
                row.get("medical_certificate_end_date")
                or row.get("fitness_expiry")
                or row.get("medical_expiry")
                or ""
            ).strip()
        )
        return {
            "id": rid,
            "name": str(row.get("name") or "").strip(),
            "phone": str(row.get("phone") or "").strip(),
            "certificate_number": str(row.get("certificate_number") or "").strip(),
            "certificate_image": str(row.get("certificate_image") or "").strip(),
            "license_registered_date": str(
                row.get("license_registered_date")
                or row.get("license_issue_date")
                or ""
            ).strip(),
            "license_expiry": license_expiry,
            "medical_certificate_issue_date": str(
                row.get("medical_certificate_issue_date")
                or row.get("medical_issue_date")
                or ""
            ).strip(),
            "medical_certificate_end_date": medical_end,
            "company_start_date": str(
                row.get("company_start_date")
                or row.get("experience_start_date")
                or row.get("joining_date")
                or ""
            ).strip(),
            "created_at": str(row.get("created_at") or datetime.now().isoformat(timespec="seconds")),
        }

    def _build(self) -> None:
        shell = ctk.CTkFrame(self, fg_color="transparent")
        shell.pack(fill="both", expand=True, padx=18, pady=18)

        header = ctk.CTkFrame(shell, fg_color=PALETTE.get("card", "#111827"), corner_radius=14)
        header.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            header,
            text="Operator Records",
            font=("Segoe UI Semibold", 23),
            text_color="#f8fafc",
        ).pack(anchor="w", padx=14, pady=(12, 2))
        ctk.CTkLabel(
            header,
            text="Manage license, medical, and service milestone records with automated alert readiness.",
            font=("Segoe UI", 13),
            text_color="#94a3b8",
        ).pack(anchor="w", padx=14, pady=(0, 10))

        summary = ctk.CTkFrame(header, fg_color="transparent")
        summary.pack(fill="x", padx=14, pady=(0, 12))
        self._count_label = ctk.CTkLabel(
            summary,
            text="0 operators",
            font=("Segoe UI Semibold", 13),
            text_color="#dbeafe",
            fg_color="#1e3a8a",
            corner_radius=8,
            padx=10,
            pady=4,
        )
        self._count_label.pack(side="left")
        self._expiry_label = ctk.CTkLabel(
            summary,
            text="Alerts now: 0",
            font=("Segoe UI", 13),
            text_color="#fde68a",
        )
        self._expiry_label.pack(side="left", padx=(10, 0))
        self._status_label = ctk.CTkLabel(
            summary,
            text="Ready",
            font=("Segoe UI", 13),
            text_color="#94a3b8",
        )
        self._status_label.pack(side="right")

        body = ctk.CTkFrame(shell, fg_color=PALETTE.get("card", "#0f172a"), corner_radius=14)
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=4)
        body.grid_columnconfigure(1, weight=3)
        body.grid_rowconfigure(1, weight=1)

        toolbar = ctk.CTkFrame(body, fg_color="transparent")
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 8))

        btn_font = ("Segoe UI Semibold", 13)
        ctk.CTkButton(
            toolbar,
            text="Add",
            width=90,
            height=34,
            font=btn_font,
            fg_color=PALETTE.get("primary", "#2563eb"),
            hover_color="#1d4ed8",
            command=self._add_new,
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            toolbar,
            text="Edit",
            width=90,
            height=34,
            font=btn_font,
            fg_color="#0f766e",
            hover_color="#115e59",
            command=self._edit_selected,
        ).pack(side="left", padx=6)
        ctk.CTkButton(
            toolbar,
            text="Delete",
            width=90,
            height=34,
            font=btn_font,
            fg_color="#b91c1c",
            hover_color="#991b1b",
            command=self._delete_selected,
        ).pack(side="left", padx=6)
        ctk.CTkButton(
            toolbar,
            text="Save",
            width=90,
            height=34,
            font=btn_font,
            fg_color="#7c3aed",
            hover_color="#6d28d9",
            command=self._save_current,
        ).pack(side="left", padx=6)
        ctk.CTkButton(
            toolbar,
            text="Check Alerts",
            width=120,
            height=34,
            font=btn_font,
            fg_color="#d97706",
            hover_color="#b45309",
            command=self._check_alerts,
        ).pack(side="left", padx=6)
        ctk.CTkButton(
            toolbar,
            text="Refresh",
            width=96,
            height=34,
            font=btn_font,
            fg_color="#334155",
            hover_color="#475569",
            command=self._refresh_table,
        ).pack(side="right")

        sheet_card = ctk.CTkFrame(body, fg_color="#0b1220", corner_radius=12)
        sheet_card.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=(0, 12))
        sheet_card.grid_columnconfigure(0, weight=1)
        sheet_card.grid_rowconfigure(1, weight=1)
        sheet_card.grid_rowconfigure(2, weight=0)

        ctk.CTkLabel(
            sheet_card,
            text="Operator Worksheet",
            font=("Segoe UI Semibold", 16),
            text_color="#e2e8f0",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 6))

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(
            "OperatorRecords.Treeview",
            rowheight=34,
            background="#0b1220",
            fieldbackground="#0b1220",
            foreground="#e2e8f0",
            borderwidth=0,
            relief="flat",
            font=("Segoe UI", 11),
        )
        style.configure(
            "OperatorRecords.Treeview.Heading",
            background="#111827",
            foreground="#cbd5e1",
            relief="flat",
            borderwidth=0,
            font=("Segoe UI Semibold", 11),
            padding=(8, 6),
        )
        style.map(
            "OperatorRecords.Treeview",
            background=[("selected", "#1d4ed8")],
            foreground=[("selected", "#f8fafc")],
        )

        columns = (
            "name",
            "phone",
            "license_registered_date",
            "license_expiry",
            "medical_certificate_issue_date",
            "medical_certificate_end_date",
            "company_start_date",
        )
        self.tree = ttk.Treeview(
            sheet_card,
            columns=columns,
            show="headings",
            style="OperatorRecords.Treeview",
            selectmode="browse",
        )
        headings = {
            "name": "Operator Name",
            "phone": "Phone",
            "license_registered_date": "Licence Reg Date",
            "license_expiry": "Licence Expiry",
            "medical_certificate_issue_date": "Medical Issue Date",
            "medical_certificate_end_date": "Medical End Date",
            "company_start_date": "Company Start Date",
        }
        widths = {
            "name": 170,
            "phone": 110,
            "license_registered_date": 120,
            "license_expiry": 120,
            "medical_certificate_issue_date": 125,
            "medical_certificate_end_date": 120,
            "company_start_date": 120,
        }
        for key in columns:
            self.tree.heading(key, text=headings[key])
            self.tree.column(key, width=widths[key], anchor="w", stretch=True)

        tree_wrap = ctk.CTkFrame(sheet_card, fg_color="transparent")
        tree_wrap.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        tree_wrap.grid_columnconfigure(0, weight=1)
        tree_wrap.grid_rowconfigure(0, weight=1)
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        yscroll = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.tree.yview)
        yscroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=yscroll.set)

        xscroll = ttk.Scrollbar(tree_wrap, orient="horizontal", command=self.tree.xview)
        xscroll.grid(row=1, column=0, sticky="ew")
        self.tree.configure(xscrollcommand=xscroll.set)

        preview_card = ctk.CTkFrame(sheet_card, fg_color="#111827", corner_radius=10)
        preview_card.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        preview_card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            preview_card,
            text="Certificate Image Preview",
            font=("Segoe UI Semibold", 13),
            text_color="#e2e8f0",
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(8, 2))
        self._cert_preview_label = ctk.CTkLabel(
            preview_card,
            text="No certificate image selected",
            font=("Segoe UI", 12),
            text_color="#94a3b8",
            fg_color="#0f172a",
            corner_radius=8,
            height=150,
            anchor="center",
        )
        self._cert_preview_label.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))

        form_card = ctk.CTkFrame(body, fg_color="#111827", corner_radius=12)
        form_card.grid(row=1, column=1, sticky="nsew", padx=(6, 12), pady=(0, 12))
        form_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            form_card,
            text="Record Editor",
            font=("Segoe UI Semibold", 16),
            text_color="#e2e8f0",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 4))
        ctk.CTkLabel(
            form_card,
            text="Use YYYY-MM-DD for date fields",
            font=("Segoe UI", 12),
            text_color="#94a3b8",
        ).grid(row=1, column=0, sticky="w", padx=12, pady=(0, 8))

        field_specs = [
            ("name", "Operator Name"),
            ("phone", "Phone (+91XXXXXXXXXX)"),
            ("certificate_number", "Certificate Number"),
            ("license_registered_date", "Driving Licence Registered Date"),
            ("license_expiry", "Driving Licence Expiry Date"),
            ("medical_certificate_issue_date", "Medical Certificate Issue Date"),
            ("medical_certificate_end_date", "Medical Certificate End Date"),
            ("company_start_date", "Company Experience Start Date"),
        ]

        row_idx = 2
        for key, label in field_specs:
            ctk.CTkLabel(
                form_card,
                text=label,
                font=("Segoe UI", 13),
                text_color="#d1d5db",
            ).grid(row=row_idx, column=0, sticky="w", padx=12, pady=(6, 2))
            var = tk.StringVar(value="")
            entry = ctk.CTkEntry(
                form_card,
                textvariable=var,
                height=36,
                fg_color="#0f172a",
                border_color="#1f2937",
                text_color="#f8fafc",
            )
            entry.grid(row=row_idx + 1, column=0, sticky="ew", padx=12, pady=(0, 2))
            self._form_vars[key] = var
            row_idx += 2

        self._form_vars["certificate_image"] = tk.StringVar(value="")
        image_actions = ctk.CTkFrame(form_card, fg_color="transparent")
        image_actions.grid(row=row_idx, column=0, sticky="ew", padx=12, pady=(8, 2))
        image_actions.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(
            image_actions,
            text="Upload Certificate Image",
            width=180,
            height=34,
            font=("Segoe UI Semibold", 12),
            fg_color="#0ea5a4",
            hover_color="#0f766e",
            command=self._upload_certificate_image,
        ).grid(row=0, column=0, sticky="w")
        self._certificate_file_label = ctk.CTkLabel(
            image_actions,
            text="No file selected (max 500KB)",
            font=("Segoe UI", 12),
            text_color="#94a3b8",
            anchor="w",
        )
        self._certificate_file_label.grid(row=0, column=1, sticky="ew", padx=(10, 0))

        self._set_status("Ready")

    def _set_status(self, text: str, color: str = "#94a3b8") -> None:
        try:
            if self._status_label is not None:
                self._status_label.configure(text=text, text_color=color)
        except Exception:
            pass

    def _current_alert_count(self) -> int:
        today = datetime.now().date()
        count = 0
        for row in self.operators:
            license_expiry = _try_parse_date(row.get("license_expiry"))
            medical_end = _try_parse_date(row.get("medical_certificate_end_date"))
            company_start = _try_parse_date(row.get("company_start_date"))

            if license_expiry is not None and 0 <= (license_expiry - today).days <= 30:
                count += 1
                continue
            if medical_end is not None and 0 <= (medical_end - today).days <= 30:
                count += 1
                continue
            if company_start is not None and today >= _add_years_safe(company_start, 10):
                count += 1
        return count

    def _update_summary(self) -> None:
        try:
            if self._count_label is not None:
                self._count_label.configure(text=f"{len(self.operators)} operators")
            if self._expiry_label is not None:
                self._expiry_label.configure(text=f"Alerts now: {self._current_alert_count()}")
        except Exception:
            pass

    def _refresh_table(self) -> None:
        if self.tree is None:
            return
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.operators = [self._normalize_record(row, idx) for idx, row in enumerate(self.operators)]
        for row in self.operators:
            rid = str(row.get("id") or "").strip()
            values = (
                row.get("name") or "",
                row.get("phone") or "",
                row.get("license_registered_date") or "",
                row.get("license_expiry") or "",
                row.get("medical_certificate_issue_date") or "",
                row.get("medical_certificate_end_date") or "",
                row.get("company_start_date") or "",
            )
            self.tree.insert("", "end", iid=rid, values=values)
        self._update_summary()
        if self._selected_id and self.tree.exists(self._selected_id):
            self.tree.selection_set(self._selected_id)
            self.tree.focus(self._selected_id)
        else:
            self._selected_id = ""
        if not self._selected_id:
            self._clear_form()

    def _record_by_id(self, rid: str) -> Optional[Dict[str, Any]]:
        for row in self.operators:
            if str(row.get("id") or "").strip() == rid:
                return row
        return None

    def _on_tree_select(self, _event=None) -> None:
        if self.tree is None:
            return
        selected = self.tree.selection()
        if not selected:
            return
        rid = str(selected[0]).strip()
        row = self._record_by_id(rid)
        if row is None:
            return
        self._selected_id = rid
        self._is_editing = False
        self._fill_form(row)
        self._set_status(f"Selected {row.get('name') or rid}", "#93c5fd")

    def _fill_form(self, row: Dict[str, Any]) -> None:
        for key in self._form_vars:
            self._form_vars[key].set(str(row.get(key) or ""))
        cert_image = str(row.get("certificate_image") or "").strip()
        self._update_certificate_label(cert_image)
        self._show_certificate_preview(cert_image)

    def _clear_form(self) -> None:
        for key in self._form_vars:
            self._form_vars[key].set("")
        self._update_certificate_label("")
        self._show_certificate_preview("")

    def _add_new(self) -> None:
        self._selected_id = ""
        self._is_editing = True
        self._clear_form()
        if self.tree is not None:
            self.tree.selection_remove(self.tree.selection())
        self._set_status("Add mode: fill fields then click Save", "#86efac")

    def _edit_selected(self) -> None:
        if not self._selected_id:
            self._set_status("Select a row to edit", "#fbbf24")
            return
        self._is_editing = True
        self._set_status("Edit mode: update fields then click Save", "#86efac")

    def _validate_payload(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        name = str(payload.get("name") or "").strip()
        if not name:
            messagebox.showwarning("Validation", "Operator name is required.")
            return None

        phone_raw = str(payload.get("phone") or "").strip()
        normalized_phone = normalize_sms_phone(phone_raw)
        if not normalized_phone:
            messagebox.showwarning("Validation", "Phone number is invalid. Use 10-digit Indian number or +91 format.")
            return None

        date_fields = (
            "license_registered_date",
            "license_expiry",
            "medical_certificate_issue_date",
            "medical_certificate_end_date",
            "company_start_date",
        )
        normalized_dates: Dict[str, str] = {}
        for key in date_fields:
            raw = str(payload.get(key) or "").strip()
            if not raw:
                normalized_dates[key] = ""
                continue
            dt = _try_parse_date(raw)
            if dt is None:
                messagebox.showwarning("Validation", f"{key.replace('_', ' ').title()} has invalid date format.")
                return None
            normalized_dates[key] = dt.isoformat()

        out = dict(payload)
        out["name"] = name
        out["phone"] = normalized_phone
        out["certificate_number"] = str(payload.get("certificate_number") or "").strip()
        out.update(normalized_dates)
        return out

    def _update_certificate_label(self, image_path: str) -> None:
        if self._certificate_file_label is None:
            return
        target = str(image_path or "").strip()
        if not target:
            self._certificate_file_label.configure(text="No file selected (max 500KB)", text_color="#94a3b8")
            return
        p = Path(target)
        size_text = ""
        try:
            if p.exists():
                size_text = f" ({int(p.stat().st_size / 1024)}KB)"
        except Exception:
            size_text = ""
        self._certificate_file_label.configure(text=f"{p.name}{size_text}", text_color="#93c5fd")

    def _show_certificate_preview(self, image_path: str) -> None:
        if self._cert_preview_label is None:
            return
        target = str(image_path or "").strip()
        if not target:
            self._cert_preview_image = None
            self._cert_preview_label.configure(image=None, text="No certificate image selected")
            return
        p = Path(target)
        if not p.exists():
            self._cert_preview_image = None
            self._cert_preview_label.configure(image=None, text="Image file not found")
            return
        if Image is None:
            self._cert_preview_image = None
            self._cert_preview_label.configure(image=None, text=f"Image saved: {p.name}")
            return
        try:
            img = Image.open(p)
            img.thumbnail((340, 140))
            cimg = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
            self._cert_preview_image = cimg
            self._cert_preview_label.configure(image=cimg, text="")
        except Exception:
            self._cert_preview_image = None
            self._cert_preview_label.configure(image=None, text=f"Unable to preview {p.name}")

    def _upload_certificate_image(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Select Certificate Image",
            filetypes=[
                ("Image files", "*.png;*.jpg;*.jpeg;*.webp;*.bmp"),
                ("All files", "*.*"),
            ],
        )
        if not file_path:
            return
        try:
            size_bytes = os.path.getsize(file_path)
        except Exception:
            messagebox.showerror("Image Upload", "Unable to read selected file.")
            return
        if size_bytes > MAX_CERT_IMAGE_BYTES:
            messagebox.showwarning("Image Too Large", "Image must be 500KB or smaller.")
            return
        self._form_vars["certificate_image"].set(file_path)
        self._update_certificate_label(file_path)
        self._show_certificate_preview(file_path)
        self._set_status("Certificate image selected. Click Save to store.", "#93c5fd")

    def _persist_certificate_image(self, source_path: str, operator_id: str) -> Optional[str]:
        raw = str(source_path or "").strip()
        if not raw:
            return ""
        src = Path(raw)
        if not src.exists():
            messagebox.showwarning("Image Upload", "Selected certificate image file is missing.")
            return None
        try:
            size_bytes = src.stat().st_size
        except Exception:
            messagebox.showwarning("Image Upload", "Unable to read certificate image size.")
            return None
        if size_bytes > MAX_CERT_IMAGE_BYTES:
            messagebox.showwarning("Image Too Large", "Image must be 500KB or smaller.")
            return None
        suffix = src.suffix.lower() or ".png"
        if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
            suffix = ".png"
        dest = self._cert_image_dir / f"{operator_id}{suffix}"
        try:
            if src.resolve() != dest.resolve():
                shutil.copy2(src, dest)
        except Exception:
            try:
                shutil.copy2(src, dest)
            except Exception:
                messagebox.showerror("Image Upload", "Failed to store certificate image.")
                return None
        return str(dest)

    def _save_current(self) -> None:
        raw_payload = {key: var.get() for key, var in self._form_vars.items()}
        payload = self._validate_payload(raw_payload)
        if payload is None:
            return

        now_iso = datetime.now().isoformat(timespec="seconds")
        if self._selected_id:
            existing = self._record_by_id(self._selected_id)
            if existing is not None:
                persisted_image = self._persist_certificate_image(payload.get("certificate_image", ""), self._selected_id)
                if persisted_image is None:
                    return
                payload["certificate_image"] = persisted_image
                existing.update(payload)
                existing["updated_at"] = now_iso
                self._save()
                self._refresh_table()
                self._set_status("Operator record updated", "#93c5fd")
                self._is_editing = False
                return

        id_index = len(self.operators)
        new_id = _operator_row_id(id_index)
        while self._record_by_id(new_id) is not None:
            id_index += 1
            new_id = _operator_row_id(id_index)
        persisted_image = self._persist_certificate_image(payload.get("certificate_image", ""), new_id)
        if persisted_image is None:
            return
        payload["certificate_image"] = persisted_image
        new_row = {
            "id": new_id,
            **payload,
            "created_at": now_iso,
            "updated_at": now_iso,
        }
        self.operators.append(self._normalize_record(new_row, len(self.operators)))
        self._selected_id = new_id
        self._save()
        self._refresh_table()
        self._set_status("Operator record saved", "#86efac")
        self._is_editing = False

    def _delete_selected(self) -> None:
        if not self._selected_id:
            self._set_status("Select a row to delete", "#fbbf24")
            return
        row = self._record_by_id(self._selected_id)
        if row is None:
            self._set_status("Selected row no longer exists", "#f87171")
            return
        answer = messagebox.askyesno("Delete Operator", f"Delete record for '{row.get('name') or self._selected_id}'?")
        if not answer:
            return
        self.operators = [item for item in self.operators if str(item.get("id") or "").strip() != self._selected_id]
        self._selected_id = ""
        self._save()
        self._refresh_table()
        self._set_status("Operator record deleted", "#fca5a5")

    def _check_alerts(self) -> None:
        today = datetime.now().date()
        lines: List[str] = []
        for row in self.operators:
            name = str(row.get("name") or "Operator").strip()
            lic_exp = _try_parse_date(row.get("license_expiry"))
            med_exp = _try_parse_date(row.get("medical_certificate_end_date"))
            comp_start = _try_parse_date(row.get("company_start_date"))

            if lic_exp is not None:
                days = (lic_exp - today).days
                if 0 <= days <= 5:
                    lines.append(f"{name}: Driving licence expires in {days} day(s).")
                elif 0 <= days <= 30:
                    lines.append(f"{name}: Driving licence renewal window ({days} day(s) left).")

            if med_exp is not None:
                days = (med_exp - today).days
                if 0 <= days <= 5:
                    lines.append(f"{name}: Medical certificate ends in {days} day(s).")
                elif 0 <= days <= 30:
                    lines.append(f"{name}: Medical renewal window ({days} day(s) left).")

            if comp_start is not None:
                milestone = _add_years_safe(comp_start, 10)
                if today >= milestone:
                    years = max(10, today.year - comp_start.year)
                    lines.append(f"{name}: {years} years completed in company service.")

        if not lines:
            self._set_status("No immediate operator alerts", "#86efac")
            messagebox.showinfo("Operator Alerts", "No immediate operator alerts found.")
            return

        self._set_status("Operator alerts found", "#fbbf24")
        messagebox.showwarning("Operator Alerts", "\n".join(lines))
