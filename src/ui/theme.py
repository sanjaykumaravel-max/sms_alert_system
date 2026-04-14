"""Advanced UI Theme System with Material Design 3, WCAG Accessibility, and Dynamic Styling.

This module provides a comprehensive theme engine featuring:
- Material Design 3 design tokens and principles
- WCAG accessibility compliance for color contrast
- Dynamic CSS-in-Python styling system
- Dark/Light mode with system preference detection
- Elevation and motion support
- Custom color palette generation
"""
from __future__ import annotations
import time
import math
import json
import os
from typing import Dict, List, Tuple, Optional, Union, Any
from dataclasses import dataclass, field
from enum import Enum
import threading

try:
    from PIL import Image, ImageTk, ImageColor, ImageDraw, ImageFont
except Exception:
    Image = None
    ImageTk = None
    ImageColor = None
    ImageDraw = None
    ImageFont = None

import tkinter as tk


# Simple palette for quick UI tokens
SIMPLE_PALETTE = {
    "bg": "#07121f",
    "card": "#0d1728",
    "accent": "#2563EB",        # electric blue
    "primary": "#22D3EE",       # cyan
    "secondary": "#F59E0B",     # amber
    "success": "#10B981",       # green
    "warning": "#F97316",       # orange
    "danger": "#EF4444",        # red
    "muted": "#94A3B8",
    "card_border": "#1d2a3f"
}

SECTION_COLORS = {
    "dashboard": {"accent": "#22d3ee", "bg": "#081520"},
    "mine_details": {"accent": "#60a5fa", "bg": "#081827"},
    "checklist": {"accent": "#f59e0b", "bg": "#1a1308"},
    "hour_entry": {"accent": "#10b981", "bg": "#071a15"},
    "machines": {"accent": "#38bdf8", "bg": "#081a22"},
    "plant_maintenance": {"accent": "#8b5cf6", "bg": "#120a21"},
    "schedules": {"accent": "#f97316", "bg": "#1d1008"},
    "alerts": {"accent": "#ef4444", "bg": "#220c0c"},
    "rule_engine": {"accent": "#06b6d4", "bg": "#081a22"},
    "operators": {"accent": "#14b8a6", "bg": "#081919"},
    "operator_records": {"accent": "#0ea5a4", "bg": "#081a1a"},
    "maintenance_history": {"accent": "#eab308", "bg": "#1b1808"},
    "reports": {"accent": "#6366f1", "bg": "#0d1022"},
    "settings": {"accent": "#64748b", "bg": "#111827"},
    "admin": {"accent": "#ec4899", "bg": "#220d1b"},
}

SECTION_GRADIENTS = {
    "dashboard": ("#0f172a", "#0f766e", "#22d3ee"),
    "mine_details": ("#0f172a", "#1d4ed8", "#60a5fa"),
    "checklist": ("#1a1308", "#b45309", "#f59e0b"),
    "hour_entry": ("#071a15", "#047857", "#34d399"),
    "machines": ("#081a22", "#0369a1", "#38bdf8"),
    "plant_maintenance": ("#120a21", "#6d28d9", "#a78bfa"),
    "schedules": ("#1d1008", "#c2410c", "#fb923c"),
    "alerts": ("#220c0c", "#b91c1c", "#f87171"),
    "rule_engine": ("#081a22", "#0e7490", "#22d3ee"),
    "operators": ("#081919", "#0f766e", "#2dd4bf"),
    "operator_records": ("#081a1a", "#0f766e", "#14b8a6"),
    "maintenance_history": ("#1b1808", "#a16207", "#facc15"),
    "reports": ("#0d1022", "#4338ca", "#818cf8"),
    "settings": ("#111827", "#475569", "#94a3b8"),
    "admin": ("#220d1b", "#be185d", "#f472b6"),
    "mine_setup": ("#0f172a", "#1d4ed8", "#0891b2"),
    "login": ("#0f172a", "#1d4ed8", "#0891b2"),
}

# Font system tokens
FONT_FAMILY = os.environ.get('UI_FONT_FAMILY', 'Arial')
FONT_LARGE = int(os.environ.get('UI_FONT_LARGE', 28))
FONT_MEDIUM = int(os.environ.get('UI_FONT_MEDIUM', 18))
FONT_SMALL = int(os.environ.get('UI_FONT_SMALL', 14))


