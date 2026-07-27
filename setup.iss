[Setup]
AppId={{92D43B9E-C9F5-47D4-8061-980127CDDAD5}
AppName=Maven Downloader
AppVersion=1.7
AppVerName=Maven Downloader v1.7
AppPublisher=SayMaven
AppPublisherURL=https://github.com/SayMaven/mavdown
AppSupportURL=https://github.com/SayMaven/mavdown/issues
AppCopyright=Copyright (C) 2026 SayMaven
DefaultDirName={autopf}\Maven Downloader
DefaultGroupName=Maven Downloader
UninstallDisplayIcon={app}\mavdown.exe
UninstallDisplayName=Maven Downloader
Compression=lzma2
SolidCompression=yes
OutputDir=Output
OutputBaseFilename=MavenDownloader_Setup_v1.7
SetupIconFile=assets\waifu_icon.ico
; Gambar wizard installer 
WizardImageFile=assets\installer_banner.png   
WizardSmallImageFile=assets\installer_icon.png
WizardStyle=modern
MinVersion=10.0
PrivilegesRequired=admin

; Metadata file .exe installer
VersionInfoVersion=1.7.0.0
VersionInfoCompany=SayMaven
VersionInfoDescription=Maven Downloader Setup
VersionInfoProductName=Maven Downloader
VersionInfoProductVersion=1.7.0.0
VersionInfoCopyright=Copyright (C) 2026 SayMaven

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "dist\mavdown.dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Maven Downloader"; Filename: "{app}\mavdown.exe"
Name: "{group}\Uninstall Maven Downloader"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Maven Downloader"; Filename: "{app}\mavdown.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Run]
Filename: "{app}\mavdown.exe"; Description: "Launch Maven Downloader"; Flags: nowait postinstall skipifsilent
