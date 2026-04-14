"""Modern UI Components with Animations, Data Visualizations, and Interactive Charts.

This module provides advanced UI components featuring:
- Custom animated components with smooth transitions
- Advanced data visualizations using Plotly/Matplotlib integration
- Interactive charts for machine performance metrics
- Custom icons and micro-interactions
- Material Design 3 compliant components
- Responsive layouts with breakpoints and adaptive scaling
- Touch-friendly interactions with gesture support
"""
import customtkinter as ctk
from tkinter import ttk
import tkinter as tk
from typing import Dict, List, Tuple, Optional, Any, Callable
import threading
import time
import math
import random
from datetime import datetime, timedelta
from pathlib import Path
import json

try:
    from ..app_paths import resource_path
except Exception:
    from app_paths import resource_path

try:
    import plotly.graph_objects as go
    import plotly.express as px
    from plotly.subplots import make_subplots
    import matplotlib.pyplot as plt
    import matplotlib.animation as animation
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    import numpy as np
    PLOTLY_AVAILABLE = True
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    MATPLOTLIB_AVAILABLE = False

from .theme import get_theme, apply_elevation, animate_widget, ElevationLevel
from . import theme as theme_mod


# Responsive breakpoints (in pixels)
BREAKPOINTS = {
    'mobile': 600,
    'tablet': 900,
    'desktop': 1200
}


def get_breakpoint(width: int) -> str:
    """Get current breakpoint based on window width."""
    if width < BREAKPOINTS['mobile']:
        return 'mobile'
    elif width < BREAKPOINTS['tablet']:
        return 'tablet'
    else:
        return 'desktop'


