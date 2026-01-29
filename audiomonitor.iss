; ============================================================
; Audio Loss Monitor - Full Offline Installer (Standalone Python)
; ============================================================

#define MyAppName "Audio Loss Monitor"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "My Company, Inc."
#define MyAppURL "https://www.example.com/"
#define MyAppExeName "start_app.bat"

[Setup]
; ---------------------------------------------------------------
; General Setup
; ---------------------------------------------------------------
AppId={{924EC670-634E-4B0B-96A2-729242236D7E}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=.
OutputBaseFilename=AudioLossMonitorSetup
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "arabic"; MessagesFile: "compiler:Languages\Arabic.isl"

[Tasks]
; ---------------------------------------------------------------
; Optional installation tasks
; ---------------------------------------------------------------
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; ---------------------------------------------------------------
; Application Files (Relative Paths)
; ---------------------------------------------------------------
Source: "start_app.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "monitor_audio.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "audio_utils.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "config.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: ".env"; DestDir: "{app}"; Flags: ignoreversion
Source: "python-embed\*"; DestDir: "{app}\python-embed"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; ---------------------------------------------------------------
; Desktop and Start Menu Shortcuts
; ---------------------------------------------------------------
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; ---------------------------------------------------------------
; 1. Initialize Python environment (ensure pip and install deps)
; ---------------------------------------------------------------
Filename: "{app}\python-embed\python.exe"; Parameters: "-m ensurepip"; Flags: runhidden waituntilterminated
Filename: "{app}\python-embed\python.exe"; Parameters: "-m pip install --upgrade pip"; Flags: runhidden waituntilterminated
Filename: "{app}\python-embed\python.exe"; Parameters: "-m pip install -r ""{app}\requirements.txt"""; Flags: runhidden waituntilterminated

; ---------------------------------------------------------------
; 2. Launch App
; ---------------------------------------------------------------
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; WorkingDir: "{app}"; Flags: shellexec postinstall skipifsilent nowait

[Code]

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    MsgBox('Installing embedded Python and dependencies... This may take a few minutes.', mbInformation, MB_OK);
  end;
end;

procedure CurStepFinished(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    MsgBox('Installation complete! You can launch Audio Loss Monitor from your desktop shortcut.', mbInformation, MB_OK);
  end;
end;
