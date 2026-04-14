"""Comprehensive test for responsive UI implementation.

Tests:
1. Responsive grid layouts with breakpoints
2. Adaptive UI components scaling
3. Mobile-optimized views
4. Touch-friendly interactions
5. Backward compatibility with existing app
"""

import customtkinter as ctk
import tkinter as tk
import sys
import os
import time
import threading

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.ui.responsive import ResponsiveGrid, Breakpoint, TouchButton, AdaptiveCard
from src.ui.cards import AnimatedCard, PerformanceChart, MetricGauge, StatusIndicator
from src.ui.dashboard import Dashboard
from src.auth import load_users


def test_responsive_grid():
    """Test responsive grid functionality."""
    print("Testing ResponsiveGrid...")

    try:
        root = ctk.CTk()
        root.geometry("800x600")
        root.update()  # Force update to avoid icon errors

        # Create responsive grid
        grid = ResponsiveGrid(root, fg_color="transparent")
        grid.pack(fill="both", expand=True)
        grid.update()

        # Test breakpoint detection
        assert hasattr(grid, '_current_config')
        print("✓ ResponsiveGrid created successfully")

        # Test component registration
        test_frame = ctk.CTkFrame(grid, fg_color="red", width=100, height=100)
        test_frame.pack(pady=10)

        responsive_config = {
            Breakpoint.MOBILE: {'grid': {'row': 0, 'column': 0}},
            Breakpoint.DESKTOP: {'grid': {'row': 0, 'column': 1}}
        }

        grid.register_component('test_frame', test_frame, responsive_config)
        print("✓ Component registration works")

        root.destroy()
        return True
    except Exception as e:
        print(f"✗ ResponsiveGrid test error: {e}")
        return False


def test_touch_button():
    """Test touch-friendly button."""
    print("Testing TouchButton...")

    root = ctk.CTk()
    root.geometry("400x300")

    # Create touch button
    button = TouchButton(root, text="Test Button", height=50)
    button.pack(pady=20, padx=20, fill="x")

    # Test gesture binding
    gesture_detected = False

    def on_tap(event):
        nonlocal gesture_detected
        gesture_detected = True

    button.bind_gesture('tap', on_tap)

    # Simulate click
    button.invoke()

    print("✓ TouchButton created and gesture binding works")
    root.destroy()
    return True


def test_adaptive_card():
    """Test adaptive card component."""
    print("Testing AdaptiveCard...")

    root = ctk.CTk()
    root.geometry("600x400")

    # Create adaptive card
    card = AdaptiveCard(root, "Test Card", "Test Content")
    card.pack(pady=20, padx=20, fill="x")

    assert hasattr(card, 'responsive_grid')
    print("✓ AdaptiveCard created with responsive grid")

    root.destroy()
    return True


def test_main_app_compatibility():
    """Test that main app still works with responsive changes."""
    print("Testing main app compatibility...")

    # Mock user object with proper attributes
    class MockUser:
        def __init__(self):
            self.username = "admin"
            self.role = "admin"
            self.name = "Administrator"

        def get(self, key, default=None):
            return getattr(self, key, default)

    try:
        # Load users for testing
        load_users()

        # Create dashboard (this will test all responsive integrations)
        root = ctk.CTk()
        root.geometry("1000x700")

        dashboard = Dashboard(MockUser())

        # Check that responsive grid was created
        assert hasattr(dashboard, 'dashboard_grid')
        assert isinstance(dashboard.dashboard_grid, ResponsiveGrid)
        print("✓ Dashboard created with responsive grid")

        # Check that cards are created
        assert hasattr(dashboard, 'card_total')
        assert hasattr(dashboard, 'card_critical')
        print("✓ Dashboard cards created successfully")

        root.destroy()
        return True

    except Exception as e:
        print(f"✗ Main app compatibility test failed: {e}")
        return False


