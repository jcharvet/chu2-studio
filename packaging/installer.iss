; The Windows installer for CHU 2 Studio. Built by packaging/build_exe.py after the
; .exe, with:  ISCC.exe /DMyAppVersion=0.2.0 packaging\installer.iss
;
; Per-user on purpose: it installs under the user's own folder, so Windows never asks
; for an administrator. It also solves the problem that forces the zip's mark-clearing
; hack - files written by an installer do not carry Windows' "came from the internet"
; mark, so .NET loads Python.Runtime.dll without help.

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#define MyAppName "CHU 2 Studio"
#define MyAppExe "CHU2Studio.exe"

[Setup]
AppId={{9E0E7F4B-2C1A-4E3D-9A55-CH2STUDIO0001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Jerome Charvet
AppPublisherURL=https://github.com/jcharvet/chu2-studio
AppSupportURL=https://github.com/jcharvet/chu2-studio/issues
DefaultDirName={autopf}\CHU2Studio
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=CHU2Studio-{#MyAppVersion}-setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#MyAppExe}
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
LicenseFile=..\LICENSE

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a shortcut on the desktop"; Flags: unchecked
Name: "startup"; Description: "Start CHU 2 Studio when Windows starts (it opens in the tray, so the earphones never click)"

[Files]
Source: "..\dist\CHU2Studio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Registry]
; The same entry the app's own "start with Windows" switch writes, so the two agree.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
    ValueName: "CHU 2 Studio"; ValueData: """{app}\{#MyAppExe}"""; \
    Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "Open CHU 2 Studio"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Presets, settings and the backup of the earphones' original EQ live in
; %APPDATA%\CHU2Studio and are deliberately left behind.
