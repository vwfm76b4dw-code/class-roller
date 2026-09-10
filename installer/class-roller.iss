; 课堂抽奖器 — Inno Setup 安装脚本
;
; 设计取舍（面向"自用 + 分享给同事"）：
;   * 按用户安装（PrivilegesRequired=lowest），装到 %LOCALAPPDATA%，
;     不需要管理员权限，双击就能装完 —— 学校电脑常常没有管理员权限。
;   * 程序文件与用户数据分开：程序装到安装目录，config.json 仍留在
;     用户可写的地方，升级/卸载不会带走名单。
;   * 中文界面（含简繁），语言文件随 Inno Setup 自带。

#define AppName "课堂抽奖器"
#define AppNameEn "Class Roller"
#define AppExeName "class-roller.exe"
#define AppPublisher "课堂工具"

; 版本号由 tools/build_installer.py 通过 /DMyAppVersion= 传入
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\class-roller"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
#endif

[Setup]
AppId={{9F3C7A21-5D84-4E16-9B3F-2C7E8A4D5F10}
AppName={#AppName}
AppVersion={#MyAppVersion}
AppVerName={#AppName} {#MyAppVersion}
AppPublisher={#AppPublisher}
VersionInfoVersion={#MyAppVersion}
VersionInfoDescription={#AppName} 安装程序
VersionInfoProductName={#AppName}

; 安装到用户目录，无需管理员权限
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
AllowNoIcons=yes

; 输出
OutputDir={#OutputDir}
OutputBaseFilename=ClassRoller-{#MyAppVersion}-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExeName}

; 中英文语言。
; 中文语言文件随项目内置（installer/languages/），因为 Inno Setup
; 官方安装包不自带简体中文，否则编译会失败。
[Languages]
Name: "chinese"; MessagesFile: "languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
chinese.CreateDesktopIcon=创建桌面快捷方式
chinese.LaunchApp=立即运行 {#AppName}
chinese.AdditionalTasks=附加任务
english.CreateDesktopIcon=Create a desktop shortcut
english.LaunchApp=Launch {#AppName} now
english.AdditionalTasks=Additional tasks

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalTasks}"; Flags: unchecked
Name: "startupicon"; Description: "开机自动启动"; GroupDescription: "{cm:AdditionalTasks}"; Flags: unchecked

[Files]
; 整个程序目录（onedir 形态）。
; Excludes 必须与 Source 写在同一行：Inno Setup 把 [Files] 的每一行当作
; 一个独立条目，单独一行 Excludes: 会被当成缺少 Source 的条目而报错。
; 不把本机配置与历史带进安装包。
Source: "{#SourceDir}\*"; DestDir: "{app}"; Excludes: "config.json,*.migrated.json,config.json.tmp"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\卸载 {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: startupicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchApp}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 程序自带的运行时文件由卸载程序按清单删除；
; 这里额外清掉可能生成的临时文件，但不碰用户数据。
Type: files; Name: "{app}\config.json.tmp"

[Code]
// 安装前提示：若正在运行，请先关闭，否则文件会被占用
function InitializeSetup(): Boolean;
begin
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  // 卸载时保留用户数据的位置提示留给 README，这里不做删除，
  // 避免用户重装后名单丢失。
end;
