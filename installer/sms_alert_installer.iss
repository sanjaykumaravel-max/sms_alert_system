[Setup]
AppName=SMS Alert App
AppVersion=1.0
DefaultDirName={pf}\SMS Alert App
DefaultGroupName=SMS Alert App
OutputBaseFilename=SMSAlertInstaller
Compression=lzma
SolidCompression=yes

[Files]
; Adjust Source path if you change --name in spec or output
Source: "dist\sms_alert_app\sms_alert_app.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\sms_alert_app\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs

[Icons]
Name: "{group}\SMS Alert App"; Filename: "{app}\sms_alert_app.exe"; IconFilename: "{app}\assets\icons\app.ico"

[Run]
Filename: "{app}\sms_alert_app.exe"; Description: "Launch SMS Alert App"; Flags: nowait postinstall skipifsilent