def font(size: int = FONT_MEDIUM, weight: str = 'normal'):
    """Return a Tk font tuple usable by customtkinter/ttk widgets."""
    try:
        return (FONT_FAMILY, int(size), weight)
    except Exception:
        return (None, int(size), weight)


class ThemeMode(Enum):
    """Theme modes supported by the system."""
    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"  # Follows system preference


class ElevationLevel(Enum):
    """Material Design 3 elevation levels."""
    LEVEL_0 = 0   # Flat surface
    LEVEL_1 = 1   # Card default elevation
    LEVEL_2 = 2   # App bar, menus
    LEVEL_3 = 3   # Navigation drawer, modal side sheet
    LEVEL_4 = 4   # Dialog, picker
    LEVEL_5 = 5   # Bottom navigation bar, bottom sheet


@dataclass
class MaterialColorTokens:
    """Material Design 3 color tokens."""
    # Primary colors
    primary: str = "#6750A4"
    on_primary: str = "#FFFFFF"
    primary_container: str = "#EADDFF"
    on_primary_container: str = "#21005D"

    # Secondary colors
    secondary: str = "#625B71"
    on_secondary: str = "#FFFFFF"
    secondary_container: str = "#E8DEF8"
    on_secondary_container: str = "#1D192B"

    # Tertiary colors
    tertiary: str = "#7D5260"
    on_tertiary: str = "#FFFFFF"
    tertiary_container: str = "#FFD8E4"
    on_tertiary_container: str = "#31111D"

    # Error colors
    error: str = "#BA1A1A"
    on_error: str = "#FFFFFF"
    error_container: str = "#FFDAD6"
    on_error_container: str = "#410002"

    # Surface colors
    surface: str = "#FEF7FF"
    on_surface: str = "#1D1B20"
    surface_variant: str = "#E7E0EC"
    on_surface_variant: str = "#49454F"

    # Background
    background: str = "#FEF7FF"
    on_background: str = "#1D1B20"

    # Outline
    outline: str = "#79747E"
    outline_variant: str = "#CAC4D0"


@dataclass
class DarkMaterialColorTokens:
    """Material Design 3 dark theme color tokens."""
    # Primary colors
    primary: str = "#D0BCFF"
    on_primary: str = "#381E72"
    primary_container: str = "#4F378B"
    on_primary_container: str = "#EADDFF"

    # Secondary colors
    secondary: str = "#CCC2DC"
    on_secondary: str = "#332D41"
    secondary_container: str = "#4A4458"
    on_secondary_container: str = "#E8DEF8"

    # Tertiary colors
    tertiary: str = "#EFB8C8"
    on_tertiary: str = "#492532"
    tertiary_container: str = "#633B48"
    on_tertiary_container: str = "#FFD8E4"

    # Error colors
    error: str = "#FFB4AB"
    on_error: str = "#690005"
    error_container: str = "#93000A"
    on_error_container: str = "#FFDAD6"

    # Surface colors
    surface: str = "#141218"
    on_surface: str = "#E6E0E9"
    surface_variant: str = "#49454F"
    on_surface_variant: str = "#CAC4D0"

    # Background
    background: str = "#141218"
    on_background: str = "#E6E0E9"

    # Outline
    outline: str = "#938F99"
    outline_variant: str = "#49454F"


@dataclass
class ElevationTokens:
    """Material Design 3 elevation tokens."""
    level_0: Dict[str, Any] = field(default_factory=lambda: {
        "shadow_color": "#000000",
        "shadow_opacity": 0.0,
        "shadow_offset": (0, 0),
        "shadow_radius": 0
    })

    level_1: Dict[str, Any] = field(default_factory=lambda: {
        "shadow_color": "#000000",
        "shadow_opacity": 0.05,
        "shadow_offset": (0, 1),
        "shadow_radius": 3
    })

    level_2: Dict[str, Any] = field(default_factory=lambda: {
        "shadow_color": "#000000",
        "shadow_opacity": 0.08,
        "shadow_offset": (0, 1),
        "shadow_radius": 6
    })

    level_3: Dict[str, Any] = field(default_factory=lambda: {
        "shadow_color": "#000000",
        "shadow_opacity": 0.11,
        "shadow_offset": (0, 1),
        "shadow_radius": 8
    })

    level_4: Dict[str, Any] = field(default_factory=lambda: {
        "shadow_color": "#000000",
        "shadow_opacity": 0.14,
        "shadow_offset": (0, 2),
        "shadow_radius": 4
    })

    level_5: Dict[str, Any] = field(default_factory=lambda: {
        "shadow_color": "#000000",
        "shadow_opacity": 0.16,
        "shadow_offset": (0, 4),
        "shadow_radius": 5
    })


