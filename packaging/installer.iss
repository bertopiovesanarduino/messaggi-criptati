; Script Inno Setup per Creazione Installer Windows "SecureChat_Setup_v1.0.exe"
; ==============================================================================

#define MyAppName "SecureChat E2EE"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "E2EE Security Lab"
#define MyAppExeName "SecureChatE2EE.exe"

[Setup]
AppId={{5A8D2A1C-9E4B-4E38-9B7C-8A9F0D1E2C3B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=..\dist_installer
OutputBaseFilename=SecureChat_Setup_v1.0
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startup"; Description: "Avvia automaticamente SecureChat all'accesso di Windows (in background)"; GroupDescription: "Integrazione di Sistema:"; Flags: unchecked

[Files]
; Copia tutti i file generati dalla compilazione PyInstaller
Source: "..\dist\SecureChatE2EE\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; NOTA: Non usare 'Flags: ignoreversion' sui file di sistema condivisi

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; Se l'utente seleziona la task di avvio automatico
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
