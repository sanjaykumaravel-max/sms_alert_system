"""Test script for responsive UI components and layouts.

This script tests:
- Grid-based responsive layouts with breakpoints
- Adaptive UI components that scale with window size
- Mobile-optimized views for tablet/phone access
- Touch-friendly interactions with gesture support
"""

import customtkinter as ctk
import tkinter as tk
from src.ui.responsive import ResponsiveGrid, Breakpoint, TouchButton, AdaptiveCard, ResponsiveSidebar
from src.ui.cards import AnimatedCard, PerformanceChart, MetricGauge, StatusIndicator, create_sample_machine_data, create_performance_chart_data
from src.ui.theme import get_theme
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))


class ResponsiveTestApp(ctk.CTk):
    """Test application for responsive UI components."""

    def __init__(self):
        super().__init__()

        self.title("Responsive UI Test - SMS Alert App")
        self.geometry("1200x800")
        self.minsize(400, 600)

        # Apply theme
        try:
            theme = get_theme()
            colors = theme.get_color_tokens()
            from src.ui.theme import apply_gradient_background
            apply_gradient_background(self, [colors.primary, colors.secondary, colors.tertiary])
        except Exception as e:
            print(f"Theme application error: {e}")

        # Create responsive main layout
        self.main_grid = ResponsiveGrid(self, fg_color="transparent")
        self.main_grid.pack(fill="both", expand=True, padx=10, pady=10)

        # Create responsive sidebar
        self.sidebar = ResponsiveSidebar(self.main_grid, fg_color="#2A2D3A")
        self.sidebar.pack(side="left", fill="y", padx=(0, 10))

        # Add navigation items
        self.sidebar.add_nav_button("📊 Dashboard", "📊", self.show_dashboard)
        self.sidebar.add_nav_button("📈 Charts", "📈", self.show_charts)
        self.sidebar.add_nav_button("🎛️ Gauges", "🎛️", self.show_gauges)
        self.sidebar.add_nav_button("📱 Mobile Test", "📱", self.show_mobile_test)

        # Create content area
        self.content_frame = ctk.CTkFrame(self.main_grid, fg_color="transparent")
        self.content_frame.pack(side="left", fill="both", expand=True)

        # Content container with responsive grid
        self.content_grid = ResponsiveGrid(self.content_frame, fg_color="transparent")
        self.content_grid.pack(fill="both", expand=True)

        # Initialize content
        self.show_dashboard()

        # Bind window resize for testing
        self.bind('<Configure>', self.on_window_resize)

        # Add breakpoint indicator
        self.breakpoint_label = ctk.CTkLabel(
            self.sidebar, text="Breakpoint: Desktop",
            font=("Arial", 10)
        )
        self.breakpoint_label.pack(side="bottom", pady=10)

    def on_window_resize(self, event=None):
        """Update breakpoint indicator on resize."""
        if hasattr(self.main_grid, '_current_config') and self.main_grid._current_config:
            config = self.main_grid._current_config
            self.breakpoint_label.configure(
                text=f"Breakpoint: {config.breakpoint.value.title()}\n"
                     f"Size: {config.width}x{config.height}\n"
                     f"Scale: {config.scale_factor:.2f}\n"
                     f"Touch: {config.touch_enabled}"
            )

    def clear_content(self):
        """Clear current content."""
        for widget in self.content_grid.winfo_children():
            widget.destroy()

    def show_dashboard(self):
        """Show dashboard with responsive cards."""
        self.clear_content()

        # Title
        title = ctk.CTkLabel(
            self.content_grid, text="📊 Responsive Dashboard",
            font=("Arial", 24, "bold")
        )
        title.pack(pady=(20, 30))

        # Cards container
        cards_frame = ctk.CTkFrame(self.content_grid, fg_color="transparent")
        cards_frame.pack(fill="x", padx=20)

        # Configure responsive grid for cards
        cards_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        # Create responsive cards
        cards_data = [
            ("🏭 Total Machines", "24", None),
            ("🚨 Critical", "3", "#F44336"),
            ("⏰ Due Tasks", "8", "#FF9800"),
            ("⚠️ Overdue", "2", "#F44336")
        ]

        self.cards = []
        for i, (title_text, value, color) in enumerate(cards_data):
            card = AnimatedCard(cards_frame, title_text, value, color=color)
            card.grid(row=0, column=i, padx=10, pady=10, sticky="ew")
            self.cards.append(card)

        # Register cards with responsive system
        responsive_config = {
            Breakpoint.MOBILE: {
                'grid': {'row': 1, 'column': 0, 'columnspan': 1, 'sticky': 'ew'},
                'font_scale': 0.8
            },
            Breakpoint.TABLET: {
                'grid': {'row': 1, 'column': 0, 'columnspan': 2, 'sticky': 'ew'},
                'font_scale': 0.9
            },
            Breakpoint.DESKTOP: {
                'grid': {'row': 1, 'column': 0, 'columnspan': 4, 'sticky': 'ew'},
                'font_scale': 1.0
            },
            Breakpoint.LARGE: {
                'grid': {'row': 1, 'column': 0, 'columnspan': 4, 'sticky': 'ew'},
                'font_scale': 1.1
            }
        }

        self.content_grid.register_component('cards_container', cards_frame, responsive_config)

    def show_charts(self):
        """Show responsive charts."""
        self.clear_content()

        # Title
        title = ctk.CTkLabel(
            self.content_grid, text="📈 Performance Charts",
            font=("Arial", 24, "bold")
        )
        title.pack(pady=(20, 30))

        # Charts container
        charts_frame = ctk.CTkFrame(self.content_grid, fg_color="transparent")
        charts_frame.pack(fill="both", expand=True, padx=20)

        # Create sample data
        machine_data = create_sample_machine_data(24)
        chart_data = create_performance_chart_data(machine_data)

        # Performance chart with responsive sizing
        chart_width = 600
        chart_height = 300

        # Adjust for current breakpoint
        if hasattr(self.content_grid, '_current_config') and self.content_grid._current_config:
            config = self.content_grid._current_config
            if config.breakpoint == Breakpoint.MOBILE:
                chart_width = int(chart_width * 0.5)
                chart_height = int(chart_height * 0.5)
            elif config.breakpoint == Breakpoint.TABLET:
                chart_width = int(chart_width * 0.75)
                chart_height = int(chart_height * 0.75)

        perf_chart = PerformanceChart(
            charts_frame, "Machine Performance (24h)", chart_data,
            chart_type="line", width=chart_width, height=chart_height
        )
        perf_chart.pack(pady=20)

    def show_gauges(self):
        """Show responsive gauges."""
        self.clear_content()

        # Title
        title = ctk.CTkLabel(
            self.content_grid, text="🎛️ Metric Gauges",
            font=("Arial", 24, "bold")
        )
        title.pack(pady=(20, 30))

        # Gauges container
        gauges_frame = ctk.CTkFrame(self.content_grid, fg_color="transparent")
        gauges_frame.pack(fill="x", padx=20)

        # Configure responsive grid
        gauges_frame.grid_columnconfigure((0, 1, 2), weight=1)

        # Sample gauge data
        gauge_data = [
            ("Performance", 85, 100, "%", "#6750A4"),
            ("Efficiency", 92, 100, "%", "#4CAF50"),
            ("Temperature", 75, 100, "°C", "#FF9800")
        ]

        for i, (title_text, value, max_val, unit, color) in enumerate(gauge_data):
            gauge = MetricGauge(
                gauges_frame, title_text, value,
                max_value=max_val, unit=unit, color=color
            )
            gauge.grid(row=0, column=i, padx=10, pady=10, sticky="n")

    def show_mobile_test(self):
        """Show mobile-optimized test view."""
        self.clear_content()

        # Title
        title = ctk.CTkLabel(
            self.content_grid, text="📱 Mobile Test View",
            font=("Arial", 24, "bold")
        )
        title.pack(pady=(20, 30))

        # Touch-friendly buttons container
        buttons_frame = ctk.CTkFrame(self.content_grid, fg_color="transparent")
        buttons_frame.pack(fill="x", padx=20)

        # Configure responsive grid
        buttons_frame.grid_columnconfigure(0, weight=1)

        # Create touch-friendly buttons
        touch_buttons = [
            ("Tap Test", self.on_touch_tap),
            ("Long Press Test", self.on_long_press),
            ("Swipe Test", self.on_swipe_test)
        ]

        self.touch_test_buttons = []
        for btn_text, command in touch_buttons:
            btn = TouchButton(
                buttons_frame, text=btn_text,
                command=command, height=60,
                font=("Arial", 16)
            )
            btn.grid(row=len(self.touch_test_buttons), column=0,
                    padx=20, pady=10, sticky="ew")

            # Bind gesture handlers
            btn.bind_gesture('tap', lambda e, t=btn_text: self.on_gesture(t, 'tap'))
            btn.bind_gesture('long_press', lambda e, t=btn_text: self.on_gesture(t, 'long_press'))

            self.touch_test_buttons.append(btn)

        # Status indicators
        status_frame = ctk.CTkFrame(self.content_grid, fg_color="transparent")
        status_frame.pack(fill="x", padx=20, pady=20)

        status_data = [
            "System Operational",
            "Maintenance Mode",
            "Critical Alert"
        ]

        for status in status_data:
            indicator = StatusIndicator(status_frame, status)
            indicator.pack(side="left", padx=(0, 20))

    def on_touch_tap(self):
        """Handle touch tap."""
        print("Touch tap detected!")

    def on_long_press(self):
        """Handle long press."""
        print("Long press detected!")

    def on_swipe_test(self):
        """Handle swipe test."""
        print("Swipe test initiated!")

    def on_gesture(self, button_text: str, gesture: str):
        """Handle gesture events."""
        print(f"Gesture '{gesture}' detected on button '{button_text}'")


def main():
    """Main test function."""
    print("Starting Responsive UI Test...")

    # Set appearance
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")

    # Create and run app
    app = ResponsiveTestApp()
    print("Responsive UI Test App created successfully!")

    # Test responsive features
    print("\nTesting responsive features:")
    print("- Resize window to test breakpoints")
    print("- Try touch gestures on mobile-optimized view")
    print("- Check sidebar collapse/expand on smaller screens")

    app.mainloop()


if __name__ == "__main__":
    main()