"""Modern login UI for the SMS alert application."""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Optional

try:
    from ..app_paths import data_path, resource_path
    from ..mine_store import get_active_mine
except Exception:
    from app_paths import data_path, resource_path
    from mine_store import get_active_mine

from .gradient import GradientPanel

try:
    from PIL import Image
except Exception:
    Image = None


try:
    import customtkinter as ctk
except Exception:
    import tkinter as tk

    def _to_bg(master: Any, fg_color: Optional[str]) -> Optional[str]:
        if not fg_color or fg_color == "transparent":
            try:
                return master.cget("bg")
            except Exception:
                return None
        return fg_color

    class _CTkFrame(tk.Frame):
        def __init__(
            self,
            master: Any = None,
            fg_color: Optional[str] = None,
            corner_radius: Optional[int] = None,
            border_width: Optional[int] = None,
            border_color: Optional[str] = None,
            **kwargs: Any,
        ) -> None:
            kwargs.pop("width", None)
            kwargs.pop("height", None)
            bg = _to_bg(master, fg_color)
            if bg:
                kwargs.setdefault("bg", bg)
            super().__init__(master, **kwargs)

    class _CTkLabel(tk.Label):
        def __init__(
            self,
            master: Any = None,
            text_color: Optional[str] = None,
            fg_color: Optional[str] = None,
            **kwargs: Any,
        ) -> None:
            kwargs.pop("corner_radius", None)
            if text_color:
                kwargs.setdefault("fg", text_color)
            bg = _to_bg(master, fg_color)
            if bg:
                kwargs.setdefault("bg", bg)
            super().__init__(master, **kwargs)

    class _CTkButton(tk.Button):
        def __init__(
            self,
            master: Any = None,
            text_color: Optional[str] = None,
            fg_color: Optional[str] = None,
            hover_color: Optional[str] = None,
            corner_radius: Optional[int] = None,
            border_width: Optional[int] = None,
            border_color: Optional[str] = None,
            **kwargs: Any,
        ) -> None:
            kwargs.pop("width", None)
            kwargs.pop("height", None)
            if text_color:
                kwargs.setdefault("fg", text_color)
            bg = _to_bg(master, fg_color)
            if bg:
                kwargs.setdefault("bg", bg)
                kwargs.setdefault("activebackground", bg)
            super().__init__(master, **kwargs)

    class _CTkEntry(tk.Entry):
        def __init__(
            self,
            master: Any = None,
            placeholder_text: Optional[str] = None,
            text_color: Optional[str] = None,
            fg_color: Optional[str] = None,
            placeholder_text_color: Optional[str] = None,
            show: Optional[str] = None,
            **kwargs: Any,
        ) -> None:
            kwargs.pop("height", None)
            kwargs.pop("corner_radius", None)
            kwargs.pop("border_width", None)
            kwargs.pop("border_color", None)
            if text_color:
                kwargs.setdefault("fg", text_color)
            bg = _to_bg(master, fg_color)
            if bg:
                kwargs.setdefault("bg", bg)
                kwargs.setdefault("insertbackground", text_color or "#000000")
            super().__init__(master, **kwargs)
            self._placeholder = placeholder_text or ""
            self._placeholder_color = placeholder_text_color or "#666666"
            self._default_fg = self.cget("fg")
            self._is_placeholder = False
            self._show_char = show or ""
            if show:
                self.config(show=show)
            if self._placeholder:
                self._apply_placeholder()
                self.bind("<FocusIn>", self._on_focus_in)
                self.bind("<FocusOut>", self._on_focus_out)

        def _apply_placeholder(self) -> None:
            if self.get():
                return
            self._is_placeholder = True
            self.config(fg=self._placeholder_color, show="")
            self.insert(0, self._placeholder)

        def _on_focus_in(self, _event: Any) -> None:
            if self._is_placeholder:
                self.delete(0, "end")
                self.config(fg=self._default_fg, show=self._show_char)
                self._is_placeholder = False

        def _on_focus_out(self, _event: Any) -> None:
            if not self.get():
                self._apply_placeholder()

    class _CTkCheckBox(tk.Checkbutton):
        def __init__(
            self,
            master: Any = None,
            text_color: Optional[str] = None,
            fg_color: Optional[str] = None,
            hover_color: Optional[str] = None,
            checkbox_width: Optional[int] = None,
            checkbox_height: Optional[int] = None,
            **kwargs: Any,
        ) -> None:
            if text_color:
                kwargs.setdefault("fg", text_color)
            bg = _to_bg(master, fg_color)
            if bg:
                kwargs.setdefault("bg", bg)
                kwargs.setdefault("activebackground", bg)
            super().__init__(master, **kwargs)

    class _CTkToplevel(tk.Toplevel):
        pass

    class _CTkModule:
        CTkFrame = _CTkFrame
        CTkLabel = _CTkLabel
        CTkButton = _CTkButton
        CTkEntry = _CTkEntry
        CTkCheckBox = _CTkCheckBox
        CTkToplevel = _CTkToplevel
        BooleanVar = tk.BooleanVar

        @staticmethod
        def set_appearance_mode(*_args: Any, **_kwargs: Any) -> None:
            return

        @staticmethod
        def set_default_color_theme(*_args: Any, **_kwargs: Any) -> None:
            return

    ctk = _CTkModule()  # type: ignore[assignment]


