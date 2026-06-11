; Inno Setup script — wraps the PyInstaller one-folder build (dist\GerberDiff\)
; into a per-user installer with Start-menu + optional desktop shortcuts.
;   compile:  iscc /DMyAppVersion=0.10.0 GerberDiffSetup.iss
; CI passes the git tag as MyAppVersion.

#ifndef MyAppVersion
  #define MyAppVersion "0.10.0"
#endif

[Setup]
AppName=Gerber Diff
AppVersion={#MyAppVersion}
AppPublisher=Simon Maddison (Cimos)
AppPublisherURL=https://github.com/Cimos/Gerber-Diff-Tool
DefaultDirName={autopf}\GerberDiff
DefaultGroupName=Gerber Diff
UninstallDisplayIcon={app}\GerberDiff.exe
OutputDir=Output
OutputBaseFilename=GerberDiffSetup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "dist\GerberDiff\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Gerber Diff"; Filename: "{app}\GerberDiff.exe"
Name: "{group}\Uninstall Gerber Diff"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Gerber Diff"; Filename: "{app}\GerberDiff.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\GerberDiff.exe"; Description: "Launch Gerber Diff"; Flags: nowait postinstall skipifsilent
