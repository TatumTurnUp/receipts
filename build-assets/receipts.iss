; Inno Setup script for the Receipts Windows installer.
; Built by .github/workflows/release.yml, which passes /DAppVersion and places
; MicrosoftEdgeWebview2Setup.exe in this folder first.

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
; Only extracted, and only when the check below says it is needed.
Source: "MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; \
  Flags: deleteafterinstall; Check: WebView2Missing

[Icons]
Name: "{group}\Receipts"; Filename: "{app}\Receipts.exe"
Name: "{autodesktop}\Receipts"; Filename: "{app}\Receipts.exe"; Tasks: desktopicon

[Run]
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; \
  StatusMsg: "Installing a component Receipts needs..."; \
  Check: WebView2Missing; Flags: waituntilterminated
Filename: "{app}\Receipts.exe"; Description: "Open Receipts"; \
  Flags: nowait postinstall skipifsilent

[Code]
// Receipts draws its window with the Edge WebView2 runtime. It ships with
// current Windows 11 but is missing on plenty of Windows 10 machines — and
// when it is missing pywebview does not fail, it quietly falls back to the old
// Internet Explorer engine, which cannot run the app's JavaScript. The user
// gets a blank white window and no error. Installing the runtime here is the
// difference between "it just works" and a bug report nobody can diagnose.
function WebView2Missing: Boolean;
begin
  Result := not RegKeyExists(HKLM,
      'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}')
    and not RegKeyExists(HKCU,
      'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}');
end;

; Note there is deliberately no [UninstallDelete] for the archive. Uninstalling
; Receipts must never remove someone's data — it lives in %LOCALAPPDATA%\Receipts
; and is left behind on purpose, so reinstalling picks up where they left off.
