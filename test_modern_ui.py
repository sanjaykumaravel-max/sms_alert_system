"""Test script for modern UI components."""

import sys
from pathlib import Path

# Add src to path
src_dir = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(src_dir))

def test_components():
    """Test modern UI components."""
    try:
        from ui.cards import AnimatedCard, PerformanceChart, MetricGauge, StatusIndicator, AnimatedButton, NotificationBadge
        from ui.theme import get_theme, ThemeMode
        print('All modern UI components imported successfully')

        # Test theme system
        theme = get_theme()
        print(f'Theme system active: {type(theme).__name__}')

        # Test color tokens
        tokens = theme.get_color_tokens()
        print(f'Primary color: {tokens.primary}')

        # Test sample data creation
        from ui.cards import create_sample_machine_data, create_performance_chart_data
        sample_data = create_sample_machine_data(5)
        chart_data = create_performance_chart_data(sample_data)
        print(f'Sample data created: {len(sample_data)} data points')

        print('Modern UI components ready for use!')

    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_components()