#ifndef AppVersion
  #error AppVersion must be supplied by tools/build_installer.py
#endif
#ifndef AppExe
  #define AppExe "..\dist\Nexo.exe"
#endif

[Setup]
AppId={{164947D3-507E-43B7-AC53-AB298BD12EE6}
AppName=Nexo
AppVersion={#AppVersion}
AppPublisher=Aston (Astonto)
AppPublisherURL=https://github.com/Astonto/Nexo
AppSupportURL=https://github.com/Astonto/Nexo/issues
AppUpdatesURL=https://github.com/Astonto/Nexo/releases/latest
DefaultDirName={autopf}\Nexo
DefaultGroupName=Nexo
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist\release
OutputBaseFilename=Nexo-{#AppVersion}-windows-x64-setup
SetupIconFile=..\resources\nexo.ico
UninstallDisplayIcon={app}\Nexo.exe
UninstallDisplayName=Nexo
LicenseFile=..\LICENSE
WizardStyle=modern
Compression=lzma2/fast
SolidCompression=yes
CloseApplications=no
RestartApplications=no
AppMutex=Nexo.SetupGuard
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#AppExe}"; DestDir: "{app}"; DestName: "Nexo.exe"; Flags: ignoreversion
Source: "nexo-installed"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\THIRD_PARTY.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\docs\images\home.png"; DestDir: "{app}\docs\images"; Flags: ignoreversion
Source: "..\resources\licenses\*"; DestDir: "{app}\licenses"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\resources\Inter-OFL.txt"; DestDir: "{app}\licenses"; Flags: ignoreversion
Source: "Inno-LICENSE.txt"; DestDir: "{app}\licenses\InnoSetup"; Flags: ignoreversion

[Icons]
Name: "{group}\Nexo"; Filename: "{app}\Nexo.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\Nexo"; Filename: "{app}\Nexo.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\Nexo.exe"; Description: "{cm:LaunchProgram,Nexo}"; Flags: nowait postinstall skipifsilent runasoriginaluser
