;==============================================================================
; Inno Setup Script for Plate Guard — License Plate Recognition Desktop App
;
; Produces:  PlateRecognitionSetup.exe
;
; Pre-build steps (run before compiling this script):
;   1. pyinstaller plate_guard.spec
;   2. Verify that .\build\exe.win-amd64-3.14\PlateGuard\PlateGuard.exe exists
;   3. Place FFmpeg DLLs in .\installer\redist\ffmpeg\  (optional)
;   4. Place MSVC redist in .\installer\redist\vc_redist.x64.exe  (optional)
;
; Build with Inno Setup Compiler (command-line):
;   iscc installer\setup.iss
;==============================================================================

#define MyAppName "Plate Guard"
#define MyAppShortName "PlateGuard"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Plate Guard"
#define MyAppURL "https://github.com/your-org/plate-guard"
#define MyAppExeName "PlateGuard.exe"
#define MyAppAssocName "Plate Guard Data"

; --- Directories ---
#define BuildDir "..\build\exe.win-amd64-3.14\PlateGuard"
#define RedistDir "..\installer\redist"
#define OutputDir "..\dist"

[Setup]
; NOTE: The value of AppId uniquely identifies this application.
; Do not use the same AppId value in installers for other applications.
AppId={{B8F4C3A1-2D5E-4F7B-9C8A-1E3D5F7B9C0D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; --- Output ---
OutputDir={#OutputDir}
OutputBaseFilename=PlateRecognitionSetup
SetupIconFile=..\assets\icon.ico
Compression=lzma2/max
SolidCompression=yes

; --- Behaviour ---
DefaultDirName={autopf}\{#MyAppShortName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
UsePreviousAppDir=yes
UsePreviousGroup=yes
DisableProgramGroupPage=auto

; --- Version info ---
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=License Plate Recognition Desktop Application
VersionInfoTextCopyright=Copyright © 2026 {#MyAppPublisher}

; --- Restart ---
RestartIfNeededByRun=no
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

;==============================================================================
; Tasks
;==============================================================================

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: checkedonce
Name: "startup"; Description: "Launch Plate Guard on &Windows startup"; GroupDescription: "Startup options:"; Flags: checkedonce
Name: "ffmpeg"; Description: "Register FFmpeg codecs (recommended for video)" ; GroupDescription: "Additional components:"; Flags: checkedonce

;==============================================================================
; Files
;==============================================================================

[Files]

; --- Main application ---
Source: "{#BuildDir}\PlateGuard.exe";        DestDir: "{app}"; Flags: ignoreversion
Source: "{#BuildDir}\*";                      DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; --- FFmpeg redistributable DLLs (optional) ---
; Place ffmpeg.exe, ffprobe.exe, and required DLLs here.
; Download from https://ffmpeg.org/download.html (Windows builds by BtbN or gyan.dev)
Source: "{#RedistDir}\ffmpeg\*";              DestDir: "{app}\ffmpeg"; Flags: ignoreversion recursesubdirs; Tasks: ffmpeg

; --- Visual C++ Redistributable ---
; Download from https://aka.ms/vs/17/release/vc_redist.x64.exe
; This is required by OpenCV and PySide6 at runtime.
Source: "{#RedistDir}\vc_redist.x64.exe";     DestDir: "{tmp}"; Flags: deleteafterinstall; Check: IsWin64 and not VCRedistInstalled

; --- Create empty directories for runtime data ---
; The app creates these on first launch, but we pre-create them
; so the user can find them easily.
[Dirs]
Name: "{app}\logs";    Permissions: users-modify
Name: "{app}\media\snapshots"; Permissions: users-modify
Name: "{app}\media\clips";     Permissions: users-modify

;==============================================================================
; Runtime checks
;==============================================================================

[Code]

function VCRedistInstalled: Boolean;
var
  Installed: Cardinal;
begin
  Result := False;
  { Check for Visual C++ 2015-2022 Redistributable (x64) }
  if RegQueryDWordValue(
    HKLM,
    'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64',
    'Installed',
    Installed
  ) then
    Result := Installed = 1;
end;

function IsFFmpegAvailable: Boolean;
begin
  Result := FileExists(ExpandConstant('{app}\ffmpeg\ffmpeg.exe'));
end;

{------------------------------------------------------------------------------
  Initialize installer: check prerequisites
------------------------------------------------------------------------------}
function InitializeSetup: Boolean;
begin
  Result := True;

  { Check Windows version (Windows 10 1809+ or Server 2019+ recommended) }
  if not IsWin64 then
  begin
    MsgBox(
      'Plate Guard requires a 64-bit version of Windows 10 or later.',
      mbError,
      MB_OK
    );
    Result := False;
    Exit;
  end;
end;

{------------------------------------------------------------------------------
  After installation steps
------------------------------------------------------------------------------}
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    { Install VC++ Redist if we copied it }
    if IsWin64 and not VCRedistInstalled then
    begin
      if FileExists(ExpandConstant('{tmp}\vc_redist.x64.exe')) then
      begin
        if MsgBox(
          'Visual C++ Redistributable is required. Install it now?',
          mbConfirmation,
          MB_YESNO
        ) = IDYES then
        begin
          if not Exec(
            ExpandConstant('{tmp}\vc_redist.x64.exe'),
            '/quiet /norestart',
            '',
            SW_SHOW,
            ewWaitUntilTerminated,
            ResultCode
          ) then
          begin
            MsgBox(
              'Failed to install Visual C++ Redistributable. ' +
              'You may need to install it manually.',
              mbError,
              MB_OK
            );
          end;
        end;
      end;
    end;
  end;
end;

{------------------------------------------------------------------------------
  Uninstall cleanup
------------------------------------------------------------------------------}
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    { Ask whether to remove user data }
    if MsgBox(
      'Remove all application data (database, logs, captured media, settings)?',
      mbConfirmation,
      MB_YESNO or MB_DEFBUTTON2
    ) = IDYES then
    begin
      DelTree(ExpandConstant('{app}\logs'), True, True, True);
      DelTree(ExpandConstant('{app}\media'), True, True, True);
      { Also remove %APPDATA%\plate-guard if it exists }
      DelTree(
        ExpandConstant('{userappdata}\plate-guard'),
        True,
        True,
        True
      );
    end;
  end;
end;

;==============================================================================
; Shortcuts
;==============================================================================

[Icons]
Name: "{group}\{#MyAppName}";                       Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}";  Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}";                  Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

; --- Startup shortcut (runs on Windows logon) ---
Name: "{userstartup}\{#MyAppShortName}";             Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: startup

;==============================================================================
; Registry
;==============================================================================

[Registry]
; File association placeholder (can be enabled for .jpg/.mp4 association later)
; Root: HKA; Subkey: "Software\Classes\.lpr\OpenWithProgids"; ValueType: string; ValueName: "{#MyAppAssocName}"; Flags: uninsdeletevalue

; Application path for uninstall detection
Root: HKA; Subkey: "Software\{#MyAppPublisher}\{#MyAppShortName}"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey

;==============================================================================
; Run
;==============================================================================

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent shellexec
