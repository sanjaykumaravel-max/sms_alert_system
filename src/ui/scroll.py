import tkinter as tk


def _scroll_delta_from_event(event: tk.Event) -> int:
    """Map wheel events to Tk canvas scroll units."""
    num = getattr(event, "num", None)
    if num == 4:
        return -1
    if num == 5:
        return 1

    delta = getattr(event, "delta", 0)
    if delta > 0:
        return -1
    if delta < 0:
        return 1
    return 0


def _resolve_scroll_canvas(root: tk.Misc, event: tk.Event) -> tk.Canvas | None:
    """Find the scrollable canvas under the pointer, falling back to the last active canvas."""
    try:
        widget = root.winfo_containing(event.x_root, event.y_root)
    except Exception:
        widget = None

    while widget is not None:
        if isinstance(widget, tk.Canvas):
            return widget
        try:
            owner_canvas = getattr(widget, "_mw_canvas_owner", None)
            if owner_canvas is not None:
                return owner_canvas
        except Exception:
            pass
        try:
            widget = widget.master
        except Exception:
            widget = None

    # Fallback: use event widget ownership when pointer resolution fails.
    widget = getattr(event, "widget", None)
    while widget is not None:
        if isinstance(widget, tk.Canvas):
            return widget
        try:
            owner_canvas = getattr(widget, "_mw_canvas_owner", None)
            if owner_canvas is not None:
                return owner_canvas
        except Exception:
            pass
        try:
            widget = widget.master
        except Exception:
            widget = None

    return getattr(root, "_mw_active_canvas", None)


def _bind_canvas_owner(widget: tk.Widget, canvas: tk.Canvas) -> None:
    """Mark widget descendants so wheel dispatch can resolve the right scroll owner."""
    try:
        widget._mw_canvas_owner = canvas
    except Exception:
        pass
    try:
        for child in widget.winfo_children():
            _bind_canvas_owner(child, canvas)
    except Exception:
        pass


def _install_global_scroll_dispatch(root: tk.Misc) -> None:
    """Install one root-level wheel handler and dispatch to active canvas."""
    if getattr(root, "_mw_dispatch_installed", False):
        return

    def _dispatch(event: tk.Event):
        canvas = _resolve_scroll_canvas(root, event)
        if canvas is None:
            return None
        try:
            if not int(canvas.winfo_exists()):
                root._mw_active_canvas = None
                return None
        except Exception:
            root._mw_active_canvas = None
            return None

        delta = _scroll_delta_from_event(event)
        if delta == 0:
            return None
        try:
            canvas.yview_scroll(delta, "units")
            return "break"
        except Exception:
            return None

    root.bind_all("<MouseWheel>", _dispatch, add="+")
    root.bind_all("<Button-4>", _dispatch, add="+")
    root.bind_all("<Button-5>", _dispatch, add="+")
    root._mw_dispatch_installed = True


def enable_mousewheel_scroll(widget: tk.Widget) -> None:
    """Enable reliable wheel scroll support for CTkScrollableFrame widgets."""
    try:
        if getattr(widget, "_mw_scroll_enabled", False):
            return

        canvas = None
        if hasattr(widget, "_canvas"):
            canvas = getattr(widget, "_canvas")
        elif hasattr(widget, "canvas"):
            canvas = getattr(widget, "canvas")
        else:
            for child in widget.winfo_children():
                if isinstance(child, tk.Canvas):
                    canvas = child
                    break

        if canvas is None:
            return

        root = widget.winfo_toplevel()
        _install_global_scroll_dispatch(root)

        def _activate(_event: tk.Event = None):
            try:
                _bind_canvas_owner(widget, canvas)
                root._mw_active_canvas = canvas
            except Exception:
                pass

        # Entering this scrollable area makes it the active wheel target.
        widget.bind("<Enter>", _activate, add="+")
        canvas.bind("<Enter>", _activate, add="+")
        widget.bind("<Motion>", _activate, add="+")
        canvas.bind("<Motion>", _activate, add="+")
        widget.bind("<Configure>", lambda _event: _bind_canvas_owner(widget, canvas), add="+")
        _bind_canvas_owner(widget, canvas)
        widget._mw_scroll_enabled = True
        _activate()
    except Exception:
        pass
