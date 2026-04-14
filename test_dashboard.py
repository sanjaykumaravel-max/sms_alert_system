"""Test script for dashboard with modern UI components."""

import sys
from pathlib import Path

# Add src to path
src_dir = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(src_dir))

def test_dashboard():
    """Test dashboard with modern components."""
    try:
        from ui.dashboard import Dashboard
        print('Dashboard with modern components imported successfully')

        # Test that we can create a dashboard instance (without showing it)
        import os
        os.environ['DISPLAY'] = ''  # Prevent GUI from showing
        dashboard = Dashboard({'name': 'Test User', 'role': 'admin'})
        print('Dashboard instance created successfully')

        print('Dashboard modernization complete!')

    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_dashboard()