import tkinter as tk


SRC_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[2]
PREFS_FILE = data_path("login_prefs.json")

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from auth import authenticate, update_user_password, update_username

try:
    from google_oauth import GoogleOAuthError, is_google_oauth_available, login_with_google
except Exception:
    class GoogleOAuthError(RuntimeError):
        pass

    def is_google_oauth_available() -> tuple[bool, str]:
        return False, "Google OAuth module is unavailable."

    def login_with_google(timeout_sec: int = 180) -> dict:
        raise GoogleOAuthError("Google OAuth module is unavailable.")

try:
    from .theme import SIMPLE_PALETTE
except Exception:
    from ui.theme import SIMPLE_PALETTE  # type: ignore


LOGGER = logging.getLogger(__name__)

PALETTE = {
    "bg": SIMPLE_PALETTE.get("bg", "#0b1220"),
    "hero": "#0f1b33",
    "panel": "#0c1629",
    "input": "#091120",
    "border": "#243247",
    "title": "#f8fafc",
    "text": "#cbd5e1",
    "muted": "#94a3b8",
    "accent": SIMPLE_PALETTE.get("accent", "#4f46e5"),
    "primary": SIMPLE_PALETTE.get("primary", "#06b6d4"),
    "primary_hover": "#0891b2",
    "link_hover": "#17253b",
    "danger": "#f87171",
    "success": "#34d399",
    "warning": "#fbbf24",
}


