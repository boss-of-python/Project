; ============================================================
;  THANS - Inno Setup script (Windows installer)
;  Compiled by build_exe.bat when Inno Setup 6 is installed.
; ============================================================

#define MyAppName "THANS"
#define MyAppVersion "0.2.0"
#define MyAppPublisher "THANS"
#define MyAppExeName "THANS.exe"

[Setup]
; NOTE: AppId must stay the same across versions for upgrades to work.
AppId={{B7E5C1A2-9D3F-4E6A-8C11-3D9F2A7B4C55}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\THANS
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=THANS-Setup-{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; branded wizard + Start-menu/desktop icons (thans.ico ships in the repo)
SetupIconFile=..\..\installer\thans.ico
ArchitecturesInstallIn64BitMode=x64compatible
; Models may be up to ~500 MB - allow the temp dir to grow.
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; the executable
Source: "..\..\dist\THANS.exe"; DestDir: "{app}"; Flags: ignoreversion
; all offline models (STT + optional LLM)
Source: "..\..\models\*"; DestDir: "{app}\models"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
