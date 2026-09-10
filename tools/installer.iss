#define AppVersion "0.2.0"
[Setup]
AppId={{0C019C01-E185-4136-A617-6911EF6DBDAA}
AppName=KájovoKarty
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\KajovoKarty
DefaultGroupName=KájovoKarty
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\installer
OutputBaseFilename=KajovoKarty-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\KajovoKarty.exe
CloseApplications=yes
[Languages]
Name: "czech"; MessagesFile: "compiler:Languages\Czech.isl"
[Files]
Source: "..\dist\KajovoKarty\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{userprograms}\KájovoKarty"; Filename: "{app}\KajovoKarty.exe"
[Run]
Filename: "{app}\KajovoKarty.exe"; Description: "Spustit KájovoKarty"; Flags: nowait postinstall skipifsilent
