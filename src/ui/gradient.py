from __future__ import annotations

import tkinter as tk
from typing import Iterable

import customtkinter as ctk


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    raw = str(value or "").strip().lstrip("#")
    if len(raw) != 6:
        return (15, 23, 42)
    return tuple(int(raw[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _mix(a: str, b: str, t: float) -> str:
    ra = _hex_to_rgb(a)
    rb = _hex_to_rgb(b)
    mixed = tuple(int(ra[i] + (rb[i] - ra[i]) * t) for i in range(3))
    return _rgb_to_hex(mixed)


class GradientPanel(ctk.CTkFrame):
    """A lightweight gradient-backed panel for prominent UI surfaces."""

    def __init__(
        self,
        parent,
        *,
        colors: Iterable[str] | None = None,
        corner_radius: int = 18,
        border_width: int = 1,
        border_color: str = "#172031",
        **kwargs,
    ):
        super().__init__(
            parent,
            fg_color="transparent",
            corner_radius=corner_radius,
            border_width=border_width,
            border_color=border_color,
            **kwargs,
        )
        self._colors = list(colors or ("#0f172a", "#1d4ed8", "#0891b2"))
        if len(self._colors) < 2:
            self._colors = ["#0f172a", "#1d4ed8"]

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._canvas = tk.Canvas(self, highlightthickness=0, bd=0, relief="flat", bg=self._colors[0])
        self._canvas.grid(row=0, column=0, sticky="nsew")

        self.content = ctk.CTkFrame(self._canvas, fg_color="transparent")
        self._window_id = self._canvas.create_window((0, 0), window=self.content, anchor="nw")

        self.bind("<Configure>", self._redraw)
        self._canvas.bind("<Configure>", self._on_canvas_configure)

    def _on_canvas_configure(self, event) -> None:
        try:
            self._canvas.itemconfigure(self._window_id, width=event.width, height=event.height)
        except Exception:
            pass

    def _redraw(self, _event=None) -> None:
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        self._canvas.delete("gradient")
        steps = max(height, 120)
        segments = len(self._colors) - 1
        if segments <= 0:
            self._canvas.create_rectangle(0, 0, width, height, fill=self._colors[0], outline="", tags="gradient")
            return
        for i in range(steps):
            pos = i / max(steps - 1, 1)
            scaled = pos * segments
            index = min(int(scaled), segments - 1)
            local_t = scaled - index
            color = _mix(self._colors[index], self._colors[index + 1], local_t)
            self._canvas.create_line(0, i, width, i, fill=color, tags="gradient")

        # Soft spotlight overlays for a more modern look.
        self._canvas.create_oval(
            width * 0.58,
            -height * 0.1,
            width * 1.12,
            height * 0.72,
            fill="#ffffff",
            stipple="gray50",
            outline="",
            tags="gradient",
        )
        self._canvas.create_oval(
            -width * 0.22,
            height * 0.35,
            width * 0.42,
            height * 1.05,
            fill="#38bdf8",
            stipple="gray50",
            outline="",
            tags="gradient",
        )
        self._canvas.tag_lower("gradient")

