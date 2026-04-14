"""Demo script showcasing modern UI components with animations and data visualizations."""

import customtkinter as ctk
import tkinter as tk
from datetime import datetime, timedelta
import random
import sys
from pathlib import Path

# Add src to sys.path if running from project root
sys.path.insert(0, str(Path(__file__).parent / 'src'))

# Corrected imports (all from ui.cards)
from ui.cards import (
    AnimatedCard, PerformanceChart, MetricGauge, StatusIndicator,
    AnimatedButton, NotificationBadge, create_sample_machine_data,
    create_performance_chart_data
)
from ui.theme import get_theme, set_theme_mode, ThemeMode


class ModernUIDemo(ctk.CTk):
    """Demo application showcasing modern UI components."""

    def __init__(self):
        super().__init__()

        # Configure window
        self.title("Modern UI Components Demo")
        self.geometry("1200x800")

        # Set theme
        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")

        # Create main container
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Title
        title_label = ctk.CTkLabel(
            self.main_frame, text="Modern UI Components Showcase",
            font=("Arial", 24, "bold")
        )
        title_label.pack(pady=(20, 30))

        # Theme toggle button
        self.theme_button = AnimatedButton(
            self.main_frame, text="Toggle Theme",
            command=self.toggle_theme, animation_type="glow"
        )
        self.theme_button.pack(pady=(0, 20))

        # Create scrollable frame for components
        self.scrollable_frame = ctk.CTkScrollableFrame(self.main_frame)
        self.scrollable_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Create demo components
        self.create_animated_cards_section()
        self.create_charts_section()
        self.create_gauges_section()
        self.create_status_indicators_section()
        self.create_interactive_elements_section()

    def create_animated_cards_section(self):
        """Create section with animated cards."""
        section_label = ctk.CTkLabel(
            self.scrollable_frame, text="🎴 Animated Cards",
            font=("Arial", 18, "bold")
        )
        section_label.pack(pady=(20, 15), anchor="w")

        cards_frame = ctk.CTkFrame(self.scrollable_frame, fg_color="transparent")
        cards_frame.pack(fill="x", pady=(0, 30))

        # Sample data
        machine_data = create_sample_machine_data(24)

        # Performance card
        latest_perf = machine_data[-1]['performance']
        prev_perf = machine_data[-2]['performance']
        trend = ((latest_perf - prev_perf) / prev_perf) * 100

        perf_card = AnimatedCard(
            cards_frame, "Machine Performance", f"{latest_perf:.1f}%",
            icon="⚙️", trend=trend, trend_label="vs yesterday"
        )
        perf_card.pack(side="left", padx=(0, 20), pady=10)

        # Efficiency card
        latest_eff = machine_data[-1]['efficiency']
        prev_eff = machine_data[-2]['efficiency']
        eff_trend = ((latest_eff - prev_eff) / prev_eff) * 100

        eff_card = AnimatedCard(
            cards_frame, "Efficiency", f"{latest_eff:.1f}%",
            icon="📈", trend=eff_trend, trend_label="vs yesterday",
            color="#4CAF50"
        )
        eff_card.pack(side="left", padx=(0, 20), pady=10)

        # Temperature card
        temp = machine_data[-1]['temperature']
        temp_card = AnimatedCard(
            cards_frame, "Temperature", f"{temp:.1f}°C",
            icon="🌡️", color="#FF9800"
        )
        temp_card.pack(side="left", padx=0, pady=10)

    def create_charts_section(self):
        """Create section with performance charts."""
        section_label = ctk.CTkLabel(
            self.scrollable_frame, text="📊 Performance Charts",
            font=("Arial", 18, "bold")
        )
        section_label.pack(pady=(20, 15), anchor="w")

        charts_frame = ctk.CTkFrame(self.scrollable_frame, fg_color="transparent")
        charts_frame.pack(fill="x", pady=(0, 30))

        # Create sample data
        machine_data = create_sample_machine_data(24)
        chart_data = create_performance_chart_data(machine_data)

        # Performance chart
        perf_chart = PerformanceChart(
            charts_frame, "Machine Performance Over Time", chart_data,
            chart_type="line", width=500, height=300
        )
        perf_chart.pack(side="left", padx=(0, 20))

        # Additional metrics chart
        temp_data = [{
            'x': [d['timestamp'] for d in machine_data],
            'y': [d['temperature'] for d in machine_data],
            'name': 'Temperature (°C)',
            'color': '#FF5722'
        }]

        temp_chart = PerformanceChart(
            charts_frame, "Temperature Monitoring", temp_data,
            chart_type="line", width=400, height=300
        )
        temp_chart.pack(side="left")

    def create_gauges_section(self):
        """Create section with metric gauges."""
        section_label = ctk.CTkLabel(
            self.scrollable_frame, text="🎯 Metric Gauges",
            font=("Arial", 18, "bold")
        )
        section_label.pack(pady=(20, 15), anchor="w")

        gauges_frame = ctk.CTkFrame(self.scrollable_frame, fg_color="transparent")
        gauges_frame.pack(fill="x", pady=(0, 30))

        # Performance gauge
        perf_gauge = MetricGauge(
            gauges_frame, "Overall Performance", 87.5, max_value=100
        )
        perf_gauge.pack(side="left", padx=(0, 30))

        # Efficiency gauge
        eff_gauge = MetricGauge(
            gauges_frame, "Efficiency", 92.3, max_value=100, color="#4CAF50"
        )
        eff_gauge.pack(side="left", padx=(0, 30))

        # Utilization gauge
        util_gauge = MetricGauge(
            gauges_frame, "Utilization", 78.9, max_value=100, color="#FF9800"
        )
        util_gauge.pack(side="left")

    def create_status_indicators_section(self):
        """Create section with status indicators."""
        section_label = ctk.CTkLabel(
            self.scrollable_frame, text="🔴 Status Indicators",
            font=("Arial", 18, "bold")
        )
        section_label.pack(pady=(20, 15), anchor="w")

        status_frame = ctk.CTkFrame(self.scrollable_frame, fg_color="transparent")
        status_frame.pack(fill="x", pady=(0, 30))

        # Different status indicators
        statuses = ["Online", "Running", "Active", "Offline", "Error", "Warning", "Maintenance"]

        for status in statuses:
            indicator = StatusIndicator(status_frame, status)
            indicator.pack(side="left", padx=(0, 20))

    def create_interactive_elements_section(self):
        """Create section with interactive elements."""
        section_label = ctk.CTkLabel(
            self.scrollable_frame, text="🎮 Interactive Elements",
            font=("Arial", 18, "bold")
        )
        section_label.pack(pady=(20, 15), anchor="w")

        interactive_frame = ctk.CTkFrame(self.scrollable_frame, fg_color="transparent")
        interactive_frame.pack(fill="x", pady=(0, 30))

        # Animated buttons
        buttons_frame = ctk.CTkFrame(interactive_frame, fg_color="transparent")
        buttons_frame.pack(fill="x", pady=(0, 20))

        scale_button = AnimatedButton(
            buttons_frame, "Scale Animation", command=self.on_scale_click,
            animation_type="scale"
        )
        scale_button.pack(side="left", padx=(0, 20))

        glow_button = AnimatedButton(
            buttons_frame, "Glow Animation", command=self.on_glow_click,
            animation_type="glow"
        )
        glow_button.pack(side="left", padx=(0, 20))

        # Notification badges
        badges_frame = ctk.CTkFrame(interactive_frame, fg_color="transparent")
        badges_frame.pack(fill="x")

        # Badge with button
        badge_container = ctk.CTkFrame(badges_frame, fg_color="transparent")
        badge_container.pack(side="left", padx=(0, 30))

        badge_button = ctk.CTkButton(
            badge_container, text="Notifications",
            command=self.on_notification_click
        )
        badge_button.pack(side="left")

        self.notification_badge = NotificationBadge(badge_container, 3)
        self.notification_badge.pack(side="left")

        # Counter controls
        counter_frame = ctk.CTkFrame(badges_frame, fg_color="transparent")
        counter_frame.pack(side="left")

        minus_btn = ctk.CTkButton(
            counter_frame, text="-", width=40,
            command=lambda: self.update_badge_count(-1)
        )
        minus_btn.pack(side="left", padx=(0, 10))

        plus_btn = ctk.CTkButton(
            counter_frame, text="+", width=40,
            command=lambda: self.update_badge_count(1)
        )
        plus_btn.pack(side="left")

    def toggle_theme(self):
        """Toggle between light and dark themes."""
        current_mode = get_theme().mode
        if current_mode == ThemeMode.LIGHT:
            set_theme_mode(ThemeMode.DARK)
            ctk.set_appearance_mode("dark")
        else:
            set_theme_mode(ThemeMode.LIGHT)
            ctk.set_appearance_mode("light")

    def on_scale_click(self):
        """Handle scale button click."""
        print("Scale animation button clicked!")

    def on_glow_click(self):
        """Handle glow button click."""
        print("Glow animation button clicked!")

    def on_notification_click(self):
        """Handle notification button click."""
        self.update_badge_count(-self.notification_badge.count)  # Clear notifications

    def update_badge_count(self, delta: int):
        """Update notification badge count."""
        new_count = max(0, self.notification_badge.count + delta)
        self.notification_badge.update_count(new_count)


def main():
    """Run the modern UI demo."""
    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")

    app = ModernUIDemo()
    app.mainloop()


if __name__ == "__main__":
    main()