class LoginWindow(ctk.CTkFrame):
    """Modern and responsive login frame."""

    def __init__(self, master: Any, on_success: Optional[Callable[[dict], None]] = None) -> None:
        super().__init__(master, fg_color=PALETTE["bg"])
        self.on_success = on_success
        self.login_successful = False
        self.authenticated_user: Optional[dict] = None
        self._google_login_available, self._google_login_reason = is_google_oauth_available()
        self._pw_visible = False
        self._destroying = False

        self._install_callback_exception_handler(master)
        self._set_window_icon(master)
        self._build_layout()
        self._load_login_preferences()

    def _install_callback_exception_handler(self, master: Any) -> None:
        def _report_callback_exception(exc: Any, value: Any, tb: Any) -> None:
            if isinstance(value, Exception) and "invalid command name" in str(value):
                return
            LOGGER.exception("Tcl callback exception", exc_info=(exc, value, tb))

        try:
            master.report_callback_exception = _report_callback_exception
        except Exception:
            pass

    def _set_window_icon(self, master: Any) -> None:
        try:
            icon_path = resource_path("assets", "icons", "OIP.ico")
            if icon_path.exists():
                try:
                    master.iconbitmap(str(icon_path))
                except Exception:
                    pass
        except Exception:
            pass

    def _build_layout(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.shell = ctk.CTkFrame(self, fg_color="transparent")
        self.shell.grid(row=0, column=0, sticky="nsew", padx=26, pady=26)
        self.shell.grid_rowconfigure(0, weight=1)
        self.shell.grid_columnconfigure(0, weight=7, uniform="login")
        self.shell.grid_columnconfigure(1, weight=8, uniform="login")

        self.hero_panel = GradientPanel(
            self.shell,
            colors=("#0f172a", "#1d4ed8", "#0891b2"),
            corner_radius=20,
            border_color="#1d2a3f",
        )
        self.hero_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self._build_hero_panel(self.hero_panel)

        self.form_panel = ctk.CTkFrame(self.shell, fg_color="#0a1422", corner_radius=20, border_width=1, border_color="#1d2a3f")
        self.form_panel.grid(row=0, column=1, sticky="nsew", padx=(12, 0))
        self._build_form_panel(self.form_panel)

        self.bind("<Configure>", self._on_resize)
        self.after(0, self._arrange_layout)

    def _on_resize(self, _event: Any) -> None:
        self._arrange_layout()

    def _arrange_layout(self) -> None:
        width = self.winfo_width()
        if width <= 1:
            return

        if width < 980:
            self.shell.grid_columnconfigure(0, weight=1, uniform="")
            self.shell.grid_columnconfigure(1, weight=0, uniform="")
            self.shell.grid_rowconfigure(0, weight=0)
            self.shell.grid_rowconfigure(1, weight=1)
            self.hero_panel.grid(row=0, column=0, sticky="ew", padx=0, pady=(0, 12))
            self.form_panel.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
            return

        self.shell.grid_columnconfigure(0, weight=7, uniform="login")
        self.shell.grid_columnconfigure(1, weight=8, uniform="login")
        self.shell.grid_rowconfigure(0, weight=1)
        self.shell.grid_rowconfigure(1, weight=0)
        self.hero_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 12), pady=0)
        self.form_panel.grid(row=0, column=1, sticky="nsew", padx=(12, 0), pady=0)

    def _active_mine_context(self) -> dict[str, str]:
        try:
            mine = get_active_mine() or {}
        except Exception:
            mine = {}
        return {
            "mine_id": str(mine.get("id") or "").strip(),
            "mine_name": str(mine.get("mine_name") or "").strip(),
            "company_name": str(mine.get("company_name") or "").strip(),
            "quarry_type": str(mine.get("quarry_type") or "").strip(),
            "lease_area": str(mine.get("lease_area") or "").strip(),
            "logo_path": str(mine.get("logo_path") or "").strip(),
        }

    def _mine_branding_line(self, mine: dict[str, str]) -> str:
        parts = [
            mine.get("company_name") or "",
            mine.get("quarry_type") or "",
            f"Lease Area: {mine.get('lease_area')}" if mine.get("lease_area") else "",
        ]
        text = " | ".join(part for part in parts if part)
        return text or "Configure the active mine profile to brand the workspace by site."

    def _set_logo_preview(self, widget: Any, logo_path: str) -> None:
        if widget is None:
            return
        if Image is None or not hasattr(ctk, "CTkImage"):
            try:
                widget._logo_image = None
                widget.configure(image=None, text="Mine Logo")
            except Exception:
                pass
            return

        candidates = []
        raw_logo = str(logo_path or "").strip()
        if raw_logo:
            candidates.append(Path(raw_logo))
        try:
            default_icon = resource_path("assets", "icons", "OIP.ico")
            if default_icon.exists():
                candidates.append(default_icon)
        except Exception:
            pass

        for candidate in candidates:
            try:
                if not candidate or not candidate.exists():
                    continue
                image = Image.open(candidate)
                image.thumbnail((90, 90))
                logo = ctk.CTkImage(light_image=image, dark_image=image, size=image.size)
                widget._logo_image = logo
                widget.configure(image=logo, text="")
                return
            except Exception:
                continue

        try:
            widget._logo_image = None
            widget.configure(image=None, text="Mine Logo")
        except Exception:
            pass

    def _build_hero_panel(self, parent: Any) -> None:
        host = getattr(parent, "content", parent)
        host.grid_columnconfigure(0, weight=1)
        mine = self._active_mine_context()

        brand = ctk.CTkLabel(
            host,
            text="MINING MAINTENANCE SYSTEM",
            font=("Segoe UI Semibold", 14),
            text_color=PALETTE["warning"],
        )
        brand.pack(anchor="w", padx=28, pady=(30, 10))

        title = ctk.CTkLabel(
            host,
            text="Operations control in one place",
            font=("Segoe UI Semibold", 34),
            text_color=PALETTE["title"],
            justify="left",
            wraplength=360,
        )
        title.pack(anchor="w", padx=28)

        subtitle = ctk.CTkLabel(
            host,
            text=(
                f"Track machine health, schedule work, and keep teams aligned for {mine['mine_name']}."
                if mine.get("mine_name")
                else "Track machine health, schedule work, and keep teams aligned with instant alerts."
            ),
            font=("Segoe UI", 16),
            text_color=PALETTE["text"],
            justify="left",
            wraplength=360,
        )
        subtitle.pack(anchor="w", padx=28, pady=(12, 24))

        mine_card = ctk.CTkFrame(host, fg_color="#07111d", corner_radius=14, border_width=1, border_color="#1f2937")
        mine_card.pack(fill="x", padx=28, pady=(0, 18))
        ctk.CTkLabel(
            mine_card,
            text="Active Mine Branding",
            font=("Segoe UI Semibold", 12),
            text_color=PALETTE["warning"],
        ).pack(anchor="w", padx=14, pady=(12, 4))
        mine_brand_row = ctk.CTkFrame(mine_card, fg_color="transparent")
        mine_brand_row.pack(fill="x", padx=14, pady=(0, 12))
        self._login_mine_logo = ctk.CTkLabel(
            mine_brand_row,
            text="Mine Logo",
            width=92,
            height=92,
            corner_radius=14,
            fg_color="#0f172a",
            text_color=PALETTE["muted"],
            font=("Segoe UI Semibold", 12),
        )
        self._login_mine_logo.pack(side="left", padx=(0, 12))
        self._set_logo_preview(self._login_mine_logo, mine.get("logo_path") or "")
        brand_text = ctk.CTkFrame(mine_brand_row, fg_color="transparent")
        brand_text.pack(side="left", fill="both", expand=True)
        ctk.CTkLabel(
            brand_text,
            text=mine.get("mine_name") or "Mine details not configured yet",
            font=("Segoe UI Semibold", 18),
            text_color=PALETTE["title"],
            wraplength=320,
            justify="left",
        ).pack(anchor="w")
        ctk.CTkLabel(
            brand_text,
            text=self._mine_branding_line(mine),
            font=("Segoe UI", 12),
            text_color=PALETTE["muted"],
            wraplength=320,
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

        for feature in (
            "Real-time maintenance workflow visibility",
            "Role-based access for operators and admin",
            "Integrated SMS alert and checklist tracking",
        ):
            line = ctk.CTkLabel(
                host,
                text=f"- {feature}",
                font=("Segoe UI", 14),
                text_color=PALETTE["muted"],
                justify="left",
                wraplength=360,
            )
            line.pack(anchor="w", padx=28, pady=4)

    def _build_form_panel(self, parent: Any) -> None:
        parent.grid_columnconfigure(0, weight=1)
        mine = self._active_mine_context()

        heading = ctk.CTkLabel(
            parent,
            text=f"Welcome to {mine['mine_name']}" if mine.get("mine_name") else "Welcome back",
            font=("Segoe UI Semibold", 30),
            text_color=PALETTE["title"],
        )
        heading.pack(anchor="w", padx=28, pady=(34, 4))

        subheading = ctk.CTkLabel(
            parent,
            text=(
                f"Sign in to continue operations for {mine['company_name']}"
                if mine.get("company_name")
                else "Sign in to continue"
            ),
            font=("Segoe UI", 14),
            text_color=PALETTE["muted"],
        )
        subheading.pack(anchor="w", padx=28, pady=(0, 24))

        ctk.CTkLabel(
            parent,
            text="Username",
            font=("Segoe UI Semibold", 13),
            text_color=PALETTE["text"],
        ).pack(anchor="w", padx=28, pady=(0, 6))

        self.username_entry = ctk.CTkEntry(
            parent,
            placeholder_text="Enter your username",
            height=44,
            corner_radius=10,
            fg_color=PALETTE["input"],
            text_color=PALETTE["title"],
            placeholder_text_color=PALETTE["muted"],
            border_width=1,
            border_color=PALETTE["border"],
            font=("Segoe UI", 14),
        )
        self.username_entry.pack(fill="x", padx=28, pady=(0, 14))

        ctk.CTkLabel(
            parent,
            text="Password",
            font=("Segoe UI Semibold", 13),
            text_color=PALETTE["text"],
        ).pack(anchor="w", padx=28, pady=(0, 6))

        password_row = ctk.CTkFrame(parent, fg_color="transparent")
        password_row.pack(fill="x", padx=28, pady=(0, 14))
        password_row.grid_columnconfigure(0, weight=1)
        password_row.grid_columnconfigure(1, weight=0)

        self.password_entry = ctk.CTkEntry(
            password_row,
            placeholder_text="Enter your password",
            show="*",
            height=44,
            corner_radius=10,
            fg_color=PALETTE["input"],
            text_color=PALETTE["title"],
            placeholder_text_color=PALETTE["muted"],
            border_width=1,
            border_color=PALETTE["border"],
            font=("Segoe UI", 14),
        )
        self.password_entry.grid(row=0, column=0, sticky="ew")

        self.password_toggle_btn = ctk.CTkButton(
            password_row,
            text="Show",
            command=self._toggle_password_visibility,
            width=84,
            height=44,
            corner_radius=10,
            fg_color=PALETTE["link_hover"],
            hover_color=PALETTE["border"],
            text_color=PALETTE["title"],
            font=("Segoe UI Semibold", 12),
        )
        self.password_toggle_btn.grid(row=0, column=1, padx=(10, 0))

        try:
            self.remember_var = ctk.BooleanVar(value=False)
        except Exception:
            self.remember_var = tk.BooleanVar(value=False)

        remember_row = ctk.CTkFrame(parent, fg_color="transparent")
        remember_row.pack(fill="x", padx=28, pady=(0, 10))

        try:
            remember = ctk.CTkCheckBox(
                remember_row,
                text="Remember username",
                variable=self.remember_var,
                text_color=PALETTE["text"],
                fg_color=PALETTE["primary"],
                hover_color=PALETTE["primary_hover"],
                checkbox_width=18,
                checkbox_height=18,
                font=("Segoe UI", 12),
            )
        except Exception:
            remember = ctk.CTkCheckBox(
                remember_row,
                text="Remember username",
                variable=self.remember_var,
            )
        remember.pack(side="left")

        self.msg = ctk.CTkLabel(
            parent,
            text="",
            font=("Segoe UI", 12),
            text_color=PALETTE["muted"],
            justify="left",
        )
        self.msg.pack(fill="x", padx=28, pady=(0, 10))

        self.login_btn = ctk.CTkButton(
            parent,
            text="Sign In",
            command=self._on_login,
            height=48,
            corner_radius=12,
            fg_color=PALETTE["primary"],
            hover_color=PALETTE["primary_hover"],
            text_color="#001219",
            font=("Segoe UI Semibold", 15),
        )
        self.login_btn.pack(fill="x", padx=28, pady=(0, 14))

        divider_row = ctk.CTkFrame(parent, fg_color="transparent")
        divider_row.pack(fill="x", padx=28, pady=(0, 10))
        ctk.CTkLabel(
            divider_row,
            text="or",
            font=("Segoe UI", 12),
            text_color=PALETTE["muted"],
        ).pack()

        self.google_login_btn = ctk.CTkButton(
            parent,
            text="Continue with Google",
            command=self._on_google_login,
            height=44,
            corner_radius=11,
            fg_color="#1f2937",
            hover_color="#111827",
            text_color=PALETTE["title"],
            font=("Segoe UI Semibold", 14),
        )
        self.google_login_btn.pack(fill="x", padx=28, pady=(0, 8))

        if not self._google_login_available:
            self.google_login_btn.configure(state="disabled")
            ctk.CTkLabel(
                parent,
                text=self._google_login_reason,
                font=("Segoe UI", 11),
                text_color=PALETTE["muted"],
                justify="left",
                wraplength=420,
            ).pack(fill="x", padx=28, pady=(0, 10))
        else:
            ctk.CTkLabel(
                parent,
                text="Use your Gmail account to log in instantly.",
                font=("Segoe UI", 11),
                text_color=PALETTE["muted"],
            ).pack(fill="x", padx=28, pady=(0, 10))

        links = ctk.CTkFrame(parent, fg_color="transparent")
        links.pack(fill="x", padx=28, pady=(0, 20))
        links.grid_columnconfigure(0, weight=1)
        links.grid_columnconfigure(1, weight=1)

        self._make_link_button(
            links,
            text="Forgot Password",
            command=self._forgot_password,
        ).grid(row=0, column=0, sticky="w")

        self._make_link_button(
            links,
            text="Manage Account",
            command=self._manage_account,
        ).grid(row=0, column=1, sticky="e")

        self.username_entry.bind("<Return>", lambda _e: self._on_login())
        self.password_entry.bind("<Return>", lambda _e: self._on_login())
        self.after(120, lambda: self.username_entry.focus_set())

    def _make_link_button(self, parent: Any, text: str, command: Callable[[], None]) -> Any:
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            fg_color="transparent",
            hover_color=PALETTE["link_hover"],
            text_color=PALETTE["warning"],
            font=("Segoe UI", 12),
            width=130,
            height=30,
            corner_radius=8,
        )

    def _toggle_password_visibility(self) -> None:
        self._pw_visible = not self._pw_visible
        self.password_entry.configure(show="" if self._pw_visible else "*")
        self.password_toggle_btn.configure(text="Hide" if self._pw_visible else "Show")

    def _set_status(self, text: str, level: str = "info") -> None:
        color_map = {
            "info": PALETTE["muted"],
            "success": PALETTE["success"],
            "error": PALETTE["danger"],
        }
        try:
            self.msg.configure(text=text, text_color=color_map.get(level, PALETTE["muted"]))
        except Exception:
            self.msg.configure(text=text)

    def _set_login_button_busy(self, busy: bool) -> None:
        if busy:
            self.login_btn.configure(state="disabled", text="Signing In...")
            try:
                self.google_login_btn.configure(state="disabled")
            except Exception:
                pass
        else:
            self.login_btn.configure(state="normal", text="Sign In")
            try:
                if self._google_login_available:
                    self.google_login_btn.configure(state="normal", text="Continue with Google")
                else:
                    self.google_login_btn.configure(state="disabled", text="Continue with Google")
            except Exception:
                pass

    def _set_google_button_busy(self, busy: bool) -> None:
        if busy:
            self.google_login_btn.configure(state="disabled", text="Opening Google...")
            self.login_btn.configure(state="disabled")
        else:
            self.google_login_btn.configure(text="Continue with Google")
            if self._google_login_available:
                self.google_login_btn.configure(state="normal")
            else:
                self.google_login_btn.configure(state="disabled")
            self.login_btn.configure(state="normal", text="Sign In")

    def _prefs_payload(self, username: str) -> dict:
        if not username:
            return {"remembered_username": ""}
        return {"remembered_username": username}

    def _load_login_preferences(self) -> None:
        try:
            if not PREFS_FILE.exists():
                return
            data = json.loads(PREFS_FILE.read_text(encoding="utf-8"))
            remembered = str(data.get("remembered_username", "")).strip()
            if remembered:
                self.username_entry.delete(0, "end")
                self.username_entry.insert(0, remembered)
                try:
                    self.remember_var.set(True)
                except Exception:
                    pass
        except Exception:
            LOGGER.exception("Failed to load login preferences")

    def _save_login_preferences(self, username: str) -> None:
        try:
            PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
            payload = self._prefs_payload(username)
            PREFS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception:
            LOGGER.exception("Failed to save login preferences")

    def _on_login(self) -> None:
        username = self._entry_text(self.username_entry).strip()
        password = self._entry_text(self.password_entry)

        if not username or not password:
            self._set_status("Enter both username and password.", "error")
            return

        self._set_login_button_busy(True)
        self.update_idletasks()

        try:
            user = authenticate(username, password)
        except Exception as exc:
            LOGGER.exception("Authentication error")
            self._set_status(f"Authentication error: {exc}", "error")
            self._set_login_button_busy(False)
            return

        if not user:
            self._set_status("Invalid username or password.", "error")
            self._set_login_button_busy(False)
            return

        remember_username = username if bool(self.remember_var.get()) else ""
        self._save_login_preferences(remember_username)

        self.login_successful = True
        self.authenticated_user = user
        display_name = str(user.get("name") or user.get("username") or "User")
        self._set_status(f"Welcome {display_name}. Opening dashboard...", "success")

        if self.on_success:
            self.after(120, lambda: self.on_success(user))

    def _on_google_login(self) -> None:
        if not self._google_login_available:
            self._set_status(self._google_login_reason, "error")
            return

        self._set_status("Opening Google sign-in. Complete login in your browser.", "info")
        self._set_google_button_busy(True)

        def worker() -> None:
            try:
                google_user = login_with_google(timeout_sec=240)
            except GoogleOAuthError as exc:
                self.after(0, lambda: self._on_google_login_error(str(exc)))
            except Exception as exc:
                LOGGER.exception("Google login failed")
                self.after(0, lambda: self._on_google_login_error(f"Google login failed: {exc}"))
            else:
                self.after(0, lambda: self._on_google_login_success(google_user))

        threading.Thread(target=worker, daemon=True).start()

    def _on_google_login_error(self, message: str) -> None:
        self._set_google_button_busy(False)
        self._set_status(message, "error")

    def _on_google_login_success(self, user: dict) -> None:
        self._set_google_button_busy(False)

        email = str(user.get("email") or user.get("username") or "").strip()
        if email:
            try:
                self.username_entry.delete(0, "end")
                self.username_entry.insert(0, email)
            except Exception:
                pass
        remember_username = email if bool(self.remember_var.get()) else ""
        self._save_login_preferences(remember_username)

        self.login_successful = True
        self.authenticated_user = user
        display_name = str(user.get("name") or user.get("username") or "User")
        self._set_status(f"Welcome {display_name}. Opening dashboard...", "success")
        if self.on_success:
            self.after(120, lambda: self.on_success(user))

    def _create_dialog(self, title: str, width: int, height: int) -> tuple[Any, Any, Any]:
        win = ctk.CTkToplevel(self)
        win.title(title)
        win.geometry(f"{width}x{height}")
        win.resizable(False, False)
        try:
            win.transient(self.winfo_toplevel())
            win.grab_set()
        except Exception:
            pass

        root = ctk.CTkFrame(win, fg_color=PALETTE["panel"], corner_radius=0)
        root.pack(fill="both", expand=True, padx=14, pady=14)

        heading = ctk.CTkLabel(
            root,
            text=title,
            font=("Segoe UI Semibold", 22),
            text_color=PALETTE["title"],
        )
        heading.pack(anchor="w", pady=(4, 10))

        status = ctk.CTkLabel(root, text="", font=("Segoe UI", 12), text_color=PALETTE["muted"])
        status.pack(side="bottom", anchor="w", pady=(8, 0))
        return win, root, status

    def _forgot_password(self) -> None:
        win, root, status = self._create_dialog("Reset Password", 460, 340)

        self._modal_label(root, "Username")
        uname = self._modal_entry(root, "Existing username")

        self._modal_label(root, "New password")
        newpw = self._modal_entry(root, "Enter new password", show="*")

        self._modal_label(root, "Confirm password")
        confpw = self._modal_entry(root, "Re-enter new password", show="*")

        def submit() -> None:
            username = uname.get().strip()
            password_1 = newpw.get()
            password_2 = confpw.get()

            if not username or not password_1:
                self._set_modal_status(status, "Username and new password are required.", "error")
                return
            if password_1 != password_2:
                self._set_modal_status(status, "Passwords do not match.", "error")
                return
            if len(password_1) < 4:
                self._set_modal_status(status, "Password should be at least 4 characters.", "error")
                return

            updated = update_user_password(username, password_1)
            if not updated:
                self._set_modal_status(
                    status,
                    "Unable to reset this account. Check username or use admin panel.",
                    "error",
                )
                return

            self._set_modal_status(status, "Password updated successfully.", "success")
            win.after(900, win.destroy)

        submit_btn = ctk.CTkButton(
            root,
            text="Reset Password",
            command=submit,
            fg_color=PALETTE["primary"],
            hover_color=PALETTE["primary_hover"],
            text_color="#001219",
            font=("Segoe UI Semibold", 13),
            height=40,
            corner_radius=10,
        )
        submit_btn.pack(fill="x", pady=(10, 0))

    def _manage_account(self) -> None:
        win, root, status = self._create_dialog("Manage Account", 500, 430)

        self._modal_label(root, "Current username")
        current_username = self._modal_entry(root, "Username to update")

        self._modal_label(root, "New username (optional)")
        new_username = self._modal_entry(root, "Leave blank to keep current username")

        self._modal_label(root, "New password (optional)")
        new_password = self._modal_entry(root, "Leave blank to keep current password", show="*")

        self._modal_label(root, "Confirm new password")
        confirm_password = self._modal_entry(root, "Re-enter new password", show="*")

        def submit() -> None:
            current = current_username.get().strip()
            target_username = new_username.get().strip()
            password_value = new_password.get()
            password_confirm = confirm_password.get()

            if not current:
                self._set_modal_status(status, "Current username is required.", "error")
                return

            if password_value and password_value != password_confirm:
                self._set_modal_status(status, "New passwords do not match.", "error")
                return

            changed = False
            final_username = current

            if target_username:
                renamed = update_username(current, target_username)
                if not renamed:
                    self._set_modal_status(
                        status,
                        "Could not change username. It may already exist.",
                        "error",
                    )
                    return
                changed = True
                final_username = target_username

            if password_value:
                updated = update_user_password(final_username, password_value)
                if not updated:
                    self._set_modal_status(
                        status,
                        "Could not change password for this account.",
                        "error",
                    )
                    return
                changed = True

            if changed:
                self._set_modal_status(status, "Account details updated.", "success")
            else:
                self._set_modal_status(status, "No changes were made.", "info")

        apply_btn = ctk.CTkButton(
            root,
            text="Apply Changes",
            command=submit,
            fg_color=PALETTE["primary"],
            hover_color=PALETTE["primary_hover"],
            text_color="#001219",
            font=("Segoe UI Semibold", 13),
            height=40,
            corner_radius=10,
        )
        apply_btn.pack(fill="x", pady=(12, 0))

    def _modal_label(self, parent: Any, text: str) -> None:
        ctk.CTkLabel(
            parent,
            text=text,
            font=("Segoe UI Semibold", 12),
            text_color=PALETTE["text"],
        ).pack(anchor="w", pady=(8, 4))

    def _modal_entry(self, parent: Any, placeholder: str, show: str = "") -> Any:
        entry = ctk.CTkEntry(
            parent,
            placeholder_text=placeholder,
            show=show,
            height=38,
            corner_radius=10,
            fg_color=PALETTE["input"],
            text_color=PALETTE["title"],
            placeholder_text_color=PALETTE["muted"],
            border_color=PALETTE["border"],
            border_width=1,
            font=("Segoe UI", 13),
        )
        entry.pack(fill="x", pady=(0, 2))
        return entry

    def _set_modal_status(self, label: Any, text: str, level: str = "info") -> None:
        color_map = {
            "info": PALETTE["muted"],
            "success": PALETTE["success"],
            "error": PALETTE["danger"],
        }
        try:
            label.configure(text=text, text_color=color_map.get(level, PALETTE["muted"]))
        except Exception:
            label.configure(text=text)

    def _entry_text(self, entry: Any) -> str:
        if getattr(entry, "_is_placeholder", False):
            return ""
        return entry.get()

    def destroy(self) -> None:
        """Destroy the login frame while suppressing noisy teardown errors."""
        self._destroying = True
        try:
            super().destroy()
        except Exception:
            pass