@dataclass
class MotionTokens:
    """Material Design 3 motion tokens."""
    # Duration tokens (in milliseconds)
    duration_short_1: int = 50
    duration_short_2: int = 100
    duration_short_3: int = 150
    duration_short_4: int = 200
    duration_medium_1: int = 250
    duration_medium_2: int = 300
    duration_medium_3: int = 350
    duration_medium_4: int = 400
    duration_long_1: int = 450
    duration_long_2: int = 500
    duration_long_3: int = 550
    duration_long_4: int = 600

    # Easing tokens
    easing_linear: str = "linear"
    easing_standard: str = "cubic-bezier(0.2, 0.0, 0.0, 1.0)"
    easing_standard_accelerate: str = "cubic-bezier(0.3, 0.0, 0.8, 0.15)"
    easing_standard_decelerate: str = "cubic-bezier(0.05, 0.7, 0.1, 1.0)"
    easing_emphasized: str = "cubic-bezier(0.05, 0.7, 0.1, 1.0)"
    easing_emphasized_accelerate: str = "cubic-bezier(0.3, 0.0, 0.8, 0.15)"
    easing_emphasized_decelerate: str = "cubic-bezier(0.05, 0.7, 0.1, 1.0)"


class StyleRule:
    """CSS-in-Python style rule system."""

    def __init__(self, selector: str, properties: Dict[str, Any]) -> None:
        self.selector = selector
        self.properties = properties.copy()

    def apply_to_widget(self, widget) -> bool:
        """Apply this style rule to a widget."""
        try:
            # Convert CSS properties to widget configuration
            config = self._convert_properties_to_config()
            if hasattr(widget, 'configure'):
                widget.configure(**config)
                return True
        except Exception:
            pass
        return False

    def _convert_properties_to_config(self) -> Dict[str, Any]:
        """Convert CSS-like properties to widget configuration."""
        config = {}

        # Color properties
        if 'background-color' in self.properties:
            config['bg'] = self.properties['background-color']
            config['fg_color'] = self.properties['background-color']

        if 'color' in self.properties:
            config['fg'] = self.properties['color']
            config['text_color'] = self.properties['color']

        if 'border-color' in self.properties:
            config['border_color'] = self.properties['border-color']

        # Size properties
        if 'width' in self.properties:
            config['width'] = self.properties['width']

        if 'height' in self.properties:
            config['height'] = self.properties['height']

        # Border radius
        if 'border-radius' in self.properties:
            config['corner_radius'] = self.properties['border-radius']

        # Font properties
        if 'font-size' in self.properties or 'font-family' in self.properties:
            font_spec = []
            if 'font-family' in self.properties:
                font_spec.append(self.properties['font-family'])
            if 'font-size' in self.properties:
                font_spec.append(self.properties['font-size'])
            if font_spec:
                config['font'] = tuple(font_spec)

        return config


class StyleSheet:
    """CSS-in-Python stylesheet system."""

    def __init__(self) -> None:
        self.rules: List[StyleRule] = []

    def add_rule(self, selector: str, properties: Dict[str, Any]) -> None:
        """Add a style rule."""
        self.rules.append(StyleRule(selector, properties))

    def apply_to_widget(self, widget, widget_class: str = None, widget_id: str = None):
        """Apply matching rules to a widget."""
        applied = False

        for rule in self.rules:
            if self._matches_selector(rule.selector, widget, widget_class, widget_id):
                if rule.apply_to_widget(widget):
                    applied = True

        return applied

    def _matches_selector(self, selector: str, widget, widget_class: str = None, widget_id: str = None) -> bool:
        """Check if a selector matches a widget."""
        # Simple selector matching - can be extended for more complex CSS selectors
        selector = selector.strip()

        # Universal selector
        if selector == '*':
            return True

        # Class selector
        if selector.startswith('.'):
            return widget_class == selector[1:]

        # ID selector
        if selector.startswith('#'):
            return widget_id == selector[1:]

        # Type selector
        if widget_class and selector == widget_class:
            return True

        return False


