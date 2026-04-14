import customtkinter as ctk
import tkinter as tk
from typing import Tuple


def create_dialog(parent, title: str = None, width: int = 400, height: int = 300) -> Tuple[object, callable]:
    """Create a dialog attached to `parent`.

    If the parent appears to be inside the Dashboard (has attribute `dashboard`),
    create an embedded overlay Frame inside the parent's dashboard `main_frame`.
    Otherwise, create a CTkToplevel as before.

    Returns (container, destroy_fn).
    """
    try:
        # If parent has dashboard reference, create embedded frame
        dash = getattr(parent, 'dashboard', None) or (getattr(parent, 'parent', None) and getattr(parent.parent, 'dashboard', None))
        if dash is not None:
            container = ctk.CTkFrame(dash.main_frame, fg_color="#222222", corner_radius=8)
            # place as overlay in center
            container.place(relx=0.5, rely=0.5, anchor='center', width=width, height=height)

            def _destroy():
                try:
                    container.place_forget()
                    container.destroy()
                except Exception:
                    pass

            if title:
                try:
                    hdr = ctk.CTkLabel(container, text=title, font=("Arial", 14, "bold"))
                    hdr.pack(fill='x', padx=8, pady=6)
                except Exception:
                    pass
            return container, _destroy
    except Exception:
        pass

    # Fallback to Toplevel
    try:
        top = ctk.CTkToplevel(parent)
    except Exception:
        top = tk.Toplevel(parent)
    if title:
        try:
            top.title(title)
        except Exception:
            pass

    def _destroy_top():
        try:
            top.destroy()
        except Exception:
            pass

    return top, _destroy_top
