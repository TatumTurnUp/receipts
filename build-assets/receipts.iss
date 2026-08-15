; Inno Setup script for the Receipts Windows installer.
; Built by .github/workflows/release.yml; VERSION is passed in with /DAppVersion.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{8E5C0F3A-7B41-4E2D-9C6A-RECEIPTS0001}
AppName=Receipts
AppVersion={#AppVersion}
AppPublisher=Tatum
DefaultDirName={autopf}\Receipts
DefaultGroupName=Receipts
; Per-user install: no admin prompt, which is one less scary dialog for
; someone who was told "just try my app".
PrivilegesRequired=lowest
OutputDir=..\installer
OutputBaseFilename=Receipts-Setup-{#AppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\Receipts.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\Receipts\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Receipts"; Filename: "{app}\Receipts.exe"
Name: "{autodesktop}\Receipts"; Filename: "{app}\Receipts.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Receipts.exe"; Description: "Open Receipts"; Flags: nowait postinstall skipifsilent

; Note there is no [UninstallDelete] for the archive. Uninstalling Receipts
; must never remove someone's data — it lives in %LOCALAPPDATA%\Receipts and
; is deliberately left behind, so reinstalling picks up exactly where they
; left off.
