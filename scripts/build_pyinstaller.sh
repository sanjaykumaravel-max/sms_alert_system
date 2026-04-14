#!/usr/bin/env bash
set -e
python -m pip install --upgrade pip
pip install -r requirements-prod.txt
pip install pyinstaller

# Create a one-file bundle. Adjust --add-data paths as needed for Windows vs Linux.
pyinstaller --onefile --name sms_alert_app --add-data "data:./data" src/main.py

echo "Built dist/sms_alert_app (check dist/ folder)"
