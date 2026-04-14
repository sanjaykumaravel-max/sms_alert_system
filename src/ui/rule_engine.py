from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox

from authz import has_role

try:
    from ..rule_engine import load_rules, save_rules
except Exception:
    from rule_engine import load_rules, save_rules

from .gradient import GradientPanel
from .theme import SIMPLE_PALETTE
from . import theme as theme_mod


PALETTE = SIMPLE_PALETTE
OPS = ["eq", "neq", "gt", "gte", "lt", "lte", "contains", "in", "between", "exists", "truthy"]
FIELD_HINTS = ["status", "risk_score", "days_to_due", "hours_to_due", "trigger", "machine_type", "company"]
CONTROL_HEIGHT = 44
TOOLBAR_BUTTON_HEIGHT = 42
COMPACT_BUTTON_HEIGHT = 40
ENTRY_FONT = ("Segoe UI", 14)
LABEL_FONT = ("Segoe UI", 13)


def _auto_parse_scalar(value: str) -> Any:
    text = str(value or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    try:
        if "." in text:
            return float(text)
        return int(text)
    except Exception:
        return text


def _extract_simple_condition(condition: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]], bool]:
    node = dict(condition or {})
    if not node:
        return "all", [], False

    if "field" in node:
        return "all", [node], False

    mode = "all" if isinstance(node.get("all"), list) else "any" if isinstance(node.get("any"), list) else "all"
    children = node.get(mode) if isinstance(node.get(mode), list) else []
    leaves: List[Dict[str, Any]] = []
    for child in children:
        if not isinstance(child, dict):
            return mode, [], True
        if "field" not in child:
            return mode, [], True
        leaves.append(child)
    return mode, leaves, False


def _build_condition(mode: str, leaves: List[Dict[str, Any]]) -> Dict[str, Any]:
    rows = [dict(item) for item in leaves if isinstance(item, dict) and str(item.get("field") or "").strip()]
    if not rows:
        return {}
    if len(rows) == 1:
        return rows[0]
    group = "any" if str(mode or "all").strip().lower() == "any" else "all"
    return {group: rows}


