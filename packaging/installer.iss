; Droid Commander installer (Inno Setup 6). Built by packaging\build.ps1 from dist\DroidCommander.
; Per-user install: no administrator rights needed.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppName "Droid Commander"
#define AppExe "DroidCommander.exe"

[Setup]
AppId={{6F1C2B7E-4D3A-4E8B-9A51-D20C0DA7A11E}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Droid Commander (unofficial fan tool)
AppComments=Voice-controlled astromech droid for FreeSpace Open / Fate of the Galaxy
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=DroidCommander-Setup-{#AppVersion}
SetupIconFile=droid.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"

[CustomMessages]
english.LaunchApp=Launch Droid Commander
italian.LaunchApp=Avvia Droid Commander
english.Manual=Droid Commander User Manual
italian.Manual=Manuale di Droid Commander
english.ReadMe=Droid Commander Read Me
italian.ReadMe=Droid Commander Leggimi
english.OpenManual=Open the user manual
italian.OpenManual=Apri il manuale utente
english.RemoveData=Also delete your Droid Commander settings, commands and voices?%n%n(%1)%n%nChoose No to keep them for a future installation.%n%nNote: if you installed the game link, remove it first from the Events tab (it lives in the game's mod folder).
italian.RemoveData=Eliminare anche impostazioni, comandi e voci di Droid Commander?%n%n(%1)%n%nScegli No per conservarli per una futura installazione.%n%nNota: se hai installato il collegamento con il gioco, toglilo prima dalla scheda Events (si trova nella cartella della mod).

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\DroidCommander\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
; for players: the user manual and a short read-me (plain text, opens in Notepad)
Source: "..\docs\DroidCommander_User_Manual.pdf"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README_USERS.md"; DestDir: "{app}"; DestName: "README.txt"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autoprograms}\{cm:Manual}"; Filename: "{app}\DroidCommander_User_Manual.pdf"
Name: "{autoprograms}\{cm:ReadMe}"; Filename: "{app}\README.txt"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchApp}"; Flags: nowait postinstall skipifsilent
Filename: "{app}\DroidCommander_User_Manual.pdf"; Description: "{cm:OpenManual}"; Flags: shellexec nowait postinstall skipifsilent unchecked

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{userappdata}\DroidCommander');
    if DirExists(DataDir) and not UninstallSilent then
      if MsgBox(FmtMessage(CustomMessage('RemoveData'), [DataDir]), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