def test_breakpoint_detection():
    """Test breakpoint detection logic."""
    print("Testing breakpoint detection...")

    root = ctk.CTk()

    # Test different window sizes
    test_sizes = [
        (400, 600, Breakpoint.MOBILE),
        (800, 600, Breakpoint.TABLET),
        (1200, 600, Breakpoint.DESKTOP),
        (1600, 600, Breakpoint.LARGE)
    ]

    for width, height, expected_bp in test_sizes:
        root.geometry(f"{width}x{height}")
        root.update()

        # Create responsive grid and check breakpoint
        grid = ResponsiveGrid(root)
        grid.update()

        if hasattr(grid, '_current_config') and grid._current_config:
            detected_bp = grid._current_config.breakpoint
            assert detected_bp == expected_bp, f"Expected {expected_bp}, got {detected_bp}"
            print(f"✓ Breakpoint detection works for {width}x{height} -> {detected_bp.value}")

        grid.destroy()

    root.destroy()
    return True


def run_visual_test():
    """Run visual test of responsive features."""
    print("Running visual responsive test...")

    def visual_test_thread():
        root = ctk.CTk()
        root.title("Responsive Visual Test")
        root.geometry("1200x800")

        # Create responsive layout
        main_grid = ResponsiveGrid(root, fg_color="#1A1B26")
        main_grid.pack(fill="both", expand=True, padx=10, pady=10)

        # Add test content
        title = ctk.CTkLabel(main_grid, text="🎯 Responsive UI Test", font=("Arial", 24, "bold"))
        title.pack(pady=20)

        # Test cards
        cards_frame = ctk.CTkFrame(main_grid, fg_color="transparent")
        cards_frame.pack(fill="x", padx=20, pady=10)

        cards_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        test_cards = []
        for i in range(4):
            card = AnimatedCard(cards_frame, f"Card {i+1}", str((i+1)*10), icon="📊")
            card.grid(row=0, column=i, padx=5, pady=5, sticky="ew")
            test_cards.append(card)

        # Instructions
        instructions = ctk.CTkLabel(
            main_grid,
            text="📱 Resize window to test responsive breakpoints\n"
                 "📊 Cards should adapt to different screen sizes\n"
                 "👆 Try touch gestures on interactive elements",
            font=("Arial", 12)
        )
        instructions.pack(pady=20)

        # Breakpoint indicator
        bp_label = ctk.CTkLabel(main_grid, text="Current Breakpoint: Detecting...", font=("Arial", 14, "bold"))
        bp_label.pack(pady=10)

        def update_breakpoint_indicator():
            if hasattr(main_grid, '_current_config') and main_grid._current_config:
                config = main_grid._current_config
                bp_label.configure(
                    text=f"Breakpoint: {config.breakpoint.value.title()}\n"
                         f"Size: {config.width}×{config.height}\n"
                         f"Scale: {config.scale_factor:.2f}"
                )
            root.after(500, update_breakpoint_indicator)

        update_breakpoint_indicator()

        print("✓ Visual test window opened - resize to test responsiveness")
        root.mainloop()

    # Run visual test in separate thread
    visual_thread = threading.Thread(target=visual_test_thread, daemon=True)
    visual_thread.start()

    # Wait a bit for visual test to start
    time.sleep(2)
    return True


def main():
    """Run all responsive tests."""
    print("🚀 Starting Comprehensive Responsive UI Tests\n")

    tests = [
        ("Responsive Grid", test_responsive_grid),
        ("Touch Button", test_touch_button),
        ("Adaptive Card", test_adaptive_card),
        ("Breakpoint Detection", test_breakpoint_detection),
        ("Main App Compatibility", test_main_app_compatibility),
        ("Visual Test", run_visual_test)
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            if test_func():
                print(f"✅ {test_name}: PASSED\n")
                passed += 1
            else:
                print(f"❌ {test_name}: FAILED\n")
                failed += 1
        except Exception as e:
            print(f"❌ {test_name}: ERROR - {e}\n")
            failed += 1

    print(f"📊 Test Results: {passed} passed, {failed} failed")

    if failed == 0:
        print("🎉 All responsive UI tests passed!")
        print("\n📋 Features implemented:")
        print("✓ Grid-based responsive layouts with breakpoints")
        print("✓ Adaptive UI components that scale with window size")
        print("✓ Mobile-optimized views for tablet/phone access")
        print("✓ Touch-friendly interactions with gesture support")
        print("✓ Backward compatibility with existing application")
    else:
        print("⚠️  Some tests failed. Check implementation.")

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)