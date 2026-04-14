# Modern UI Components

This document describes the modern UI components available in the SMS Alert App, featuring animations, data visualizations, and interactive elements.

## 🚀 Features

- **Custom Animated Components** with smooth transitions
- **Advanced Data Visualizations** using Plotly/Matplotlib integration
- **Interactive Charts** for machine performance metrics
- **Custom Icons and Micro-interactions**
- **Material Design 3** compliant components
- **WCAG Accessibility** compliance
- **Theme Integration** with automatic dark/light mode support

## 📦 Components

### AnimatedCard

Modern animated card with hover effects, trend indicators, and smooth transitions.

```python
from ui.cards import AnimatedCard

# Basic card
card = AnimatedCard(parent, "Machine Status", "Running")

# Card with trend indicator
perf_card = AnimatedCard(
    parent, "Performance", "87.5%",
    icon="⚙️",
    trend=2.3,
    trend_label="vs yesterday"
)
```

### PerformanceChart

Interactive charts for displaying machine performance data using Plotly or Matplotlib.

```python
from ui.cards import PerformanceChart, create_performance_chart_data

# Create chart data
machine_data = create_sample_machine_data(24)
chart_data = create_performance_chart_data(machine_data)

# Create chart
chart = PerformanceChart(
    parent, "Performance Over Time", chart_data,
    chart_type="line", width=500, height=300
)
```

### MetricGauge

Circular gauge for displaying metric values with smooth animations.

```python
from ui.cards import MetricGauge

gauge = MetricGauge(
    parent, "Efficiency", 92.5,
    max_value=100, unit="%", color="#4CAF50"
)

# Update value with animation
gauge.update_value(95.2)
```

### StatusIndicator

Animated status indicators with pulsing effects for active states.

```python
from ui.cards import StatusIndicator

indicator = StatusIndicator(parent, "Running", color="#4CAF50")
indicator.update_status("Error")  # Changes color and animation
```

### AnimatedButton

Custom buttons with micro-interactions and animation effects.

```python
from ui.cards import AnimatedButton

# Scale animation on hover
scale_btn = AnimatedButton(
    parent, "Click Me", command=my_function,
    animation_type="scale"
)

# Glow effect on hover
glow_btn = AnimatedButton(
    parent, "Hover Me", command=my_function,
    animation_type="glow"
)
```

### NotificationBadge

Animated notification badges with count display.

```python
from ui.cards import NotificationBadge

badge = NotificationBadge(parent, count=5)
badge.update_count(10)  # Animated update
```

## 🎨 Theme Integration

All components automatically integrate with the advanced theme system:

```python
from ui.theme import get_theme, set_theme_mode, ThemeMode

# Get current theme
theme = get_theme()
colors = theme.get_color_tokens()

# Switch themes
set_theme_mode(ThemeMode.DARK)
set_theme_mode(ThemeMode.LIGHT)
set_theme_mode(ThemeMode.SYSTEM)  # Follows system preference
```

## 📊 Data Visualization

### Sample Data Generation

```python
from ui.cards import create_sample_machine_data, create_performance_chart_data

# Generate 24 hours of sample machine data
machine_data = create_sample_machine_data(24)

# Convert to chart format
chart_data = create_performance_chart_data(machine_data)
```

### Chart Types Supported

- **Line Charts**: Time series performance data
- **Bar Charts**: Categorical comparisons
- **Pie Charts**: Distribution visualization
- **Matplotlib Fallback**: When Plotly is unavailable

## 🔧 Installation Requirements

```bash
pip install plotly matplotlib pillow
```

## 🎯 Usage Examples

### Complete Dashboard Example

```python
import customtkinter as ctk
from ui.cards import AnimatedCard, PerformanceChart, MetricGauge
from ui.theme import get_theme

class Dashboard(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent)

        # Performance metrics cards
        perf_card = AnimatedCard(self, "Performance", "87.5%", icon="⚙️")
        perf_card.pack(pady=10)

        # Performance chart
        chart_data = create_performance_chart_data(create_sample_machine_data(24))
        chart = PerformanceChart(self, "Performance Trend", chart_data)
        chart.pack(pady=10)

        # Efficiency gauge
        gauge = MetricGauge(self, "Efficiency", 92.3)
        gauge.pack(pady=10)
```

## 🎨 Customization

### Custom Colors

```python
# Use theme colors
theme = get_theme()
tokens = theme.get_color_tokens()

card = AnimatedCard(
    parent, "Custom", "Value",
    color=tokens.secondary  # Use theme secondary color
)
```

### Custom Animations

```python
from ui.theme import animate_widget

# Custom animation
animate_widget(widget, "corner_radius", 6, 12, 300)
```

## ♿ Accessibility

All components are designed with accessibility in mind:

- **WCAG AA Compliance**: Contrast ratios ≥ 4.5:1
- **Keyboard Navigation**: Full keyboard support
- **Screen Reader Support**: Proper labeling and descriptions
- **High Contrast**: Automatic theme adaptation

## 🔄 Backward Compatibility

Legacy `Card` class is maintained for existing code:

```python
from ui.cards import Card  # Legacy class still available

legacy_card = Card(parent, "Title", "Value")
```

## 🚀 Performance

- **Efficient Rendering**: Optimized for smooth animations
- **Lazy Loading**: Charts load only when visible
- **Memory Management**: Automatic cleanup of resources
- **Threading Support**: Background data processing

## 📝 API Reference

### AnimatedCard
- `title`: Card title text
- `value`: Main value to display
- `icon`: Optional emoji/icon
- `trend`: Trend percentage (optional)
- `trend_label`: Trend description (optional)
- `color`: Custom color override

### PerformanceChart
- `title`: Chart title
- `data`: Chart data in list of dict format
- `chart_type`: "line", "bar", or "pie"
- `width/height`: Chart dimensions

### MetricGauge
- `title`: Gauge title
- `value`: Current value
- `max_value`: Maximum value (default: 100)
- `unit`: Unit string (default: "%")
- `color`: Custom color

### StatusIndicator
- `status`: Status text ("Online", "Running", etc.)
- `color`: Custom color override
- `size`: Indicator size in pixels

### AnimatedButton
- `text`: Button text
- `command`: Click callback function
- `animation_type`: "scale" or "glow"

### NotificationBadge
- `count`: Initial notification count
- `max_count`: Maximum display count (default: 99)