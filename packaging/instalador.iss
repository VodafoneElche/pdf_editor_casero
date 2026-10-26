; Instalador de PDF Casero (Inno Setup 6).
; Se compila después de PyInstaller:  iscc /DVersion=0.1.0 packaging\instalador.iss
; Resultado: packaging\salida\PDFCasero-Instalador-<versión>.exe

#ifndef Version
  #define Version "0.1.0"
#endif
#define Nombre "PDF Casero"
#define Exe "PDFCasero.exe"

[Setup]
AppId={{E14513AA-93E1-46D7-8FF1-50121DBD245B}
AppName={#Nombre}
AppVersion={#Version}
AppVerName={#Nombre} {#Version}
AppPublisher=PDF Casero
DefaultDirName={autopf}\{#Nombre}
DefaultGroupName={#Nombre}
DisableProgramGroupPage=yes
; Por defecto se instala solo para el usuario actual (no pide permiso de administrador);
; el instalador deja elegir "para todos los usuarios".
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=salida
OutputBaseFilename=PDFCasero-Instalador-{#Version}
SetupIconFile=icono.ico
UninstallDisplayIcon={app}\{#Exe}
UninstallDisplayName={#Nombre}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ChangesAssociations=yes
CloseApplications=yes

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
es.Asociar=Usar {#Nombre} para abrir los archivos PDF (se puede cambiar luego en Aplicaciones predeterminadas)
en.Asociar=Use {#Nombre} to open PDF files (can be changed later in Default apps)
es.Abrir=Abrir con {#Nombre}
en.Abrir=Open with {#Nombre}

[Tasks]
Name: "escritorio"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "asociar"; Description: "{cm:Asociar}"; Flags: unchecked

[Files]
Source: "..\dist\PDFCasero\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#Nombre}"; Filename: "{app}\{#Exe}"
Name: "{autodesktop}\{#Nombre}"; Filename: "{app}\{#Exe}"; Tasks: escritorio

[Registry]
; Tipo de archivo propio para los PDF
Root: HKA; Subkey: "Software\Classes\PDFCasero.pdf"; ValueType: string; ValueData: "Documento PDF"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\PDFCasero.pdf\DefaultIcon"; ValueType: string; ValueData: "{app}\{#Exe},0"
Root: HKA; Subkey: "Software\Classes\PDFCasero.pdf\shell\open"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#Nombre}"
Root: HKA; Subkey: "Software\Classes\PDFCasero.pdf\shell\open\command"; ValueType: string; ValueData: """{app}\{#Exe}"" ""%1"""
; Aparece en "Abrir con" para los .pdf
Root: HKA; Subkey: "Software\Classes\.pdf\OpenWithProgids"; ValueType: string; ValueName: "PDFCasero.pdf"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\{#Exe}\SupportedTypes"; ValueType: string; ValueName: ".pdf"; ValueData: ""; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Applications\{#Exe}\shell\open\command"; ValueType: string; ValueData: """{app}\{#Exe}"" ""%1"""
; Aparece en Configuración > Aplicaciones predeterminadas
Root: HKA; Subkey: "Software\PDFCasero\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "{#Nombre}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\PDFCasero\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "Leer, editar, dibujar y rellenar PDF"
Root: HKA; Subkey: "Software\PDFCasero\Capabilities\FileAssociations"; ValueType: string; ValueName: ".pdf"; ValueData: "PDFCasero.pdf"
Root: HKA; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "PDFCasero"; ValueData: "Software\PDFCasero\Capabilities"; Flags: uninsdeletevalue
; Solo si se marca la casilla: abrir los PDF con PDF Casero (en Windows 10/11 puede que el sistema pregunte una vez)
Root: HKA; Subkey: "Software\Classes\.pdf"; ValueType: string; ValueData: "PDFCasero.pdf"; Tasks: asociar; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#Exe}"; Description: "{cm:LaunchProgram,{#Nombre}}"; Flags: nowait postinstall skipifsilent
