#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{8B5DD476-E2DD-47E0-A45A-C09A31929DE4}
AppName=RpaOrkestrAI Studio
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\RpaOrkestrAI
DefaultGroupName=RpaOrkestrAI Studio
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\installer
OutputBaseFilename=RpaOrkestrAI-Setup-{#AppVersion}-Windows-x64
SetupIconFile=..\build\app-icon\studio.ico
UninstallDisplayIcon={app}\RpaOrkestrAI.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\dist\RpaOrkestrAI\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userdesktop}\RpaOrkestrAI Studio"; Filename: "{app}\RpaOrkestrAI.exe"
Name: "{userprograms}\RpaOrkestrAI Studio"; Filename: "{app}\RpaOrkestrAI.exe"

[Run]
Filename: "{app}\RpaOrkestrAI.exe"; Description: "RpaOrkestrAI Studio'yu aç"; Flags: nowait postinstall skipifsilent

[Code]
function WebViewInstalled(): Boolean;
var
  Version: String;
  Key: String;
begin
  Key := 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  Result := (RegQueryStringValue(HKLM32, Key, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0'));
  if not Result then
    Result := (RegQueryStringValue(HKCU, Key, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0'));
end;

function InitializeSetup(): Boolean;
begin
  Result := WebViewInstalled();
  if not Result then
    MsgBox('Microsoft Edge WebView2 Runtime gerekli. Önce BT ekibiniz üzerinden veya https://developer.microsoft.com/microsoft-edge/webview2 adresinden kurun, ardından kurulumu yeniden açın.', mbError, MB_OK);
end;
