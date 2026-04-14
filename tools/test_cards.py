import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
from ui.dashboard import Dashboard
import tkinter as tk
from api_client import sync_get_machines

root = tk.Tk()
root.withdraw()  # hide window
user = {'name': 'Test', 'role': 'admin'}
try:
    db = Dashboard(root, user)
    machines = sync_get_machines() or []
    db._update_ui_with_data(machines)
    # fetch card texts
    total = getattr(db, 'card_total', None)
    critical = getattr(db, 'card_critical', None)
    due = getattr(db, 'card_due', None)
    overdue = getattr(db, 'card_overdue', None)
    print('card_total:', total.value_label.cget('text') if total else 'MISSING')
    print('card_critical:', critical.value_label.cget('text') if critical else 'MISSING')
    print('card_due:', due.value_label.cget('text') if due else 'MISSING')
    print('card_overdue:', overdue.value_label.cget('text') if overdue else 'MISSING')
except Exception as e:
    print('ERROR while testing cards:', e)
finally:
    try:
        root.destroy()
    except Exception:
        pass
