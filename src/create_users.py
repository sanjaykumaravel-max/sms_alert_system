import pandas as pd
from auth import hash_password
import os

users = [
    {
        "username": "admin",
        "password_hash": hash_password("admin123"),
        "role": "Admin",
        "name": "System Admin"
    },
    {
        "username": "supervisor",
        "password_hash": hash_password("sup123"),
        "role": "Supervisor",
        "name": "Shift Supervisor"
    },
    {
        "username": "operator",
        "password_hash": hash_password("op123"),
        "role": "Operator",
        "name": "Machine Operator"
    }
]

df = pd.DataFrame(users)

# ensure data dir exists (relative to project root)
data_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "data"))
os.makedirs(data_dir, exist_ok=True)

out_path = os.path.join(data_dir, "users.xlsx")
df.to_excel(out_path, sheet_name="Users", index=False)

print("Users created successfully.")
