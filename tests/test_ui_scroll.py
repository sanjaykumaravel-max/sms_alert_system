from types import SimpleNamespace

from src.ui.scroll import _scroll_delta_from_event


def test_scroll_delta_from_mousewheel_windows_up():
    event = SimpleNamespace(delta=120, num=None)
    assert _scroll_delta_from_event(event) == -1


def test_scroll_delta_from_mousewheel_windows_down():
    event = SimpleNamespace(delta=-120, num=None)
    assert _scroll_delta_from_event(event) == 1


def test_scroll_delta_from_button_events_linux():
    assert _scroll_delta_from_event(SimpleNamespace(num=4, delta=0)) == -1
    assert _scroll_delta_from_event(SimpleNamespace(num=5, delta=0)) == 1
