import sys
import traceback
from tkinter import Tk
import os
import sys
ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

try:
    root = Tk()
    root.withdraw()
    # Import dashboard class
    from src.ui.dashboard import Dashboard
    d = Dashboard(root, {'name':'tester'})
    try:
        # simulate clicking the sidebar button
        if getattr(d, 'sidebar', None):
            try:
                d.sidebar.show_machines()
                print('sidebar.show_machines() called')
            except Exception:
                print('sidebar.show_machines() raised:')
                traceback.print_exc()
        else:
            print('Dashboard has no sidebar')
        print('current_content=', getattr(d, 'current_content', None))
    except Exception as e:
        print('show_content("machines") raised:')
        traceback.print_exc()
    finally:
        try:
            root.destroy()
        except Exception:
            pass
except Exception:
    traceback.print_exc()
    sys.exit(1)
