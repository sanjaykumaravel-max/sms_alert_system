import os, sys, datetime
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
from data import surface_machines
import pandas as pd

DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', 'src', 'data'))
MACHINES_FILE = os.path.join(DATA_DIR, 'machines.xlsx')
SHEET = 'Machines'

os.makedirs(DATA_DIR, exist_ok=True)

# load existing
if os.path.exists(MACHINES_FILE):
    try:
        df = pd.read_excel(MACHINES_FILE, sheet_name=SHEET)
    except Exception:
        df = pd.DataFrame()
else:
    df = pd.DataFrame()

existing_ids = set()
if not df.empty and 'id' in df.columns:
    existing_ids = set(str(x) for x in df['id'].dropna().tolist())

added = []
for m in surface_machines.SURFACE_MACHINES:
    mid = str(m.get('id'))
    if mid not in existing_ids:
        # normalize keys to DataFrame columns
        added.append(m)

if added:
    # backup existing file
    if os.path.exists(MACHINES_FILE):
        ts = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
        bak = MACHINES_FILE + f'.bak.{ts}'
        try:
            import shutil
            shutil.copy2(MACHINES_FILE, bak)
            print('Backup written to', bak)
        except Exception as e:
            print('Failed to write backup:', e)
    # append and write
    try:
        add_df = pd.DataFrame(added)
        if df.empty:
            out = add_df
        else:
            out = pd.concat([df, add_df], ignore_index=True, sort=False)
        # ensure columns exist
        out.to_excel(MACHINES_FILE, sheet_name=SHEET, index=False)
        print('WROTE:', MACHINES_FILE)
    except Exception as e:
        print('Failed to write machines file:', e)
else:
    print('No new default machines to add')
