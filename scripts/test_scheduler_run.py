import sys
import os
from datetime import datetime

# Ensure project root is on path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import tkinter as tk
from src.ui import scheduler

print('Starting scheduler template test')
root = tk.Tk()
root.withdraw()
try:
    sf = scheduler.SchedulerFrame(root, dashboard=None)
    print('SchedulerFrame created')
    # create a simple daily template
    tpl = {
        'id': 'tpl_test_1',
        'name': 'Test Daily Oil Change',
        'subject': 'Engine oil change',
        'type': 'daily',
        'every': 1,
        'start': datetime.utcnow().isoformat()
    }
    sf.templates.append(tpl)
    sf._save()
    print('Template appended and saved')

    # generate tasks for next 7 days
    sf._generate_from_templates(horizon_days=7, dedup_minutes=30)
    print(f'Generated tasks count: {len(sf.tasks)}')
    for i, t in enumerate(sf.tasks[:10]):
        print(i, t.get('subject'), t.get('scheduled_at'), t.get('status'))

    # show where tasks were saved
    print('Tasks file:', sf.data_path)
    print('Templates file:', sf.templates_path)

except Exception as e:
    print('Error during test:', e)
finally:
    try:
        root.destroy()
    except Exception:
        pass

print('Done')