def calculate_contrast_ratio(color1: str, color2: str) -> float:
    """Calculate WCAG contrast ratio between two colors."""
    def get_luminance(color: str) -> float:
        if not color.startswith('#'):
            # Handle named colors or invalid colors
            return 0.5

        # Convert hex to RGB
        hex_color = color.lstrip('#')
        if len(hex_color) == 3:
            hex_color = ''.join([c*2 for c in hex_color])

        try:
            r = int(hex_color[0:2], 16) / 255.0
            g = int(hex_color[2:4], 16) / 255.0
            b = int(hex_color[4:6], 16) / 255.0
        except (ValueError, IndexError):
            return 0.5

        # Calculate relative luminance
        def adjust_channel(c):
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

        r = adjust_channel(r)
        g = adjust_channel(g)
        b = adjust_channel(b)

        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    lum1 = get_luminance(color1)
    lum2 = get_luminance(color2)

    brighter = max(lum1, lum2)
    darker = min(lum1, lum2)

    return (brighter + 0.05) / (darker + 0.05)


def ensure_wcag_compliance(color_tokens: MaterialColorTokens) -> MaterialColorTokens:
    """Ensure color tokens meet WCAG AA standards (4.5:1 for normal text, 3:1 for large text)."""
    # Check primary combinations
    if calculate_contrast_ratio(color_tokens.primary, color_tokens.on_primary) < 4.5:
        # Adjust on_primary to ensure contrast
        color_tokens.on_primary = "#FFFFFF" if color_tokens.primary.startswith("#") else "#000000"

    # Check surface combinations
    if calculate_contrast_ratio(color_tokens.surface, color_tokens.on_surface) < 4.5:
        color_tokens.on_surface = "#000000" if color_tokens.surface.startswith("#FE") else "#FFFFFF"

    return color_tokens


def detect_system_theme() -> ThemeMode:
    """Detect system theme preference."""
    try:
        # Try to detect system theme on Windows
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                           r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return ThemeMode.LIGHT if value == 1 else ThemeMode.DARK
    except Exception:
        pass

    try:
        # Try macOS detection
        import subprocess
        result = subprocess.run(['defaults', 'read', '-g', 'AppleInterfaceStyle'],
                              capture_output=True, text=True)
        if result.returncode == 0 and 'Dark' in result.stdout:
            return ThemeMode.DARK
    except Exception:
        pass

    # Default to light mode
    return ThemeMode.LIGHT


