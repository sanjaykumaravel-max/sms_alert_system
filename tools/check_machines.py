import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
from api_client import sync_get_machines

machines = sync_get_machines() or []

total = len(machines)
critical = sum(1 for m in machines if (str(m.get('status') or '').lower() == 'critical'))
due = sum(1 for m in machines if (str(m.get('status') or '').lower() in ('maintenance', 'due')))
overdue = sum(1 for m in machines if (str(m.get('status') or '').lower() == 'overdue'))

print(f"Total machines: {total}")
print(f"Critical: {critical}")
print(f"Due (maintenance/due): {due}")
print(f"Overdue: {overdue}")
print('\nMachines list:')
for m in machines:
    print(f" - {m.get('id')} | {m.get('type')} | {m.get('status')}")

print('\nSURFACE_MACHINES fallback contents:')
try:
    import sys, os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
    from data import surface_machines
    for m in getattr(surface_machines, 'SURFACE_MACHINES', []):
        print(f" * {m.get('id')} | {m.get('type')} | {m.get('status')}")
except Exception as e:
    print('Could not load SURFACE_MACHINES:', e)
