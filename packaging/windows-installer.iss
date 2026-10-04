#ifndef AppVersion
  #define AppVersion "0.9.2"
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
Filename: "{app}\RpaOrkestrAI.exe"; Description: "RpaOrkestrAI Studio'yu aç"; Flags: nowait postinstall skipifsilent; Check: not IsUpdate
Filename: "{app}\RpaOrkestrAI.exe"; Flags: nowait; Check: IsUpdate

[Code]
function OpenProcess(Access: LongWord; Inherit: BOOL; ProcessId: LongWord): THandle;
  external 'OpenProcess@kernel32.dll stdcall';
function WaitForSingleObject(Handle: THandle; Milliseconds: LongWord): LongWord;
  external 'WaitForSingleObject@kernel32.dll stdcall';
function CloseHandle(Handle: THandle): BOOL;
  external 'CloseHandle@kernel32.dll stdcall';

function IsUpdate(): Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount do
    if CompareText(ParamStr(I), '/RPAUPDATE') = 0 then
      Result := True;
end;

function PreviousAppExited(): Boolean;
var
  ProcessId: Integer;
  Handle: THandle;
begin
  Result := True;
  if not IsUpdate() then exit;
  ProcessId := StrToIntDef(ExpandConstant('{param:RPAPID|0}'), 0);
  if ProcessId <= 0 then begin
    Result := False;
    exit;
  end;
  Handle := OpenProcess($00100000, False, ProcessId);
  if Handle = 0 then begin
    { Only an absent process is safe; access denied does not mean it exited. }
    Result := DLLGetLastError = 87;
    exit;
  end;
  Result := WaitForSingleObject(Handle, 120000) = 0;
  CloseHandle(Handle);
end;

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

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  { Bilgisayar açılınca Studio'yu başlat: the login entry would point to a removed program. }
  if CurUninstallStep = usUninstall then
    RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'RpaOrkestrAI Studio');
end;

function InitializeSetup(): Boolean;
begin
  if not PreviousAppExited() then begin
    Result := False;
    MsgBox('Studio kapanmadığı için güncelleme ertelendi. Çalışmalarınızı kaydedip uygulamayı kapatın.', mbInformation, MB_OK);
    exit;
  end;
  Result := WebViewInstalled();
  if not Result then
    MsgBox('Microsoft Edge WebView2 Runtime gerekli. Önce BT ekibiniz üzerinden veya https://developer.microsoft.com/microsoft-edge/webview2 adresinden kurun, ardından kurulumu yeniden açın.', mbError, MB_OK);
end;
