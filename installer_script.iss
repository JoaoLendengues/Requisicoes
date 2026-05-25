; Inno Setup — Requisições Pinheiro
; Uso manual:
;   ISCC.exe /DMyAppVersion=1.0.0 /DBuildRoot=dist\requisicoes installer_script.iss
; O GitHub Actions passa essas variáveis automaticamente.

#define MyAppName      "Requisições App"
#define MyAppPublisher "Ferragens Pinheiro"
#define MyAppURL       "https://github.com/JoaoLendengues/Requisicoes"

#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif

#ifndef BuildRoot
  #define BuildRoot "dist\requisicoes"
#endif

[Setup]
AppId={{F3A8C1D2-B456-7890-CDEF-123456789ABC}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}

; Instala em AppData\Local do usuário — sem necessidade de admin
DefaultDirName={localappdata}\Programs\Requisicoes
DefaultGroupName={#MyAppName}
UsePreviousAppDir=yes
PrivilegesRequired=lowest

AllowNoIcons=yes
OutputDir=installer_output
OutputBaseFilename=Requisicoes_Setup_v{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=client\assets\icons\icon_setup.ico

UninstallDisplayIcon={app}\requisicoes.exe
CloseApplications=force
RestartApplications=no

[Languages]
Name: "portuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar ícone na Área de Trabalho"; GroupDescription: "Ícones adicionais:"

[InstallDelete]
; Limpa _internal antes de instalar — garante que binários antigos sejam removidos
Type: filesandordirs; Name: "{app}\_internal"

[Files]
; Executável principal
Source: "{#BuildRoot}\requisicoes.exe"; DestDir: "{app}"; Flags: ignoreversion

; Todos os arquivos internos (PySide6, libs, assets, etc.)
Source: "{#BuildRoot}\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs

; Configurações padrão — só copia se o arquivo ainda não existir (preserva configurações do usuário)
Source: "{#BuildRoot}\_internal\client\settings.json"; DestDir: "{app}\_internal\client"; Flags: ignoreversion onlyifdoesntexist uninsneveruninstall skipifsourcedoesntexist

[Icons]
Name: "{group}\Requisições App";       Filename: "{app}\requisicoes.exe"
Name: "{autodesktop}\Requisições App"; Filename: "{app}\requisicoes.exe"; Tasks: desktopicon
Name: "{group}\Desinstalar Requisições App"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\requisicoes.exe"; Description: "Executar Requisições agora"; Flags: postinstall nowait skipifsilent