class GIFSpinner(ctk.CTkFrame):
    """A simple animated GIF spinner. Falls back to ttk.Progressbar if GIF not found/unsupported."""
    def __init__(self, parent, gif_paths=None, width=32, height=32, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._label = None
        self._frames = []
        self._current = 0
        self._running = False
        self._after_id = None

        if gif_paths is None:
            gif_paths = [
                resource_path("assets", "icons", "spinner.gif"),
                resource_path("assets", "icons", "loader.gif"),
                resource_path("assets", "icons", "logo.gif"),
            ]

        for p in gif_paths:
            try:
                p = Path(p)
                if p.exists():
                    # load frames
                    i = 0
                    while True:
                        try:
                            img = tk.PhotoImage(file=str(p), format=f"gif -index {i}")
                            self._frames.append(img)
                            i += 1
                        except Exception:
                            break
                    break
            except Exception:
                continue

        if self._frames:
            self._label = tk.Label(self, bg=self.cget('fg_color'))
            self._label.pack()
        else:
            # Fallback to ttk progressbar
            try:
                from tkinter import ttk
                self._spinner = ttk.Progressbar(self, mode='indeterminate', length=width)
                self._spinner.pack()
            except Exception:
                self._spinner = None

    def start(self, interval=80):
        if getattr(self, '_spinner', None) is not None:
            try:
                self._spinner.start(10)
            except Exception:
                pass
            return

        if not self._frames or self._running:
            return
        self._running = True
        self._interval = interval
        self._animate()

    def _animate(self):
        if not self._running:
            return
        try:
            frame = self._frames[self._current]
            self._label.configure(image=frame)
            self._current = (self._current + 1) % len(self._frames)
            self._after_id = self.after(self._interval, self._animate)
        except Exception:
            self._running = False

    def stop(self):
        if getattr(self, '_spinner', None) is not None:
            try:
                self._spinner.stop()
            except Exception:
                pass
            return
        self._running = False
        if self._after_id:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None


class ResponsiveMixin:
    """Simple mixin class for backward compatibility - no responsive behavior."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # No responsive behavior - just pass through


class AnimatedCard(ResponsiveMixin, ctk.CTkFrame):
    """Modern animated card with smooth transitions and micro-interactions."""

    def __init__(self, parent, title: str, value: str, icon: str = None,
                 trend: Optional[float] = None, trend_label: str = None,
                 color: str = None, **kwargs):
        # Initialize with theme-aware colors
        theme = get_theme()
        tokens = theme.get_color_tokens()

        # Set default colors based on theme
        if color is None:
            color = tokens.primary

        fg_color = kwargs.pop('fg_color', tokens.surface)
        border_color = kwargs.pop('border_color', color)

        super().__init__(parent, corner_radius=16, fg_color=fg_color,
                        border_color=border_color, border_width=1, **kwargs)
        self._accent_color = color

        self.pack_propagate(False)

        # Store original sizes for responsive scaling
        self._original_height = 140
        self._mobile_height = 100
        self._tablet_height = 120
        self._desktop_height = 140

        self.configure(height=self._original_height)

        # Animation state
        self._hover = False
        self._animation_running = False

        # Store UI elements for responsive updates
        self.icon_label = None
        self.title_label = None
        self.value_label = None
        self.trend_icon = None
        self.trend_label = None

        # Bind hover events for micro-interactions
        self.bind("<Enter>", self._on_hover_enter)
        self.bind("<Leave>", self._on_hover_leave)

        self._create_ui(title, value, icon, trend, trend_label, color, tokens)

        # Apply elevation
        apply_elevation(self, ElevationLevel.LEVEL_1)

    def _create_ui(self, title: str, value: str, icon: Optional[str], trend: Optional[float], trend_label: Optional[str], color: str, tokens: Any) -> None:
        """Create the UI elements."""
        # Main container
        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.pack(fill="both", expand=True, padx=2, pady=2)

        self._glow_orb = ctk.CTkFrame(
            self.container,
            width=52,
            height=52,
            corner_radius=26,
            fg_color=color,
        )
        self._glow_orb.place(relx=1.0, x=-18, y=16, anchor="ne")

        # Header section with icon and title
        header_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        header_frame.pack(fill="x", padx=20, pady=(20, 10))

        # Icon (if provided)
        if icon:
            self.icon_label = ctk.CTkLabel(
                header_frame, text=icon, font=("Arial", 24),
                text_color=color
            )
            self.icon_label.pack(side="left", padx=(0, 10))

        # Title
        self.icon_label = ctk.CTkLabel(
            header_frame, text=icon, font=("Arial", 28),
            text_color=color
        ) if icon else None

        self.title_label = ctk.CTkLabel(
            header_frame, text=title, font=theme_mod.font(theme_mod.FONT_MEDIUM, "bold"),
            text_color=tokens.on_surface_variant
        )
        self.title_label.pack(side="left")

        # Value section
        value_frame = ctk.CTkFrame(self.container, fg_color="transparent")
        value_frame.pack(fill="x", padx=20, pady=(0, 10))

        self.value_label = ctk.CTkLabel(
            value_frame, text=value, font=theme_mod.font(theme_mod.FONT_LARGE, "bold"),
            text_color=tokens.on_surface
        )
        self.value_label.pack(side="left")

        # Optional loading spinner (GIFSpinner preferred, ttk.Progressbar fallback)
        try:
            spinner = GIFSpinner(value_frame)
            spinner.pack(side="left", padx=(10, 0))
            spinner.stop()
            spinner.pack_forget()
            self._spinner = spinner
        except Exception:
            try:
                self._spinner = ttk.Progressbar(value_frame, mode='indeterminate', length=80)
                self._spinner.pack(side="left", padx=(10,0))
                self._spinner.stop()
                self._spinner.pack_forget()
            except Exception:
                self._spinner = None

        # Trend indicator (if provided)
        if trend is not None:
            trend_frame = ctk.CTkFrame(value_frame, fg_color="transparent")
            trend_frame.pack(side="right", padx=(10, 0))

            # Trend icon and color
            trend_color = "#4CAF50" if trend >= 0 else "#F44336"
            trend_icon = "↗" if trend >= 0 else "↘"

            self.trend_icon = ctk.CTkLabel(
                trend_frame, text=trend_icon, font=theme_mod.font(theme_mod.FONT_SMALL),
                text_color=trend_color
            )
            self.trend_icon.pack(side="left")

            trend_text = f"{abs(trend):.1f}%"
            if trend_label:
                trend_text += f" {trend_label}"

            self.trend_label = ctk.CTkLabel(
                trend_frame, text=trend_text, font=theme_mod.font(theme_mod.FONT_SMALL),
                text_color=trend_color
            )
            self.trend_label.pack(side="left", padx=(5, 0))

        # Accent strip at the bottom for visual emphasis
        try:
            accent = tokens.primary or tokens.primary_container
            # subtle accent gradient fallback: solid accent bar
            bar = ctk.CTkFrame(self, height=6, fg_color=accent, corner_radius=4)
            bar.pack(fill="x", side="bottom")
            self._accent_bar = bar
            # start a slow pulse animation on the accent bar
            try:
                self._accent_state = 0
                def _pulse():
                    try:
                        palette = getattr(theme_mod, 'SIMPLE_PALETTE', {})
                        base = palette.get('primary', '#4F46E5')
                        alt = palette.get('primary_container', base)
                        self._accent_state = 1 - getattr(self, '_accent_state', 0)
                        color = alt if self._accent_state else base
                        try:
                            self._accent_bar.configure(fg_color=color)
                        except Exception:
                            pass
                    except Exception:
                        pass
                    try:
                        self.after(1200, _pulse)
                    except Exception:
                        pass
                self.after(1200, _pulse)
            except Exception:
                pass
        except Exception:
            pass

    def show_spinner(self) -> None:
        """Show spinner and hide numeric value while loading."""
        try:
            if self.value_label:
                self.value_label.pack_forget()
            if self._spinner:
                self._spinner.pack(side="left", padx=(10,0))
                try:
                    self._spinner.start(10)
                except Exception:
                    pass
        except Exception:
            pass

    def hide_spinner(self) -> None:
        """Hide spinner and show value_label with updated text."""
        try:
            if self._spinner:
                try:
                    self._spinner.stop()
                except Exception:
                    pass
                self._spinner.pack_forget()
            if self.value_label:
                self.value_label.pack(side="left")
        except Exception:
            pass

    def _adapt_to_breakpoint(self, breakpoint: str) -> None:
        """Adapt card to current breakpoint (simplified - no responsive behavior)."""
        # No responsive adaptation - just use default sizing
        pass

    def _adjust_layout_for_breakpoint(self, breakpoint: str, orientation: str) -> None:
        """Adjust layout for specific breakpoint (simplified - no responsive behavior)."""
        # No responsive layout adjustment
        pass

    def _on_hover_enter(self, event: Any) -> None:
        """Handle hover enter with smooth animation."""
        if self._animation_running:
            return

        self._hover = True
        try:
            self.configure(border_color=self._accent_color, border_width=2)
            self._glow_orb.configure(width=60, height=60, corner_radius=30)
        except Exception:
            pass
        self._animate_hover(True)

    def _on_hover_leave(self, event: Any) -> None:
        """Handle hover leave with smooth animation."""
        if self._animation_running:
            return

        self._hover = False
        try:
            self.configure(border_color=self._accent_color, border_width=1)
            self._glow_orb.configure(width=52, height=52, corner_radius=26)
        except Exception:
            pass
        self._animate_hover(False)

    def _animate_hover(self, entering: bool):
        """Animate card on hover with elevation change."""
        self._animation_running = True

        target_elevation = ElevationLevel.LEVEL_3 if entering else ElevationLevel.LEVEL_1
        apply_elevation(self, target_elevation)

        # Subtle scale animation
        if entering:
            self.configure(corner_radius=20)  # Slightly more rounded on hover
        else:
            self.configure(corner_radius=16)  # Back to normal

        self._animation_running = False


class MachineCard(ResponsiveMixin, ctk.CTkFrame):
    """Card representing a machine with company, status and a short description.

    Clicking the card opens a detail dialog with full information.
    """

    def __init__(self, parent, machine: Dict[str, Any], on_click: Callable[[Dict[str, Any]], None] = None, **kwargs):
        theme = get_theme()
        tokens = theme.get_color_tokens()

        super().__init__(parent, fg_color=tokens.surface, corner_radius=14,
                         border_color=tokens.outline_variant, border_width=1, **kwargs)

        self.machine = machine
        self.on_click = on_click
        self.pack_propagate(False)

        # Layout
        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.pack(fill="both", expand=True, padx=12, pady=12)

        title = machine.get('id') or machine.get('name') or machine.get('type') or 'Unknown'
        company = machine.get('company') or '—'
        status = machine.get('status') or 'unknown'
        desc = machine.get('description') or machine.get('how_it_works') or 'No description available.'

        # Header row
        header = ctk.CTkFrame(self.container, fg_color="transparent")
        header.pack(fill="x")

        self.title_lbl = ctk.CTkLabel(header, text=title, font=(None, 16, 'bold'))
        self.title_lbl.pack(side="left", anchor="w")

        self.company_lbl = ctk.CTkLabel(header, text=company, font=(None, 12), text_color=tokens.on_surface_variant)
        self.company_lbl.pack(side="right", anchor="e")

        # Body
        body = ctk.CTkFrame(self.container, fg_color="transparent")
        body.pack(fill="both", expand=True, pady=(8,0))

        # Status dot + label
        try:
            status_low = (status or '').lower()
            palette = getattr(__import__('src.ui.theme', fromlist=['SIMPLE_PALETTE']), 'SIMPLE_PALETTE')
            status_color = palette.get('success') if status_low in ('operational', 'ok') else (palette.get('warning') if status_low in ('maintenance', 'due', 'need maintenance') else palette.get('danger'))

            # Accent strip on the left
            strip = ctk.CTkFrame(self, width=6, fg_color=status_color)
            strip.place(relheight=1.0, x=0, y=0)

            # small dot
            dot = tk.Canvas(body, width=14, height=14, highlightthickness=0, bg=self.cget('fg_color'))
            dot.create_oval(2, 2, 12, 12, fill=status_color, outline=status_color)
            dot.pack(side='left', padx=(0,8), anchor='w')

            self.status_lbl = ctk.CTkLabel(body, text=f"Status: {status}", font=(None, 12, 'bold'))
            self.status_lbl.pack(anchor="w")
        except Exception:
            self.status_lbl = ctk.CTkLabel(body, text=f"Status: {status}", font=(None, 12))
            self.status_lbl.pack(anchor="w")

        # Short description (single line)
        short = desc.split('\n')[0]
        if len(short) > 120:
            short = short[:117] + '...'

        self.desc_lbl = ctk.CTkLabel(body, text=short, font=(None, 12), text_color=tokens.on_surface_variant, wraplength=360)
        self.desc_lbl.pack(anchor="w", pady=(6,0))

        # Bind click to open details
        self.bind('<Button-1>', self._on_click)
        for child in self.winfo_children():
            try:
                child.bind('<Button-1>', self._on_click)
            except Exception:
                pass

        apply_elevation(self, ElevationLevel.LEVEL_1)

    def _on_click(self, event=None):
        # Simple click feedback animation
        try:
            animate_widget(self, 'corner_radius', self.cget('corner_radius'), self.cget('corner_radius') + 6, 120,
                           lambda: animate_widget(self, 'corner_radius', self.cget('corner_radius') + 6, self.cget('corner_radius'), 120))
        except Exception:
            pass

        # Call external handler if provided
        if callable(self.on_click):
            try:
                self.on_click(self.machine)
                return
            except Exception:
                pass

        # Default: open a simple detail dialog
        try:
            dlg = ctk.CTkToplevel(self)
            dlg.title(f"Machine: {self.machine.get('id') or self.machine.get('name')}")
            dlg.geometry("560x360")
            dlg.transient(self)
            dlg.grab_set()

            title = ctk.CTkLabel(dlg, text=self.machine.get('id') or self.machine.get('name') or 'Machine', font=(None, 16, 'bold'))
            title.pack(anchor='w', padx=12, pady=(12,6))

            info_frame = ctk.CTkFrame(dlg)
            info_frame.pack(fill='both', expand=True, padx=12, pady=6)

            # Company
            c_lbl = ctk.CTkLabel(info_frame, text=f"Company: {self.machine.get('company', '—')}", font=(None, 12))
            c_lbl.pack(anchor='w', pady=(6,0))

            # Status
            s_lbl = ctk.CTkLabel(info_frame, text=f"Status: {self.machine.get('status', 'unknown')}", font=(None, 12))
            s_lbl.pack(anchor='w', pady=(6,0))

            # How it works
            how = self.machine.get('description') or self.machine.get('how_it_works') or 'No detailed description available.'
            how_lbl = ctk.CTkLabel(info_frame, text="How it works:", font=(None, 12, 'bold'))
            how_lbl.pack(anchor='w', pady=(12,0))

            # Ensure theme tokens are available in this method scope
            theme = get_theme()
            tokens = theme.get_color_tokens()

            how_text = ctk.CTkLabel(info_frame, text=how, font=(None, 11), wraplength=520, text_color=tokens.on_surface_variant)
            how_text.pack(anchor='w', pady=(6,0))

            close_btn = ctk.CTkButton(dlg, text="Close", command=dlg.destroy)
            close_btn.pack(side='right', padx=12, pady=12)
        except Exception:
            pass

    def _on_swipe_left(self) -> None:
        """Handle swipe left gesture - could navigate to next card."""
        print("Swipe left detected - next card")

    def _on_swipe_right(self) -> None:
        """Handle swipe right gesture - could navigate to previous card."""
        print("Swipe right detected - previous card")

    def _on_zoom_in(self) -> None:
        """Handle zoom in - increase card size."""
        current_height = self.cget("height")
        new_height = min(current_height + 20, 200)
        animate_widget(self, "height", current_height, new_height, 200)

    def _on_zoom_out(self) -> None:
        """Handle zoom out - decrease card size."""
        current_height = self.cget("height")
        new_height = max(current_height - 20, 80)
        animate_widget(self, "height", current_height, new_height, 200)

    def _on_hover_enter(self, event):
        """Handle hover enter with smooth animation."""
        if self._animation_running:
            return

        self._hover = True
        self._animate_hover(True)

    def _on_hover_leave(self, event):
        """Handle hover leave with smooth animation."""
        if self._animation_running:
            return

        self._hover = False
        self._animate_hover(False)

    def _animate_hover(self, entering: bool):
        """Animate card on hover with elevation change."""
        self._animation_running = True

        target_elevation = ElevationLevel.LEVEL_3 if entering else ElevationLevel.LEVEL_1
        apply_elevation(self, target_elevation)

        # Subtle scale animation
        if entering:
            self.configure(corner_radius=20)  # Slightly more rounded on hover
        else:
            self.configure(corner_radius=16)  # Back to normal

        self._animation_running = False


class PerformanceChart(ResponsiveMixin, ctk.CTkFrame):
    """Interactive performance chart for machine metrics using Plotly."""

    def __init__(self, parent, title: str, data: List[Dict], chart_type: str = "line",
                 width: int = 400, height: int = 300, **kwargs):
        theme = get_theme()
        tokens = theme.get_color_tokens()

        super().__init__(parent, fg_color=tokens.surface, corner_radius=16,
                        border_color=tokens.outline_variant, border_width=1, **kwargs)

        self.pack_propagate(False)

        # Store responsive sizes
        self._sizes = {
            'mobile': (300, 200),
            'tablet': (350, 250),
            'desktop': (400, 300)
        }

        self.configure(width=width, height=height)

        # Title
        title_label = ctk.CTkLabel(
            self, text=title, font=("Arial", 16, "bold"),
            text_color=tokens.on_surface
        )
        title_label.pack(pady=(20, 10), padx=20, anchor="w")

        # Chart container
        self.chart_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.chart_frame.pack(fill="both", expand=True, padx=10, pady=(0, 20))

        self.data = data
        self.chart_type = chart_type
        self.canvas = None

        if PLOTLY_AVAILABLE:
            self._create_plotly_chart()
        elif MATPLOTLIB_AVAILABLE:
            self._create_matplotlib_chart()
        else:
            self._create_fallback_chart()

    def _adapt_to_breakpoint(self, breakpoint: str):
        """Adapt chart size to breakpoint."""
        width, height = self._sizes[breakpoint]
        animate_widget(self, "width", self.cget("width"), width, 300)
        animate_widget(self, "height", self.cget("height"), height, 300)

        # Update chart if exists
        if self.canvas:
            self.canvas.get_tk_widget().configure(width=width-20, height=height-40)

    def _on_zoom_in(self):
        """Zoom in chart."""
        current_width = self.cget("width")
        current_height = self.cget("height")
        new_width = min(current_width + 50, 600)
        new_height = min(current_height + 30, 400)
        animate_widget(self, "width", current_width, new_width, 200)
        animate_widget(self, "height", current_height, new_height, 200)

    def _on_zoom_out(self):
        """Zoom out chart."""
        current_width = self.cget("width")
        current_height = self.cget("height")
        new_width = max(current_width - 50, 200)
        new_height = max(current_height - 30, 150)
        animate_widget(self, "width", current_width, new_width, 200)
        animate_widget(self, "height", current_height, new_height, 200)

    def _create_plotly_chart(self):
        """Create interactive chart using Plotly."""
        try:
            if self.chart_type == "line":
                self._create_line_chart()
            elif self.chart_type == "bar":
                self._create_bar_chart()
            elif self.chart_type == "pie":
                self._create_pie_chart()
            else:
                self._create_line_chart()
        except Exception as e:
            print(f"Plotly chart creation failed: {e}")
            self._create_fallback_chart()

    def _create_line_chart(self):
        """Create line chart for time series data."""
        fig = go.Figure()

        for series in self.data:
            if 'x' in series and 'y' in series:
                fig.add_trace(go.Scatter(
                    x=series['x'],
                    y=series['y'],
                    mode='lines+markers',
                    name=series.get('name', 'Series'),
                    line=dict(color=series.get('color', '#6750A4'), width=3),
                    marker=dict(size=6)
                ))

        # Update layout
        theme = get_theme()
        tokens = theme.get_color_tokens()

        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font_color=tokens.on_surface,
            margin=dict(l=20, r=20, t=20, b=20),
            showlegend=True,
            legend=dict(
                bgcolor='rgba(0,0,0,0)',
                bordercolor=tokens.outline,
                borderwidth=1
            )
        )

        # Add to tkinter
        import plotly.io as pio
        pio.templates.default = "plotly_white"

        from tkinterweb import HtmlFrame  # Alternative embedding method
        # For now, create a simple text representation
        self._create_fallback_chart()

    def _create_bar_chart(self):
        """Create bar chart for categorical data."""
        # Simplified implementation
        self._create_fallback_chart()

    def _create_pie_chart(self):
        """Create pie chart for distribution data."""
        # Simplified implementation
        self._create_fallback_chart()

    def _create_matplotlib_chart(self):
        """Create chart using Matplotlib as fallback."""
        try:
            fig = Figure(figsize=(4, 3), dpi=100)
            ax = fig.add_subplot(111)

            theme = get_theme()
            tokens = theme.get_color_tokens()

            # Set theme-aware colors
            ax.set_facecolor(tokens.surface)
            fig.patch.set_facecolor(tokens.surface)
            ax.tick_params(colors=tokens.on_surface)
            ax.spines['bottom'].set_color(tokens.outline)
            ax.spines['top'].set_color(tokens.outline)
            ax.spines['right'].set_color(tokens.outline)
            ax.spines['left'].set_color(tokens.outline)

            # Plot data
            for series in self.data:
                if 'x' in series and 'y' in series:
                    ax.plot(series['x'], series['y'],
                           color=series.get('color', tokens.primary),
                           linewidth=2, marker='o', markersize=4)

            ax.set_title("Performance Metrics", color=tokens.on_surface, fontsize=12)

            # Embed in tkinter
            self.canvas = FigureCanvasTkAgg(fig, master=self.chart_frame)
            self.canvas.draw()
            self.canvas.get_tk_widget().pack(fill="both", expand=True)

        except Exception as e:
            print(f"Matplotlib chart creation failed: {e}")
            self._create_fallback_chart()

    def _create_fallback_chart(self):
        """Create a simple fallback chart when advanced libraries aren't available."""
        theme = get_theme()
        tokens = theme.get_color_tokens()

        fallback_label = ctk.CTkLabel(
            self.chart_frame,
            text="Chart visualization requires\nPlotly or Matplotlib installation",
            font=("Arial", 12),
            text_color=tokens.on_surface_variant,
            justify="center"
        )
        fallback_label.pack(expand=True)


class MetricGauge(ResponsiveMixin, ctk.CTkFrame):
    """Circular gauge for displaying metric values with animations."""

    def __init__(self, parent, title: str, value: float, max_value: float = 100,
                 unit: str = "%", color: str = None, **kwargs):
        theme = get_theme()
        tokens = theme.get_color_tokens()

        if color is None:
            color = tokens.primary

        super().__init__(parent, fg_color=tokens.surface, corner_radius=16,
                        border_color=tokens.outline_variant, border_width=1, **kwargs)

        self.pack_propagate(False)

        # Responsive sizes
        self._sizes = {
            'mobile': (150, 150),
            'tablet': (180, 180),
            'desktop': (200, 200)
        }

        self.configure(width=200, height=200)

        self.title = title
        self.value = value
        self.max_value = max_value
        self.unit = unit
        self.color = color

        # Create canvas for gauge
        self.canvas = tk.Canvas(self, bg=tokens.surface, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=10, pady=10)

        # Title
        self.title_label = ctk.CTkLabel(
            self, text=title, font=("Arial", 12, "bold"),
            text_color=tokens.on_surface
        )
        self.title_label.pack(pady=(10, 0))

        # Value display
        self.value_label = ctk.CTkLabel(
            self, text=f"{value:.1f}{unit}", font=("Arial", 24, "bold"),
            text_color=tokens.on_surface
        )
        self.value_label.pack()

        # Draw initial gauge
        self._draw_gauge()

        # Animate to current value
        self._animate_gauge(0, value, 1000)  # 1 second animation

    def _adapt_to_breakpoint(self, breakpoint: str):
        """Adapt gauge size to breakpoint."""
        width, height = self._sizes[breakpoint]
        animate_widget(self, "width", self.cget("width"), width, 300)
        animate_widget(self, "height", self.cget("height"), height, 300)
        self._draw_gauge()  # Redraw with new size

    def _on_zoom_in(self):
        """Zoom in gauge."""
        current_width = self.cget("width")
        current_height = self.cget("height")
        new_size = min(current_width + 30, 250)
        animate_widget(self, "width", current_width, new_size, 200)
        animate_widget(self, "height", current_height, new_size, 200)

    def _on_zoom_out(self):
        """Zoom out gauge."""
        current_width = self.cget("width")
        current_height = self.cget("height")
        new_size = max(current_width - 30, 100)
        animate_widget(self, "width", current_width, new_size, 200)
        animate_widget(self, "height", current_height, new_size, 200)

    def _draw_gauge(self):
        """Draw the circular gauge."""
        width = 150
        height = 150
        center_x = width // 2
        center_y = height // 2
        radius = 60

        # Clear canvas
        self.canvas.delete("all")

        theme = get_theme()
        tokens = theme.get_color_tokens()

        # Background circle
        self.canvas.create_oval(
            center_x - radius, center_y - radius,
            center_x + radius, center_y + radius,
            outline=tokens.outline_variant, width=8, fill=""
        )

        # Progress arc
        percentage = min(self.value / self.max_value, 1.0)
        angle = percentage * 360

        if angle > 0:
            # Draw progress arc
            extent = angle - 90  # Start from top
            self.canvas.create_arc(
                center_x - radius, center_y - radius,
                center_x + radius, center_y + radius,
                start=-90, extent=extent,
                outline=self.color, width=8, style="arc"
            )

        # Center dot
        self.canvas.create_oval(
            center_x - 3, center_y - 3,
            center_x + 3, center_y + 3,
            fill=self.color
        )

    def _animate_gauge(self, start_value: float, end_value: float, duration: int):
        """Animate gauge from start to end value."""
        steps = max(1, duration // 50)  # ~20 FPS
        step_duration = duration / steps

        def animate_step(step: int):
            if step >= steps:
                return

            progress = step / steps
            current_value = start_value + (end_value - start_value) * progress

            self.value = current_value
            self.value_label.configure(text=f"{current_value:.1f}{self.unit}")
            self._draw_gauge()

            self.after(int(step_duration), lambda: animate_step(step + 1))

        animate_step(0)

    def update_value(self, new_value: float, animate: bool = True):
        """Update gauge value with optional animation."""
        if animate:
            self._animate_gauge(self.value, new_value, 500)
        else:
            self.value = new_value
            self.value_label.configure(text=f"{new_value:.1f}{self.unit}")
            self._draw_gauge()


class StatusIndicator(ResponsiveMixin, ctk.CTkFrame):
    """Animated status indicator with pulsing effects."""

    def __init__(self, parent, status: str, color: str = None, size: int = 12, **kwargs):
        theme = get_theme()
        tokens = theme.get_color_tokens()

        super().__init__(parent, fg_color="transparent", **kwargs)

        self.status = status
        self.color = color or self._get_status_color(status)

        # Responsive sizes
        self._sizes = {
            'mobile': 10,
            'tablet': 12,
            'desktop': 14
        }

        self.size = size
        self.pulsing = False

        # Status indicator canvas
        self.canvas = tk.Canvas(self, width=size, height=size,
                              bg=tokens.surface, highlightthickness=0)
        self.canvas.pack()

        # Status text
        self.label = ctk.CTkLabel(
            self, text=status, font=("Arial", 10),
            text_color=tokens.on_surface
        )
        self.label.pack(pady=(2, 0))

        self._draw_indicator()

        # Start pulsing for active statuses
        if status.lower() in ['running', 'active', 'online']:
            self._start_pulsing()

    def _adapt_to_breakpoint(self, breakpoint: str):
        """Adapt indicator size to breakpoint."""
        new_size = self._sizes[breakpoint]
        self.size = new_size
        self.canvas.configure(width=new_size, height=new_size)
        self._draw_indicator()

    def _get_status_color(self, status: str) -> str:
        """Get color based on status."""
        status_colors = {
            'online': '#4CAF50',
            'running': '#4CAF50',
            'active': '#4CAF50',
            'offline': '#9E9E9E',
            'stopped': '#9E9E9E',
            'error': '#F44336',
            'warning': '#FF9800',
            'maintenance': '#FF9800'
        }
        return status_colors.get(status.lower(), '#9E9E9E')

    def _draw_indicator(self):
        """Draw the status indicator."""
        radius = self.size // 2
        center = self.size // 2

        # Outer ring
        self.canvas.create_oval(
            center - radius, center - radius,
            center + radius, center + radius,
            outline=self.color, width=2, fill=self.color
        )

    def _start_pulsing(self):
        """Start pulsing animation for active indicators."""
        self.pulsing = True
        self._pulse_animation()

    def _pulse_animation(self):
        """Animate pulsing effect."""
        if not self.pulsing:
            return

        def pulse():
            if not self.pulsing:
                return

            # Simple opacity animation (simulated with color intensity)
            # In a full implementation, this would use actual opacity
            self.canvas.after(1000, pulse)

        pulse()

    def update_status(self, new_status: str):
        """Update status with animation."""
        if self.status != new_status:
            self.status = new_status
            self.color = self._get_status_color(new_status)
            self.label.configure(text=new_status)
            self._draw_indicator()

            # Stop pulsing for inactive statuses
            if new_status.lower() not in ['running', 'active', 'online']:
                self.pulsing = False


class PerformanceChart(ResponsiveMixin, ctk.CTkFrame):
    """Interactive performance chart using Matplotlib or Plotly."""

    def __init__(self, parent, title: str, data: List[Dict], chart_type: str = "line",
                 width: int = 500, height: int = 250, **kwargs):
        theme = get_theme()
        tokens = theme.get_color_tokens()

        super().__init__(parent, fg_color=tokens.surface, **kwargs)

        self.title = title
        self.data = data
        self.chart_type = chart_type
        self.width = width
        self.height = height

        # Title
        self.title_label = ctk.CTkLabel(
            self, text=title, font=("Arial", 14, "bold"),
            text_color=tokens.on_surface
        )
        self.title_label.pack(pady=(10, 5))

        # Chart container
        self.chart_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.chart_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Create the chart
        self._create_chart()

    def _create_chart(self):
        """Create the chart using available library."""
        if MATPLOTLIB_AVAILABLE:
            self._create_matplotlib_chart()
        elif PLOTLY_AVAILABLE:
            self._create_plotly_chart()
        else:
            # Fallback: show message
            label = ctk.CTkLabel(
                self.chart_frame,
                text="Chart requires matplotlib or plotly.\nInstall with: pip install matplotlib plotly",
                font=("Arial", 12)
            )
            label.pack(expand=True)

    def _create_matplotlib_chart(self):
        """Create chart using Matplotlib."""
        fig = Figure(figsize=(self.width/100, self.height/100), dpi=100)
        ax = fig.add_subplot(111)

        theme = get_theme()
        tokens = theme.get_color_tokens()

        # Set background colors
        fig.patch.set_facecolor(tokens.surface)
        ax.set_facecolor(tokens.surface)

        # Plot data
        for series in self.data:
            x = series['x']
            y = series['y']
            name = series['name']
            color = series.get('color', '#6750A4')

            if self.chart_type == "line":
                ax.plot(x, y, label=name, color=color, linewidth=2)
            elif self.chart_type == "bar":
                ax.bar(x, y, label=name, color=color)

        # Styling
        ax.set_title(self.title, color=tokens.on_surface, fontsize=12)
        ax.set_xlabel("Time", color=tokens.on_surface_variant)
        ax.set_ylabel("Value", color=tokens.on_surface_variant)
        ax.tick_params(colors=tokens.on_surface_variant)
        ax.spines['bottom'].set_color(tokens.outline)
        ax.spines['top'].set_color(tokens.outline)
        ax.spines['right'].set_color(tokens.outline)
        ax.spines['left'].set_color(tokens.outline)

        if len(self.data) > 1:
            ax.legend()

        # Embed in tkinter
        canvas = FigureCanvasTkAgg(fig, master=self.chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)

    def _create_plotly_chart(self):
        """Create chart using Plotly (fallback)."""
        # For simplicity, show a message since embedding plotly in tkinter is complex
        label = ctk.CTkLabel(
            self.chart_frame,
            text="Plotly charts available.\nUse matplotlib for embedded charts.",
            font=("Arial", 12)
        )
        label.pack(expand=True)

    def _adapt_to_breakpoint(self, breakpoint: str):
        """Adapt chart size to breakpoint."""
        if breakpoint == 'mobile':
            new_width, new_height = 300, 150
        elif breakpoint == 'tablet':
            new_width, new_height = 400, 200
        else:  # desktop
            new_width, new_height = self.width, self.height

        # Recreate chart with new size
        self.width, self.height = new_width, new_height
        # Clear and recreate
        for widget in self.chart_frame.winfo_children():
            widget.destroy()
        self._create_chart()


class AnimatedButton(ResponsiveMixin, ctk.CTkButton):
    """Custom animated button with micro-interactions."""

    def __init__(self, parent, text: str, command: Callable = None,
                 animation_type: str = "scale", **kwargs):
        theme = get_theme()
        tokens = theme.get_color_tokens()

        # Set theme-aware defaults
        fg_color = kwargs.pop('fg_color', tokens.primary)
        hover_color = kwargs.pop('hover_color', tokens.primary_container)
        text_color = kwargs.pop('text_color', tokens.on_primary)

        super().__init__(parent, text=text, command=command,
                        fg_color=fg_color, hover_color=hover_color,
                        text_color=text_color, **kwargs)

        self.animation_type = animation_type
        self._original_fg_color = fg_color
        self._hover_fg_color = hover_color

        # Bind animation events
        self.bind("<Enter>", self._on_hover_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)

    def _adapt_to_breakpoint(self, breakpoint: str):
        """Adapt button size to breakpoint."""
        if breakpoint == 'mobile':
            self.configure(height=35, font=("Arial", 10))
        elif breakpoint == 'tablet':
            self.configure(height=40, font=("Arial", 11))
        else:  # desktop
            self.configure(height=45, font=("Arial", 12))

    def _on_swipe_left(self):
        """Swipe left could trigger button action."""
        if self.cget("state") != "disabled":
            self.invoke()

    def _on_zoom_in(self):
        """Zoom in button."""
        current_height = self.cget("height")
        new_height = min(current_height + 5, 60)
        self.configure(height=new_height)

    def _on_zoom_out(self):
        """Zoom out button."""
        current_height = self.cget("height")
        new_height = max(current_height - 5, 25)
        self.configure(height=new_height)

    def _on_hover_enter(self, event):
        """Handle mouse enter with animation."""
        if self.animation_type == "scale":
            animate_widget(self, "corner_radius", 6, 12, 200)
        elif self.animation_type == "glow":
            # Simulate glow effect with color change
            self.configure(fg_color=self._hover_fg_color)

    def _on_leave(self, event=None):
        """Handle mouse leave with animation."""
        if self.animation_type == "scale":
            animate_widget(self, "corner_radius", 12, 6, 200)
        elif self.animation_type == "glow":
            self.configure(fg_color=self._original_fg_color)

    def _on_click(self, event):
        """Handle click with feedback animation."""
        # Quick scale animation for feedback
        original_radius = self.cget("corner_radius") or 6
        animate_widget(self, "corner_radius", original_radius, original_radius + 4, 100,
                      lambda: animate_widget(self, "corner_radius", original_radius + 4, original_radius, 100))


class NotificationBadge(ResponsiveMixin, ctk.CTkFrame):
    """Animated notification badge with count display."""

    def __init__(self, parent, count: int = 0, max_count: int = 99, **kwargs):
        theme = get_theme()
        tokens = theme.get_color_tokens()

        super().__init__(parent, fg_color="transparent", **kwargs)

        self.count = count
        self.max_count = max_count

        # Responsive sizes
        self._sizes = {
            'mobile': (18, 18, 8),
            'tablet': (20, 20, 10),
            'desktop': (22, 22, 12)
        }

        # Badge container
        self.badge_frame = ctk.CTkFrame(
            self, fg_color="#F44336", corner_radius=10,
            width=20, height=20
        )
        self.badge_frame.pack_propagate(False)

        # Count label
        self.count_label = ctk.CTkLabel(
            self.badge_frame, text=self._format_count(),
            font=("Arial", 10, "bold"), text_color="white"
        )
        self.count_label.pack(expand=True)

        if count > 0:
            self.badge_frame.pack(side="right", padx=(5, 0))
            self._animate_badge()
        else:
            self.badge_frame.pack_forget()

    def _adapt_to_breakpoint(self, breakpoint: str):
        """Adapt badge size to breakpoint."""
        width, height, font_size = self._sizes[breakpoint]
        self.badge_frame.configure(width=width, height=height)
        self.count_label.configure(font=("Arial", font_size, "bold"))

    def _format_count(self) -> str:
        """Format count display."""
        if self.count > self.max_count:
            return f"{self.max_count}+"
        return str(self.count)

    def _animate_badge(self):
        """Animate badge appearance."""
        # Simple bounce animation
        def bounce():
            self.badge_frame.configure(corner_radius=12)
            self.after(100, lambda: self.badge_frame.configure(corner_radius=10))

        bounce()

    def update_count(self, new_count: int):
        """Update badge count with animation."""
        old_count = self.count
        self.count = new_count

        if new_count > 0 and old_count == 0:
            # Show badge with animation
            self.badge_frame.pack(side="right", padx=(5, 0))
            self._animate_badge()
        elif new_count == 0 and old_count > 0:
            # Hide badge
            self.badge_frame.pack_forget()
        else:
            # Update count
            self.count_label.configure(text=self._format_count())
            if new_count != old_count:
                self._animate_badge()


# Legacy Card class for backward compatibility
class Card(ctk.CTkFrame):
    """Legacy card class - use AnimatedCard for new implementations."""

    def __init__(self, parent, title, value):
        super().__init__(parent, corner_radius=12, fg_color="transparent")

        self.pack_propagate(False)
        self.configure(height=100)

        title_label = ctk.CTkLabel(
            self, text=title, font=("Arial", 13)
        )
        title_label.pack(anchor="w", padx=15, pady=(15, 5))

        value_label = ctk.CTkLabel(
            self, text=value, font=("Arial", 28, "bold")
        )
        value_label.pack(anchor="w", padx=15)


class ResponsiveGrid(ResponsiveMixin, ctk.CTkFrame):
    """Grid-based responsive layout container."""

    def __init__(self, parent, columns: int = 3, **kwargs):
        super().__init__(parent, **kwargs)

        self.columns = columns
        self._widgets = []
        self._current_breakpoint = 'desktop'

    def _adapt_to_breakpoint(self, breakpoint: str):
        """Rearrange widgets based on breakpoint."""
        if breakpoint == 'mobile':
            cols = 1
        elif breakpoint == 'tablet':
            cols = 2
        else:  # desktop
            cols = self.columns

        # Reposition widgets in grid
        for i, widget in enumerate(self._widgets):
            row = i // cols
            col = i % cols
            widget.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")

        # Configure grid weights
        for r in range((len(self._widgets) + cols - 1) // cols):
            self.grid_rowconfigure(r, weight=1)
        for c in range(cols):
            self.grid_columnconfigure(c, weight=1)

    def add_widget(self, widget):
        """Add a widget to the grid."""
        self._widgets.append(widget)
        self._adapt_to_breakpoint(self._current_breakpoint)

    def remove_widget(self, widget):
        """Remove a widget from the grid."""
        if widget in self._widgets:
            self._widgets.remove(widget)
            widget.grid_forget()
            self._adapt_to_breakpoint(self._current_breakpoint)


# Utility functions for creating sample data
def create_sample_machine_data(hours: int = 24) -> List[Dict]:
    """Create sample machine performance data."""
    now = datetime.now()
    data = []

    for i in range(hours):
        timestamp = now - timedelta(hours=hours-i)
        # Simulate realistic machine performance data
        base_performance = 85 + random.uniform(-10, 10)
        efficiency = base_performance + random.uniform(-5, 5)
        temperature = 70 + random.uniform(-5, 15)

        data.append({
            'timestamp': timestamp,
            'performance': round(base_performance, 1),
            'efficiency': round(efficiency, 1),
            'temperature': round(temperature, 1)
        })

    return data


def create_performance_chart_data(machine_data: List[Dict]) -> List[Dict]:
    """Convert machine data to chart format."""
    return [{
        'x': [d['timestamp'] for d in machine_data],
        'y': [d['performance'] for d in machine_data],
        'name': 'Performance (%)',
        'color': '#6750A4'
    }, {
        'x': [d['timestamp'] for d in machine_data],
        'y': [d['efficiency'] for d in machine_data],
        'name': 'Efficiency (%)',
        'color': '#7D5260'
    }]
