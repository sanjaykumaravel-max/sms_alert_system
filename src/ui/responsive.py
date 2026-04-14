"""Responsive Layout System with Adaptive Components and Touch Support.

This module provides:
- Grid-based responsive layouts with breakpoints
- Adaptive UI components that scale with window size
- Mobile-optimized views for tablet/phone access
- Touch-friendly interactions with gesture support
- Breakpoint detection and dynamic layout switching
"""

import customtkinter as ctk
import tkinter as tk
from typing import Dict, List, Tuple, Optional, Any, Callable, Union
from dataclasses import dataclass
from enum import Enum
import threading
import time
import math


class Breakpoint(Enum):
    """Responsive breakpoints for different screen sizes."""
    MOBILE = "mobile"      # < 768px
    TABLET = "tablet"      # 768px - 1024px
    DESKTOP = "desktop"    # 1024px - 1440px
    LARGE = "large"        # > 1440px


class Orientation(Enum):
    """Device orientation."""
    PORTRAIT = "portrait"
    LANDSCAPE = "landscape"


@dataclass
class ResponsiveConfig:
    """Configuration for responsive behavior."""
    breakpoint: Breakpoint
    orientation: Orientation
    width: int
    height: int
    scale_factor: float
    touch_enabled: bool = False


class ResponsiveGrid(ctk.CTkFrame):
    """Responsive grid layout system with breakpoints."""

    def __init__(self, parent, breakpoints: Dict[Breakpoint, Dict[str, Any]] = None, **kwargs):
        super().__init__(parent, **kwargs)

        self.breakpoints = breakpoints or self._get_default_breakpoints()
        self.current_config: Optional[ResponsiveConfig] = None
        self.components: Dict[str, Dict[str, Any]] = {}
        self.touch_bindings: List[Tuple[tk.Widget, str, Callable]] = []

        # Bind to configure event for responsive updates
        self.bind('<Configure>', self._on_resize)
        parent.bind('<Configure>', self._on_resize)

        # Initialize responsive system
        self._update_responsive_config()

    def _get_default_breakpoints(self) -> Dict[Breakpoint, Dict[str, Any]]:
        """Get default breakpoint configurations."""
        return {
            Breakpoint.MOBILE: {
                'max_width': 767,
                'columns': 1,
                'gutter': 10,
                'padding': 15,
                'font_scale': 0.8,
                'touch_target_size': 44
            },
            Breakpoint.TABLET: {
                'max_width': 1023,
                'columns': 2,
                'gutter': 15,
                'padding': 20,
                'font_scale': 0.9,
                'touch_target_size': 44
            },
            Breakpoint.DESKTOP: {
                'max_width': 1439,
                'columns': 3,
                'gutter': 20,
                'padding': 25,
                'font_scale': 1.0,
                'touch_target_size': 32
            },
            Breakpoint.LARGE: {
                'max_width': float('inf'),
                'columns': 4,
                'gutter': 25,
                'padding': 30,
                'font_scale': 1.1,
                'touch_target_size': 32
            }
        }

    def _on_resize(self, event=None):
        """Handle window resize events."""
        if event and hasattr(event, 'widget') and event.widget != self:
            return

        # Debounce resize events
        if hasattr(self, '_resize_timer'):
            self.after_cancel(self._resize_timer)

        self._resize_timer = self.after(100, self._update_responsive_config)

    def _update_responsive_config(self):
        """Update responsive configuration based on current size."""
        try:
            # Get current dimensions
            width = self.winfo_width()
            height = self.winfo_height()

            if width <= 0 or height <= 0:
                return

            # Determine orientation
            orientation = Orientation.LANDSCAPE if width > height else Orientation.PORTRAIT

            # Determine breakpoint
            breakpoint = Breakpoint.MOBILE
            for bp, config in self.breakpoints.items():
                if width <= config['max_width']:
                    breakpoint = bp
                    break

            # Calculate scale factor
            base_width = 1200  # Reference width
            scale_factor = min(width / base_width, 1.0)

            # Check for touch support (simplified detection)
            touch_enabled = self._detect_touch_support()

            # Create new config
            new_config = ResponsiveConfig(
                breakpoint=breakpoint,
                orientation=orientation,
                width=width,
                height=height,
                scale_factor=scale_factor,
                touch_enabled=touch_enabled
            )

            # Update if config changed
            if self.current_config != new_config:
                self.current_config = new_config
                self._apply_responsive_layout()

        except Exception as e:
            print(f"Responsive config update error: {e}")

    def _detect_touch_support(self) -> bool:
        """Detect if touch input is supported."""
        try:
            # Check for touch capabilities (simplified)
            root = self.winfo_toplevel()
            return hasattr(root, 'tk') and 'touch' in str(root.tk.call('tk', 'windowingsystem')).lower()
        except:
            return False

    def _apply_responsive_layout(self):
        """Apply responsive layout changes."""
        if not self.current_config:
            return

        config = self.current_config
        bp_config = self.breakpoints[config.breakpoint]

        # Update grid configuration
        self._configure_grid(bp_config)

        # Update all registered components
        for component_id, component_data in self.components.items():
            self._update_component_responsive(component_id, component_data)

        # Update touch interactions
        self._update_touch_interactions()

    def _configure_grid(self, bp_config: Dict[str, Any]):
        """Configure grid layout for current breakpoint."""
        columns = bp_config['columns']
        gutter = bp_config['gutter']

        # Configure column weights
        for i in range(columns):
            self.grid_columnconfigure(i, weight=1, uniform='responsive_col')

        # Configure gutters
        for child in self.winfo_children():
            if hasattr(child, 'grid_info'):
                info = child.grid_info()
                if 'column' in info:
                    child.grid_configure(padx=(gutter//2, gutter//2), pady=(gutter//2, gutter//2))

    def register_component(self, component_id: str, component: tk.Widget,
                          responsive_config: Dict[Breakpoint, Dict[str, Any]]):
        """Register a component for responsive updates."""
        self.components[component_id] = {
            'widget': component,
            'config': responsive_config,
            'original_config': self._get_widget_config(component)
        }

    def _get_widget_config(self, widget: tk.Widget) -> Dict[str, Any]:
        """Get current widget configuration."""
        config = {}
        try:
            if hasattr(widget, 'grid_info'):
                config.update(widget.grid_info())
            if hasattr(widget, 'place_info'):
                config.update(widget.place_info())
            if hasattr(widget, 'pack_info'):
                config.update(widget.pack_info())
        except:
            pass
        return config

    def _update_component_responsive(self, component_id: str, component_data: Dict[str, Any]):
        """Update a component's responsive configuration."""
        widget = component_data['widget']
        config = component_data['config']

        if self.current_config.breakpoint in config:
            bp_config = config[self.current_config.breakpoint]
            self._apply_component_config(widget, bp_config)

    def _apply_component_config(self, widget: tk.Widget, config: Dict[str, Any]):
        """Apply configuration to a component."""
        try:
            # Grid configuration
            if 'grid' in config:
                grid_config = config['grid'].copy()
                # Scale dimensions if needed
                if 'width' in grid_config and isinstance(grid_config['width'], (int, float)):
                    grid_config['width'] = int(grid_config['width'] * self.current_config.scale_factor)
                if 'height' in grid_config and isinstance(grid_config['height'], (int, float)):
                    grid_config['height'] = int(grid_config['height'] * self.current_config.scale_factor)
                widget.grid(**grid_config)

            # Font scaling
            if 'font_scale' in config and hasattr(widget, 'cget') and 'font' in widget.configure():
                current_font = widget.cget('font')
                if current_font:
                    scaled_font = self._scale_font(current_font, config['font_scale'])
                    widget.configure(font=scaled_font)

        except Exception as e:
            print(f"Component config error: {e}")

    def _scale_font(self, font_spec: Any, scale: float) -> Tuple[str, int, str]:
        """Scale font size."""
        if isinstance(font_spec, (tuple, list)) and len(font_spec) >= 2:
            family, size, *styles = font_spec
            if isinstance(size, int):
                new_size = max(8, int(size * scale))
                return (family, new_size, *styles)
        return font_spec

    def _update_touch_interactions(self):
        """Update touch-friendly interactions."""
        if not self.current_config or not self.current_config.touch_enabled:
            return

        bp_config = self.breakpoints[self.current_config.breakpoint]
        touch_size = bp_config['touch_target_size']

        # Update touch targets for interactive elements
        for child in self.winfo_children():
            self._make_touch_friendly(child, touch_size)

    def _make_touch_friendly(self, widget: tk.Widget, min_size: int):
        """Make widget touch-friendly by ensuring minimum size."""
        try:
            # Ensure minimum touch target size
            current_width = widget.winfo_reqwidth()
            current_height = widget.winfo_reqheight()

            if current_width > 0 and current_width < min_size:
                widget.configure(width=min_size)
            if current_height > 0 and current_height < min_size:
                widget.configure(height=min_size)

            # Add touch gesture support
            self._add_touch_gestures(widget)

        except Exception as e:
            print(f"Touch friendly error: {e}")

    def _add_touch_gestures(self, widget: tk.Widget):
        """Add touch gesture support to widget."""
        # Remove existing touch bindings
        for w, event, callback in self.touch_bindings:
            if w == widget:
                try:
                    w.unbind(event, callback)
                except:
                    pass

        # Clear old bindings for this widget
        self.touch_bindings = [b for b in self.touch_bindings if b[0] != widget]

        # Add touch gestures
        gestures = {
            '<Button-1>': self._on_touch_tap,
            '<Double-Button-1>': self._on_touch_double_tap,
            '<B1-Motion>': self._on_touch_drag,
            '<ButtonRelease-1>': self._on_touch_release
        }

        for event, callback in gestures.items():
            try:
                bound_callback = widget.bind(event, callback, add='+')
                self.touch_bindings.append((widget, event, bound_callback))
            except:
                pass

    def _on_touch_tap(self, event):
        """Handle touch tap."""
        # Could implement haptic feedback here
        pass

    def _on_touch_double_tap(self, event):
        """Handle double tap."""
        pass

    def _on_touch_drag(self, event):
        """Handle touch drag."""
        pass

    def _on_touch_release(self, event):
        """Handle touch release."""
        pass


class AdaptiveCard(ctk.CTkFrame):
    """Adaptive card that responds to screen size changes."""

    def __init__(self, parent, title: str, content: Any = None, **kwargs):
        super().__init__(parent, **kwargs)

        self.title = title
        self.content = content
        self.responsive_grid = None

        # Initialize responsive behavior
        self._setup_responsive_layout()

    def _setup_responsive_layout(self):
        """Setup responsive layout for the card."""
        # Create responsive grid for card content
        self.responsive_grid = ResponsiveGrid(self, fg_color="transparent")

        # Title section
        self.title_frame = ctk.CTkFrame(self.responsive_grid, fg_color="transparent")
        self.title_label = ctk.CTkLabel(
            self.title_frame, text=self.title,
            font=("Arial", 16, "bold")
        )
        self.title_label.pack(pady=10, padx=15)

        # Content section
        self.content_frame = ctk.CTkFrame(self.responsive_grid, fg_color="transparent")

        if self.content:
            if isinstance(self.content, tk.Widget):
                self.content.pack(in_=self.content_frame, fill="both", expand=True, padx=10, pady=10)
            else:
                content_label = ctk.CTkLabel(self.content_frame, text=str(self.content))
                content_label.pack(pady=10, padx=15)

        # Register components for responsive updates
        responsive_config = {
            Breakpoint.MOBILE: {
                'grid': {'column': 0, 'row': 0, 'columnspan': 1, 'sticky': 'ew'},
                'font_scale': 0.8
            },
            Breakpoint.TABLET: {
                'grid': {'column': 0, 'row': 0, 'columnspan': 2, 'sticky': 'ew'},
                'font_scale': 0.9
            },
            Breakpoint.DESKTOP: {
                'grid': {'column': 0, 'row': 0, 'columnspan': 3, 'sticky': 'ew'},
                'font_scale': 1.0
            },
            Breakpoint.LARGE: {
                'grid': {'column': 0, 'row': 0, 'columnspan': 4, 'sticky': 'ew'},
                'font_scale': 1.1
            }
        }

        self.responsive_grid.register_component('title_frame', self.title_frame, responsive_config)
        self.responsive_grid.register_component('content_frame', self.content_frame, responsive_config)

        # Pack the responsive grid
        self.responsive_grid.pack(fill="both", expand=True)


class TouchButton(ctk.CTkButton):
    """Touch-friendly button with gesture support."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        self.touch_start = None
        self.long_press_timer = None
        self.gesture_handlers = {}

        # Bind touch events
        self.bind('<Button-1>', self._on_touch_start)
        self.bind('<ButtonRelease-1>', self._on_touch_end)
        self.bind('<B1-Motion>', self._on_touch_move)
        self.bind('<Leave>', self._on_touch_leave)

    def _on_touch_start(self, event):
        """Handle touch start."""
        self.touch_start = (event.x, event.y, event.time)

        # Start long press timer
        self.long_press_timer = self.after(500, self._on_long_press)

        # Visual feedback
        self._scale_button(0.95)

    def _on_touch_end(self, event):
        """Handle touch end."""
        if self.long_press_timer:
            self.after_cancel(self.long_press_timer)
            self.long_press_timer = None

        # Reset visual feedback
        self._scale_button(1.0)

        # Check for tap vs drag
        if self.touch_start:
            dx = abs(event.x - self.touch_start[0])
            dy = abs(event.y - self.touch_start[1])

            if dx < 10 and dy < 10:  # Tap threshold
                self._trigger_handler('tap', event)

    def _on_touch_move(self, event):
        """Handle touch move."""
        if self.touch_start:
            dx = abs(event.x - self.touch_start[0])
            dy = abs(event.y - self.touch_start[1])

            if dx > 20 or dy > 20:  # Drag threshold
                self._trigger_handler('drag', event)

    def _on_touch_leave(self, event):
        """Handle touch leave."""
        if self.long_press_timer:
            self.after_cancel(self.long_press_timer)
            self.long_press_timer = None

        self._scale_button(1.0)

    def _on_long_press(self):
        """Handle long press."""
        self.long_press_timer = None
        self._trigger_handler('long_press', None)

    def _scale_button(self, scale: float):
        """Scale button for visual feedback."""
        try:
            # Simple scaling effect (could be enhanced with actual scaling)
            if scale < 1.0:
                self.configure(border_width=2, border_color=self.cget('fg_color'))
            else:
                self.configure(border_width=0)
        except:
            pass

    def _trigger_handler(self, gesture: str, event):
        """Trigger gesture handler."""
        if gesture in self.gesture_handlers:
            try:
                self.gesture_handlers[gesture](event)
            except Exception as e:
                print(f"Gesture handler error: {e}")

    def bind_gesture(self, gesture: str, handler: Callable):
        """Bind a gesture handler."""
        self.gesture_handlers[gesture] = handler


class ResponsiveSidebar(ctk.CTkFrame):
    """Responsive sidebar that adapts to screen size."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        self.is_collapsed = False
        self.animation_duration = 300

        # Create responsive grid
        self.responsive_grid = ResponsiveGrid(self, fg_color="transparent")

        # Navigation items container
        self.nav_container = ctk.CTkFrame(self.responsive_grid, fg_color="transparent")

        # Collapse/expand button
        self.toggle_btn = TouchButton(
            self.nav_container, text="☰",
            command=self.toggle_sidebar,
            width=40, height=40
        )
        self.toggle_btn.pack(pady=(10, 20), padx=10)

        # Navigation buttons container
        self.buttons_frame = ctk.CTkFrame(self.nav_container, fg_color="transparent")
        self.buttons_frame.pack(fill="x", padx=10)

        self.nav_buttons = []

    def add_nav_button(self, text: str, icon: str, command: Callable):
        """Add a navigation button."""
        btn = TouchButton(
            self.buttons_frame, text=f"{icon} {text}",
            command=command, anchor="w",
            height=50
        )
        btn.pack(fill="x", pady=2, padx=5)
        self.nav_buttons.append(btn)

        return btn

    def toggle_sidebar(self):
        """Toggle sidebar collapse/expand."""
        target_width = 80 if not self.is_collapsed else 250
        self.is_collapsed = not self.is_collapsed

        # Animate width change
        self._animate_width(target_width)

        # Update button visibility
        for btn in self.nav_buttons:
            if self.is_collapsed:
                # Show only icons
                text = btn.cget('text')
                if ' ' in text:
                    icon = text.split(' ')[0]
                    btn.configure(text=icon)
            else:
                # Restore full text (this would need to be stored)
                pass

    def _animate_width(self, target_width: int):
        """Animate sidebar width change."""
        current_width = self.winfo_width()
        if current_width == 0:
            current_width = 250

        steps = 20
        step_duration = self.animation_duration // steps
        width_diff = target_width - current_width

        def animate_step(step: int):
            if step >= steps:
                return

            progress = step / steps
            new_width = current_width + (width_diff * progress)

            self.configure(width=int(new_width))

            self.after(step_duration, lambda: animate_step(step + 1))

        animate_step(0)


# Utility functions
def get_screen_size(root: tk.Tk) -> Tuple[int, int]:
    """Get screen size."""
    return root.winfo_screenwidth(), root.winfo_screenheight()


def is_mobile_device() -> bool:
    """Check if running on mobile device."""
    try:
        import platform
        system = platform.system().lower()
        return 'android' in system or 'ios' in system
    except:
        return False


def create_responsive_layout(parent, config: Dict[str, Any] = None) -> ResponsiveGrid:
    """Create a responsive layout with default configuration."""
    if config is None:
        config = {
            Breakpoint.MOBILE: {
                'columns': 1, 'gutter': 10, 'padding': 15,
                'font_scale': 0.8, 'touch_target_size': 44
            },
            Breakpoint.TABLET: {
                'columns': 2, 'gutter': 15, 'padding': 20,
                'font_scale': 0.9, 'touch_target_size': 44
            },
            Breakpoint.DESKTOP: {
                'columns': 3, 'gutter': 20, 'padding': 25,
                'font_scale': 1.0, 'touch_target_size': 32
            },
            Breakpoint.LARGE: {
                'columns': 4, 'gutter': 25, 'padding': 30,
                'font_scale': 1.1, 'touch_target_size': 32
            }
        }

    return ResponsiveGrid(parent, config)