class RuleEngineFrame(ctk.CTkFrame):
    def __init__(self, parent: Any, dashboard: Any = None):
        super().__init__(parent, fg_color="transparent")
        self.dashboard = dashboard
        self.user = getattr(dashboard, "user", None) if dashboard is not None else None
        self._is_admin = bool(has_role(self.user, "admin")) if self.user is not None else True
        self._rows: List[Dict[str, Any]] = []

        outer = ctk.CTkFrame(self, fg_color=PALETTE.get("card", "#111827"), corner_radius=16)
        outer.pack(fill="both", expand=True, padx=6, pady=6)

        self._build_header(outer)
        self._build_toolbar(outer)

        self.rules_container = ctk.CTkScrollableFrame(
            outer,
            fg_color="transparent",
            height=self._worksheet_height(),
        )
        self.rules_container.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        try:
            self.rules_container.grid_columnconfigure(0, weight=1)
        except Exception:
            pass

        try:
            self.bind("<Configure>", self._on_resize, add="+")
        except Exception:
            pass

        self._reload_rules()

    def _worksheet_height(self) -> int:
        """Use a taller worksheet viewport for better visibility."""
        try:
            top = self.winfo_toplevel()
            top.update_idletasks()
            current_h = int(top.winfo_height() or 0)
            if current_h <= 1:
                current_h = int(top.winfo_screenheight() * 0.9)
            return max(760, int(current_h * 0.84))
        except Exception:
            return 840

    def _on_resize(self, _event: Any = None) -> None:
        try:
            self.rules_container.configure(height=self._worksheet_height())
        except Exception:
            pass

    def _build_header(self, parent: Any) -> None:
        panel = GradientPanel(
            parent,
            colors=getattr(theme_mod, "SECTION_GRADIENTS", {}).get("rule_engine", ("#101827", "#155e75", "#22d3ee")),
            corner_radius=14,
            border_color="#1d2a3f",
        )
        panel.pack(fill="x", padx=10, pady=(10, 8))
        ctk.CTkLabel(
            panel.content,
            text="Rule Engine",
            font=("Segoe UI Semibold", 24),
            text_color="#f8fafc",
        ).pack(anchor="w", padx=14, pady=(14, 2))
        ctk.CTkLabel(
            panel.content,
            text="Create maintenance automation rules visually. No JSON editing needed.",
            font=("Segoe UI", 13),
            text_color="#dbeafe",
        ).pack(anchor="w", padx=14, pady=(0, 6))

        access_text = "Administrator edit mode" if self._is_admin else "View-only mode"
        access_color = "#22c55e" if self._is_admin else "#f59e0b"
        ctk.CTkLabel(
            panel.content,
            text=access_text,
            font=("Segoe UI Semibold", 12),
            text_color="#ffffff",
            fg_color=access_color,
            corner_radius=8,
            padx=8,
            pady=4,
        ).pack(anchor="w", padx=14, pady=(0, 12))

    def _build_toolbar(self, parent: Any) -> None:
        toolbar = ctk.CTkFrame(parent, fg_color="transparent")
        toolbar.pack(fill="x", padx=14, pady=(0, 10))

        self.add_btn = ctk.CTkButton(
            toolbar,
            text="Add Rule",
            width=110,
            height=TOOLBAR_BUTTON_HEIGHT,
            command=self._add_rule,
            fg_color="#0f766e",
            hover_color="#0d9488",
            font=("Segoe UI Semibold", 13),
        )
        self.add_btn.pack(side="left", padx=(0, 8))

        self.reload_btn = ctk.CTkButton(
            toolbar,
            text="Reload",
            width=90,
            height=TOOLBAR_BUTTON_HEIGHT,
            command=self._reload_rules,
            fg_color="#1e293b",
            hover_color="#334155",
            font=("Segoe UI Semibold", 13),
        )
        self.reload_btn.pack(side="left", padx=(0, 8))

        self.save_btn = ctk.CTkButton(
            toolbar,
            text="Save All Rules",
            width=130,
            height=TOOLBAR_BUTTON_HEIGHT,
            command=self._save_all,
            fg_color="#1d4ed8",
            hover_color="#2563eb",
            font=("Segoe UI Semibold", 13),
        )
        self.save_btn.pack(side="left")

        self.status_label = ctk.CTkLabel(
            toolbar,
            text="",
            font=("Segoe UI", 13),
            text_color="#94a3b8",
        )
        self.status_label.pack(side="right")

        if not self._is_admin:
            for widget in (self.add_btn, self.save_btn):
                try:
                    widget.configure(state="disabled")
                except Exception:
                    pass

    def _set_status(self, text: str, color: str = "#94a3b8") -> None:
        try:
            self.status_label.configure(text=text, text_color=color)
        except Exception:
            pass

    def _clear_cards(self) -> None:
        for child in self.rules_container.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
        self._rows = []

    def _reload_rules(self) -> None:
        self._clear_cards()
        rows = load_rules()
        for rule in rows:
            self._create_rule_card(rule)
        if not rows:
            self._create_rule_card({})
        self._set_status(f"Loaded {len(rows)} rule(s).", "#94a3b8")

    def _add_rule(self) -> None:
        if not self._is_admin:
            return
        self._create_rule_card(
            {
                "id": "",
                "name": "",
                "enabled": True,
                "severity": "warning",
                "trigger": "rule_engine",
                "dedup_window_minutes": 360,
                "message_template": "{machine_id} matched rule.",
                "condition": {"field": "status", "op": "eq", "value": "due"},
            }
        )
        self._set_status("Added new rule draft.", "#94a3b8")

    def _new_condition_row(self, parent: Any, values: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        vals = dict(values or {})
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=6)
        row.grid_columnconfigure(0, weight=3)
        row.grid_columnconfigure(1, weight=2)
        row.grid_columnconfigure(2, weight=4)
        row.grid_columnconfigure(3, weight=0)

        field_var = tk.StringVar(value=str(vals.get("field") or ""))
        op_var = tk.StringVar(value=str(vals.get("op") or "eq"))
        value_var = tk.StringVar(value="" if vals.get("value") is None else str(vals.get("value")))

        field_entry = ctk.CTkEntry(row, textvariable=field_var, height=CONTROL_HEIGHT, font=ENTRY_FONT, placeholder_text="field (e.g. risk_score)")
        field_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        op_menu = ctk.CTkOptionMenu(row, values=OPS, variable=op_var, height=CONTROL_HEIGHT, font=LABEL_FONT)
        op_menu.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        value_entry = ctk.CTkEntry(row, textvariable=value_var, height=CONTROL_HEIGHT, font=ENTRY_FONT, placeholder_text="value")
        value_entry.grid(row=0, column=2, sticky="ew", padx=(0, 8))
        remove_btn = ctk.CTkButton(row, text="Remove", width=108, height=COMPACT_BUTTON_HEIGHT, fg_color="#3f1d1d", hover_color="#7f1d1d", font=("Segoe UI", 13))
        remove_btn.grid(row=0, column=3, sticky="e")

        return {
            "frame": row,
            "field_var": field_var,
            "op_var": op_var,
            "value_var": value_var,
            "field_entry": field_entry,
            "op_menu": op_menu,
            "value_entry": value_entry,
            "remove_btn": remove_btn,
        }

    def _create_rule_card(self, rule: Dict[str, Any]) -> None:
        card = ctk.CTkFrame(self.rules_container, fg_color="#0b1220", corner_radius=14, border_width=1, border_color="#1d2a3f")
        card.pack(fill="x", padx=2, pady=8)

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(14, 8))
        top.grid_columnconfigure(1, weight=1)
        top.grid_columnconfigure(3, weight=2)
        top.grid_columnconfigure(5, weight=1)
        top.grid_columnconfigure(7, weight=0)
        top.grid_columnconfigure(9, weight=0)

        id_var = tk.StringVar(value=str(rule.get("id") or ""))
        name_var = tk.StringVar(value=str(rule.get("name") or ""))
        enabled_var = tk.BooleanVar(value=bool(rule.get("enabled", True)))
        severity_var = tk.StringVar(value=str(rule.get("severity") or "warning"))
        dedup_var = tk.StringVar(value=str(rule.get("dedup_window_minutes", 360)))
        trigger_var = tk.StringVar(value=str(rule.get("trigger") or "rule_engine"))
        mode_var = tk.StringVar(value="all")
        message_var = tk.StringVar(value=str(rule.get("message_template") or ""))

        ctk.CTkLabel(top, text="ID", font=LABEL_FONT, text_color="#94a3b8").grid(row=0, column=0, sticky="w")
        id_entry = ctk.CTkEntry(top, textvariable=id_var, height=CONTROL_HEIGHT, font=ENTRY_FONT, placeholder_text="unique_id")
        id_entry.grid(row=0, column=1, sticky="ew", padx=(6, 12))

        ctk.CTkLabel(top, text="Name", font=LABEL_FONT, text_color="#94a3b8").grid(row=0, column=2, sticky="w")
        name_entry = ctk.CTkEntry(top, textvariable=name_var, height=CONTROL_HEIGHT, font=ENTRY_FONT, placeholder_text="Rule name")
        name_entry.grid(row=0, column=3, sticky="ew", padx=(6, 12))

        ctk.CTkLabel(top, text="Severity", font=LABEL_FONT, text_color="#94a3b8").grid(row=0, column=4, sticky="w")
        severity_menu = ctk.CTkOptionMenu(top, values=["info", "warning", "critical"], variable=severity_var, height=CONTROL_HEIGHT, font=LABEL_FONT)
        severity_menu.grid(row=0, column=5, sticky="ew", padx=(6, 12))

        enabled_chk = ctk.CTkCheckBox(top, text="Enabled", variable=enabled_var, font=LABEL_FONT)
        enabled_chk.grid(row=0, column=6, sticky="w", padx=(0, 12))

        delete_btn = ctk.CTkButton(top, text="Delete Rule", width=116, height=COMPACT_BUTTON_HEIGHT, fg_color="#7f1d1d", hover_color="#991b1b", font=("Segoe UI", 13))
        delete_btn.grid(row=0, column=7, sticky="e")

        ctk.CTkLabel(top, text="Dedup(min)", font=LABEL_FONT, text_color="#94a3b8").grid(row=1, column=0, sticky="w", pady=(8, 0))
        dedup_entry = ctk.CTkEntry(top, textvariable=dedup_var, height=CONTROL_HEIGHT, font=ENTRY_FONT)
        dedup_entry.grid(row=1, column=1, sticky="ew", padx=(6, 12), pady=(8, 0))

        ctk.CTkLabel(top, text="Trigger", font=LABEL_FONT, text_color="#94a3b8").grid(row=1, column=2, sticky="w", pady=(8, 0))
        trigger_entry = ctk.CTkEntry(top, textvariable=trigger_var, height=CONTROL_HEIGHT, font=ENTRY_FONT, placeholder_text="rule_engine")
        trigger_entry.grid(row=1, column=3, sticky="ew", padx=(6, 12), pady=(8, 0))

        ctk.CTkLabel(top, text="Match Mode", font=LABEL_FONT, text_color="#94a3b8").grid(row=1, column=4, sticky="w", pady=(8, 0))
        mode_menu = ctk.CTkOptionMenu(top, values=["all", "any"], variable=mode_var, height=CONTROL_HEIGHT, font=LABEL_FONT)
        mode_menu.grid(row=1, column=5, sticky="ew", padx=(6, 12), pady=(8, 0))

        meta = ctk.CTkFrame(card, fg_color="transparent")
        meta.pack(fill="x", padx=14, pady=(0, 8))
        meta.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(meta, text="Message Template", font=LABEL_FONT, text_color="#94a3b8").grid(row=0, column=0, sticky="w")
        message_entry = ctk.CTkEntry(meta, textvariable=message_var, height=CONTROL_HEIGHT, font=ENTRY_FONT, placeholder_text="{machine_id} ...")
        message_entry.grid(row=0, column=1, sticky="ew", padx=(8, 0))

        body = ctk.CTkFrame(card, fg_color="#0f172a", corner_radius=12)
        body.pack(fill="x", padx=14, pady=(0, 14))

        hint = ctk.CTkLabel(
            body,
            text=f"Conditions use fields like: {', '.join(FIELD_HINTS)}",
            font=("Segoe UI", 12),
            text_color="#64748b",
        )
        hint.pack(anchor="w", padx=10, pady=(8, 4))

        cond_container = ctk.CTkFrame(body, fg_color="transparent")
        cond_container.pack(fill="x", padx=10, pady=(0, 10))

        mode, leaves, advanced = _extract_simple_condition(rule.get("condition") if isinstance(rule.get("condition"), dict) else {})
        mode_var.set(mode if mode in ("all", "any") else "all")
        if not leaves:
            leaves = [{"field": "", "op": "eq", "value": ""}]

        cond_rows: List[Dict[str, Any]] = []
        for leaf in leaves:
            cond_row = self._new_condition_row(cond_container, leaf)
            cond_rows.append(cond_row)

        controls = ctk.CTkFrame(body, fg_color="transparent")
        controls.pack(fill="x", padx=10, pady=(0, 8))
        add_cond_btn = ctk.CTkButton(
            controls,
            text="+ Add Condition",
            width=150,
            height=COMPACT_BUTTON_HEIGHT,
            fg_color="#1e293b",
            hover_color="#334155",
            font=("Segoe UI", 13),
        )
        add_cond_btn.pack(side="left")

        advanced_note = ctk.CTkLabel(
            controls,
            text="",
            font=("Segoe UI", 12),
            text_color="#f59e0b",
        )
        advanced_note.pack(side="left", padx=(10, 0))

        row_state: Dict[str, Any] = {
            "card": card,
            "id_var": id_var,
            "name_var": name_var,
            "enabled_var": enabled_var,
            "severity_var": severity_var,
            "dedup_var": dedup_var,
            "trigger_var": trigger_var,
            "mode_var": mode_var,
            "message_var": message_var,
            "condition_rows": cond_rows,
            "condition_parent": cond_container,
            "advanced": bool(advanced),
            "advanced_condition": dict(rule.get("condition") or {}) if advanced else None,
            "widgets": [
                id_entry,
                name_entry,
                enabled_chk,
                severity_menu,
                dedup_entry,
                trigger_entry,
                mode_menu,
                message_entry,
                add_cond_btn,
                delete_btn,
            ],
        }

        def _remove_condition(cond: Dict[str, Any]) -> None:
            if not self._is_admin:
                return
            if row_state.get("advanced"):
                return
            rows = row_state["condition_rows"]
            if len(rows) <= 1:
                return
            try:
                cond["frame"].destroy()
            except Exception:
                pass
            row_state["condition_rows"] = [item for item in rows if item is not cond]

        def _add_condition() -> None:
            if not self._is_admin:
                return
            if row_state.get("advanced"):
                return
            cond = self._new_condition_row(row_state["condition_parent"], {"field": "", "op": "eq", "value": ""})
            cond["remove_btn"].configure(command=lambda c=cond: _remove_condition(c))
            row_state["condition_rows"].append(cond)
            row_state["widgets"].extend([cond["field_entry"], cond["op_menu"], cond["value_entry"], cond["remove_btn"]])
            if not self._is_admin:
                for widget in [cond["field_entry"], cond["op_menu"], cond["value_entry"], cond["remove_btn"]]:
                    try:
                        widget.configure(state="disabled")
                    except Exception:
                        pass

        add_cond_btn.configure(command=_add_condition)
        delete_btn.configure(command=lambda: self._delete_rule_card(row_state))

        for cond in cond_rows:
            cond["remove_btn"].configure(command=lambda c=cond: _remove_condition(c))
            row_state["widgets"].extend([cond["field_entry"], cond["op_menu"], cond["value_entry"], cond["remove_btn"]])

        if advanced:
            advanced_note.configure(text="Advanced nested condition detected. Preserved as read-only in basic editor.")
            row_state["advanced"] = True
            for widget in [mode_menu, add_cond_btn]:
                try:
                    widget.configure(state="disabled")
                except Exception:
                    pass
            for cond in cond_rows:
                for widget in [cond["field_entry"], cond["op_menu"], cond["value_entry"], cond["remove_btn"]]:
                    try:
                        widget.configure(state="disabled")
                    except Exception:
                        pass

        if not self._is_admin:
            for widget in row_state["widgets"]:
                try:
                    widget.configure(state="disabled")
                except Exception:
                    pass

        self._rows.append(row_state)

    def _delete_rule_card(self, row_state: Dict[str, Any]) -> None:
        if not self._is_admin:
            return
        if len(self._rows) <= 1:
            if not messagebox.askyesno("Delete rule", "This is the last rule card. Remove it?"):
                return
        try:
            row_state["card"].destroy()
        except Exception:
            pass
        self._rows = [row for row in self._rows if row is not row_state]
        self._set_status("Rule removed.", "#94a3b8")

    def _parse_value(self, text: str, op: str) -> Any:
        op_norm = str(op or "eq").strip().lower()
        if op_norm in {"exists", "truthy"}:
            return True
        raw = str(text or "").strip()
        if op_norm in {"in", "between"}:
            parts = [part.strip() for part in raw.split(",") if part.strip()]
            return [_auto_parse_scalar(part) for part in parts]
        return _auto_parse_scalar(raw)

    def _serialize_rule(self, row: Dict[str, Any], seen_ids: set[str]) -> Dict[str, Any]:
        rule_id = str(row["id_var"].get() or "").strip()
        if not rule_id:
            raise ValueError("Every rule must have an ID.")
        if rule_id in seen_ids:
            raise ValueError(f"Duplicate rule ID: {rule_id}")
        seen_ids.add(rule_id)

        name = str(row["name_var"].get() or "").strip() or rule_id
        severity = str(row["severity_var"].get() or "warning").strip().lower() or "warning"
        trigger = str(row["trigger_var"].get() or "rule_engine").strip().lower() or "rule_engine"
        message_template = str(row["message_var"].get() or "").strip()
        try:
            dedup_window_minutes = max(30, int(float(row["dedup_var"].get() or 360)))
        except Exception:
            dedup_window_minutes = 360

        condition: Dict[str, Any]
        if row.get("advanced"):
            condition = dict(row.get("advanced_condition") or {})
        else:
            leaves: List[Dict[str, Any]] = []
            for cond in row.get("condition_rows") or []:
                field = str(cond["field_var"].get() or "").strip()
                if not field:
                    continue
                op = str(cond["op_var"].get() or "eq").strip().lower() or "eq"
                value = self._parse_value(str(cond["value_var"].get() or ""), op)
                leaf: Dict[str, Any] = {"field": field, "op": op}
                if op not in {"exists", "truthy"}:
                    leaf["value"] = value
                leaves.append(leaf)
            condition = _build_condition(row["mode_var"].get(), leaves)

        if not condition:
            raise ValueError(f"Rule '{rule_id}' has no valid condition.")

        return {
            "id": rule_id,
            "name": name,
            "enabled": bool(row["enabled_var"].get()),
            "severity": severity,
            "trigger": trigger,
            "dedup_window_minutes": dedup_window_minutes,
            "condition": condition,
            "message_template": message_template,
        }

    def _save_all(self) -> None:
        if not self._is_admin:
            return
        try:
            seen_ids: set[str] = set()
            rows: List[Dict[str, Any]] = []
            for row in self._rows:
                rows.append(self._serialize_rule(row, seen_ids))
            saved = save_rules(rows)
            self._set_status(f"Saved {len(saved)} rule(s).", "#22c55e")
        except Exception as exc:
            self._set_status(f"Save failed: {exc}", "#ef4444")
            messagebox.showerror("Rule Engine", f"Could not save rules.\n\n{exc}")
