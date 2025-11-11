; ERPlora Hub - Inno Setup Script
; Crea instalador para Windows con autostart

#define MyAppName "ERPlora Hub"
#define MyAppVersion "0.8.0"
#define MyAppPublisher "CPOS Team"
#define MyAppURL "https://cpos.app"
#define MyAppExeName "main.exe"

[Setup]
; Basic information
AppId={{E8F2A3B4-5C6D-7E8F-9A0B-1C2D3E4F5G6H}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/support
AppUpdatesURL={#MyAppURL}/downloads
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=..\..\LICENSE
OutputDir=..\..\dist
OutputBaseFilename=CPOS-Hub-{#MyAppVersion}-Setup
SetupIconFile=..\..\assets\app_icon.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64

; Uninstall settings
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "startmenu"; Description: "Crear acceso directo en el Men\u00fa Inicio"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce
Name: "autostart"; Description: "Iniciar autom\u00e1ticamente con Windows"; GroupDescription: "Opciones de inicio:"; Flags: checkedonce

[Files]
; Copiar toda la aplicación
Source: "..\..\dist\main\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Men\u00fa Inicio
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startmenu
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"; Tasks: startmenu

; Escritorio
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

; Autostart - Carpeta Inicio de Windows
Name: "{autostartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: autostart

[Registry]
; Añadir a "Programas y características"
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{{E8F2A3B4-5C6D-7E8F-9A0B-1C2D3E4F5G6H}_is1"; ValueType: string; ValueName: "DisplayName"; ValueData: "{#MyAppName}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{{E8F2A3B4-5C6D-7E8F-9A0B-1C2D3E4F5G6H}_is1"; ValueType: string; ValueName: "DisplayVersion"; ValueData: "{#MyAppVersion}"
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{{E8F2A3B4-5C6D-7E8F-9A0B-1C2D3E4F5G6H}_is1"; ValueType: string; ValueName: "Publisher"; ValueData: "{#MyAppPublisher}"
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{{E8F2A3B4-5C6D-7E8F-9A0B-1C2D3E4F5G6H}_is1"; ValueType: string; ValueName: "URLInfoAbout"; ValueData: "{#MyAppURL}"
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{{E8F2A3B4-5C6D-7E8F-9A0B-1C2D3E4F5G6H}_is1"; ValueType: string; ValueName: "DisplayIcon"; ValueData: "{app}\{#MyAppExeName}"

; Registro de aplicación
Root: HKLM; Subkey: "Software\CPOS\Hub"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\CPOS\Hub"; ValueType: string; ValueName: "Version"; ValueData: "{#MyAppVersion}"

[Run]
; Opción de ejecutar después de instalar
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Detener la aplicación antes de desinstalar (si está corriendo)
Filename: "{cmd}"; Parameters: "/C taskkill /F /IM main.exe"; Flags: runhidden; RunOnceId: "KillApp"

[Code]
// Verificar si la aplicación está corriendo
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
  Running: Boolean;
begin
  Result := True;
  Running := False;

  // Intentar detectar si la app está corriendo
  if Exec('tasklist', '/FI "IMAGENAME eq main.exe"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    if ResultCode = 0 then
    begin
      Running := True;
    end;
  end;

  if Running then
  begin
    if MsgBox('ERPlora Hub parece estar ejecutándose. ¿Desea cerrarlo para continuar con la instalación?', mbConfirmation, MB_YESNO) = IDYES then
    begin
      Exec('taskkill', '/F /IM main.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
      Sleep(1000); // Esperar 1 segundo
      Result := True;
    end
    else
    begin
      Result := False;
    end;
  end;
end;

// Mostrar mensaje después de la instalación
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // Aquí se podría añadir lógica adicional post-instalación
  end;
end;
