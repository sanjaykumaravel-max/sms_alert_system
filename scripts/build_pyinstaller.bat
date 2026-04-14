@echo off
python -m pip install --upgrade pip
pip install -r requirements-prod.txt
pip install pyinstaller

rem Build using the spec which now includes .env in datas (will be copied to dist\sms_alert_app\)
pyinstaller --clean --noconfirm pyinstaller.spec

rem If you prefer a one-file bundle instead, use the following (note: .env will be embedded,
rem typically extracted to a temp folder at runtime; the app also checks next to the exe):
rem pyinstaller --onefile --name sms_alert_app --add-data ".env;." --add-data "src/data;data" --add-data "assets;assets" src\main.py