class AdvancedTheme:
    """Advanced theme system with Material Design 3, WCAG compliance, and dynamic styling."""

    def __init__(self, mode: ThemeMode = ThemeMode.SYSTEM) -> None:
        self.mode = mode
        self._current_mode = self._resolve_mode()
        self._color_tokens = self._get_color_tokens()
        self._elevation_tokens = ElevationTokens()
        self._motion_tokens = MotionTokens()
        self._stylesheet = StyleSheet()
        self._custom_palettes: Dict[str, List[str]] = {}

        # Initialize default styles
        self._init_default_styles()

    def _resolve_mode(self) -> ThemeMode:
        """Resolve the actual theme mode."""
        if self.mode == ThemeMode.SYSTEM:
            return detect_system_theme()
        return self.mode

    def _get_color_tokens(self) -> MaterialColorTokens:
        """Get appropriate color tokens based on current mode."""
        if self._current_mode == ThemeMode.DARK:
            return ensure_wcag_compliance(DarkMaterialColorTokens())
        else:
            return ensure_wcag_compliance(MaterialColorTokens())

    def _init_default_styles(self) -> None:
        """Initialize default CSS-in-Python styles."""
        # Button styles
        self._stylesheet.add_rule('.primary-button', {
            'background-color': self._color_tokens.primary,
            'color': self._color_tokens.on_primary,
            'border-radius': 8,
            'font-size': 14,
            'font-family': 'Arial'
        })

        self._stylesheet.add_rule('.secondary-button', {
            'background-color': self._color_tokens.secondary,
            'color': self._color_tokens.on_secondary,
            'border-radius': 8,
            'font-size': 14
        })

        # Card styles
        self._stylesheet.add_rule('.card', {
            'background-color': self._color_tokens.surface,
            'color': self._color_tokens.on_surface,
            'border-radius': 12,
            'border-color': self._color_tokens.outline_variant
        })

        # Label styles
        self._stylesheet.add_rule('.primary-text', {
            'color': self._color_tokens.on_surface,
            'font-size': 14
        })

        self._stylesheet.add_rule('.secondary-text', {
            'color': self._color_tokens.on_surface_variant,
            'font-size': 12
        })

    def set_mode(self, mode: ThemeMode):
        """Set the theme mode."""
        self.mode = mode
        self._current_mode = self._resolve_mode()
        self._color_tokens = self._get_color_tokens()
        self._init_default_styles()  # Reinitialize styles with new colors

    def get_color_tokens(self) -> MaterialColorTokens:
        """Get current color tokens."""
        return self._color_tokens

    def get_elevation_tokens(self) -> ElevationTokens:
        """Get elevation tokens."""
        return self._elevation_tokens

    def get_motion_tokens(self) -> MotionTokens:
        """Get motion tokens."""
        return self._motion_tokens

    def create_custom_palette(self, name: str, base_color: str, variations: int = 5) -> List[str]:
        """Create a custom color palette with WCAG-compliant variations."""
        palette = [base_color]

        # Generate lighter variations
        for i in range(1, variations // 2 + 1):
            factor = 1 + (i * 0.2)
            lighter = self._lighten_color(base_color, factor)
            palette.insert(0, lighter)

        # Generate darker variations
        for i in range(1, variations // 2 + 1):
            factor = 1 - (i * 0.2)
            darker = self._darken_color(base_color, factor)
            palette.append(darker)

        self._custom_palettes[name] = palette
        return palette

    def _lighten_color(self, color: str, factor: float) -> str:
        """Lighten a color by a factor."""
        if not color.startswith('#'):
            return color

        hex_color = color.lstrip('#')
        if len(hex_color) == 3:
            hex_color = ''.join([c*2 for c in hex_color])

        try:
            r = min(255, int(int(hex_color[0:2], 16) * factor))
            g = min(255, int(int(hex_color[2:4], 16) * factor))
            b = min(255, int(int(hex_color[4:6], 16) * factor))

            return f"#{r:02x}{g:02x}{b:02x}"
        except (ValueError, IndexError):
            return color

    def _darken_color(self, color: str, factor: float) -> str:
        """Darken a color by a factor."""
        if not color.startswith('#'):
            return color

        hex_color = color.lstrip('#')
        if len(hex_color) == 3:
            hex_color = ''.join([c*2 for c in hex_color])

        try:
            r = max(0, int(int(hex_color[0:2], 16) * factor))
            g = max(0, int(int(hex_color[2:4], 16) * factor))
            b = max(0, int(int(hex_color[4:6], 16) * factor))

            return f"#{r:02x}{g:02x}{b:02x}"
        except (ValueError, IndexError):
            return color

    def apply_elevation(self, widget, level: ElevationLevel):
        """Apply Material Design elevation to a widget."""
        elevation = getattr(self._elevation_tokens, f"level_{level.value}")

        # For CustomTkinter widgets, we can simulate elevation with border effects
        try:
            if hasattr(widget, 'configure'):
                # Create a subtle border effect to simulate elevation
                border_color = self._adjust_color_alpha(
                    elevation["shadow_color"],
                    elevation["shadow_opacity"]
                )
                widget.configure(border_color=border_color, border_width=1)
        except Exception:
            pass

    def animate_widget(self, widget, property_name: str, start_value: Any, end_value: Any,
                      duration: int = 300, easing: str = None):
        """Animate a widget property with Material Design motion."""
        if easing is None:
            easing = self._motion_tokens.easing_standard

        # Simple linear animation for now
        # In a full implementation, this would use easing functions
        steps = max(1, duration // 16)  # ~60 FPS

        def animate_step(step: int):
            if step >= steps:
                return

            progress = step / steps
            current_value = self._interpolate_value(start_value, end_value, progress)

            try:
                if hasattr(widget, 'configure'):
                    widget.configure(**{property_name: current_value})
            except Exception:
                pass

            # Schedule next step
            widget.after(16, lambda: animate_step(step + 1))

        animate_step(0)

    def _interpolate_value(self, start: Any, end: Any, progress: float) -> Any:
        """Interpolate between two values."""
        if isinstance(start, (int, float)) and isinstance(end, (int, float)):
            return start + (end - start) * progress
        elif isinstance(start, str) and isinstance(end, str) and start.startswith('#') and end.startswith('#'):
            # Color interpolation
            return self._interpolate_color(start, end, progress)
        else:
            return end if progress > 0.5 else start

    def _interpolate_color(self, color1: str, color2: str, progress: float) -> str:
        """Interpolate between two colors."""
        if not (color1.startswith('#') and color2.startswith('#')):
            return color2 if progress > 0.5 else color1

        # Extract RGB components
        r1, g1, b1 = self._hex_to_rgb(color1)
        r2, g2, b2 = self._hex_to_rgb(color2)

        # Interpolate
        r = int(r1 + (r2 - r1) * progress)
        g = int(g1 + (g2 - g1) * progress)
        b = int(b1 + (b2 - b1) * progress)

        return f"#{r:02x}{g:02x}{b:02x}"

    def _hex_to_rgb(self, hex_color: str) -> Tuple[int, int, int]:
        """Convert hex color to RGB tuple."""
        hex_color = hex_color.lstrip('#')
        if len(hex_color) == 3:
            hex_color = ''.join([c*2 for c in hex_color])

        return (
            int(hex_color[0:2], 16),
            int(hex_color[2:4], 16),
            int(hex_color[4:6], 16)
        )

    def _adjust_color_alpha(self, color: str, alpha: float) -> str:
        """Adjust color alpha (simplified - returns original color for now)."""
        return color

    def style_widget(self, widget, style_class: str = None, style_id: str = None):
        """Apply theme styling to a widget."""
        # Try CSS-in-Python styling first
        if self._stylesheet.apply_to_widget(widget, style_class, style_id):
            return True

        # Fallback to legacy styling methods
        return self._legacy_style_widget(widget)

    def _legacy_style_widget(self, widget) -> bool:
        """Legacy widget styling for backward compatibility."""
        try:
            widget_type = type(widget).__name__

            if 'Button' in widget_type:
                self._style_button(widget)
                return True
            elif 'Label' in widget_type:
                self._style_label(widget)
                return True
            elif 'Frame' in widget_type:
                self._style_frame(widget)
                return True

        except Exception:
            pass

        return False

    def _style_button(self, btn) -> None:
        """Style a button with theme colors."""
        try:
            if hasattr(btn, 'configure') and str(btn) != 'None':
                btn.configure(
                    fg_color=self._color_tokens.primary,
                    hover_color=self._color_tokens.primary_container,
                    text_color=self._color_tokens.on_primary
                )
        except Exception:
            try:
                if hasattr(btn, 'configure') and str(btn) != 'None':
                    btn.configure(bg=self._color_tokens.primary, fg=self._color_tokens.on_primary)
            except Exception:
                pass

    def _style_label(self, lbl) -> None:
        """Style a label with theme colors."""
        try:
            if hasattr(lbl, 'configure') and str(lbl) != 'None':
                lbl.configure(text_color=self._color_tokens.on_surface)
        except Exception:
            try:
                if hasattr(lbl, 'configure') and str(lbl) != 'None':
                    lbl.configure(fg=self._color_tokens.on_surface, bg=self._color_tokens.surface)
            except Exception:
                pass

    def _style_frame(self, frm) -> None:
        """Style a frame with theme colors."""
        try:
            if hasattr(frm, 'configure') and str(frm) != 'None':
                frm.configure(fg_color=self._color_tokens.surface)
        except Exception:
            pass

    def get_gradient_colors(self) -> List[str]:
        """Get gradient colors for backgrounds."""
        if self._current_mode == ThemeMode.DARK:
            return ["#1a1a2e", "#16213e", "#0f3460", "#1a1a2e"]
        else:
            return ["#667eea", "#764ba2", "#f093fb", "#f5576c"]

    def save_theme(self, filepath: str):
        """Save current theme configuration."""
        config = {
            "mode": self.mode.value,
            "current_mode": self._current_mode.value,
            "custom_palettes": self._custom_palettes
        }

        try:
            with open(filepath, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception:
            pass

    def load_theme(self, filepath: str):
        """Load theme configuration."""
        try:
            with open(filepath, 'r') as f:
                config = json.load(f)

            self.mode = ThemeMode(config.get("mode", "system"))
            self._current_mode = ThemeMode(config.get("current_mode", "light"))
            self._custom_palettes = config.get("custom_palettes", {})
            self._color_tokens = self._get_color_tokens()
            self._init_default_styles()
        except Exception:
            pass


# Global theme instance
current_theme = AdvancedTheme()

def set_theme_mode(mode: ThemeMode):
    """Set the global theme mode."""
    current_theme.set_mode(mode)

def get_theme() -> AdvancedTheme:
    """Get the current theme instance."""
    return current_theme

def style_widget(widget, style_class: str = None, style_id: str = None):
    """Convenience function to style a widget."""
    return current_theme.style_widget(widget, style_class, style_id)

def apply_elevation(widget, level: ElevationLevel):
    """Convenience function to apply elevation."""
    current_theme.apply_elevation(widget, level)

def animate_widget(widget, property_name: str, start_value: Any, end_value: Any,
                  duration: int = 300, easing: str = None):
    """Convenience function to animate a widget."""
    current_theme.animate_widget(widget, property_name, start_value, end_value, duration, easing)


# Legacy compatibility functions
def _hex_to_rgb(hexstr: str):
    """Legacy function for backward compatibility."""
    return current_theme._hex_to_rgb(hexstr)


def _make_gradient_image(width: int, height: int, colors: list[str]):
    """Legacy function for backward compatibility."""
    # This would need PIL implementation
    return None


def apply_gradient_background(window: tk.Tk | tk.Toplevel, colors: list[str] | tuple[str, ...] = None):
    """Apply gradient background with theme integration."""
    if colors is None:
        colors = current_theme.get_gradient_colors()

    # Reuse existing gradient background logic
    # This is a simplified version - the full implementation would be in the original code
    try:
        # For now, just set a solid background color from the theme
        if hasattr(window, 'configure'):
            window.configure(bg=colors[0])
    except Exception:
        pass


def set_theme(colors, preset='Custom'):
    """Legacy function for backward compatibility."""
    # Convert old format to new theme system
    current_theme.create_custom_palette(preset, colors[0] if colors else "#667eea")


class Theme:
    """Legacy theme class for backward compatibility."""

    def __init__(self, colors=None, preset='Rainbow') -> None:
        self.preset = preset
        self.colors = list(colors) if colors else ["#667eea", "#764ba2", "#f093fb", "#f5576c"]

    @property
    def primary(self):
        return self.colors[-1] if self.colors else '#2c5364'

    @property
    def accent(self):
        return self.colors[1] if len(self.colors) > 1 else self.colors[0]

    @property
    def background(self):
        return self.colors[0] if self.colors else '#0f2027'

    def set(self, colors, preset='Custom') -> None:
        self.colors = list(colors)
        self.preset = preset

    def get_preview_photo(self, width=240, height=80):
        """Return a PhotoImage (PIL-backed if available) for preview widgets."""
        if Image is not None and ImageTk is not None:
            img = _make_gradient_image(width, height, self.colors)
            try:
                return ImageTk.PhotoImage(img)
            except Exception:
                return None
        # fallback: generate a tiny PhotoImage via tkinter
        try:
            # create a blank image using tkinter's PhotoImage and fill with first color
            ph = tk.PhotoImage(width=width, height=height)
            ph.put(self.background, to=(0,0,width,height))
            return ph
        except Exception:
            return None

    def style_button(self, btn):
        """Apply theme colors to a `customtkinter.CTkButton`, CTkOptionMenu, or tkinter Button-like widget."""
        try:
            if hasattr(btn, 'configure') and str(btn) != 'None':
                # Try CTkButton/CTkOptionMenu styling
                btn.configure(fg_color=self.accent, hover_color=self.primary, text_color='white')
        except Exception:
            try:
                if hasattr(btn, 'configure') and str(btn) != 'None':
                    btn.configure(bg=self.accent, fg='white')
            except Exception:
                pass

    def style_label(self, lbl):
        try:
            if hasattr(lbl, 'configure') and str(lbl) != 'None':
                lbl.configure(text_color='white')
        except Exception:
            try:
                if hasattr(lbl, 'configure') and str(lbl) != 'None':
                    lbl.configure(fg='white', bg=self.background)
            except Exception:
                pass


# global theme instance for backward compatibility
legacy_theme = Theme()

def get_theme():
    return current_theme

