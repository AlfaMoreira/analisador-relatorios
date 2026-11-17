#ifndef AppVersion
  #error AppVersion deve ser informado pelo processo de compilacao.
#endif
#ifndef PackageDir
  #error PackageDir deve apontar para a pasta RevisorCelacanto compilada.
#endif
#ifndef OutputPath
  #error OutputPath deve apontar para a pasta de distribuicao.
#endif

[Setup]
AppId={{14F85646-1431-4422-B403-AB32632C881E}
AppName=Revisor Celacanto
AppVersion={#AppVersion}
AppPublisher=Celacanto
AppPublisherURL=https://github.com/AlfaMoreira/analisador-relatorios
AppSupportURL=https://github.com/AlfaMoreira/analisador-relatorios/issues
AppUpdatesURL=https://github.com/AlfaMoreira/analisador-relatorios/releases
DefaultDirName={localappdata}\Programs\Celacanto\Revisor
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputPath}
OutputBaseFilename=RevisorCelacanto-Instalador
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\RevisorCelacanto.exe
CloseApplications=yes
RestartApplications=no
SetupLogging=yes

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na area de trabalho"; GroupDescription: "Atalhos:"; Flags: unchecked

[Files]
Source: "{#PackageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Revisor Celacanto"; Filename: "{app}\RevisorCelacanto.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\Revisor Celacanto"; Filename: "{app}\RevisorCelacanto.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\RevisorCelacanto.exe"; Description: "Abrir Revisor Celacanto"; Flags: nowait postinstall skipifsilent

; A biblioteca fica em {localappdata}\Celacanto\AnalisadorRelatorios.
; Nao incluir UninstallDelete ou remocao recursiva de dados do usuario.
