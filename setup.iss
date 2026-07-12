[Setup]
AppName=Maven Downloader
AppVersion=1.5
AppPublisher=SayMaven
DefaultDirName={autopf}\Maven Downloader
DefaultGroupName=Maven Downloader
UninstallDisplayIcon={app}\mavdown.exe
Compression=lzma2
SolidCompression=yes
OutputDir=Output
OutputBaseFilename=MavenDownloader_Setup_v1.5
SetupIconFile=assets\waifu_icon.ico

[Files]
Source: "dist\mavdown.dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Maven Downloader"; Filename: "{app}\mavdown.exe"
Name: "{autodesktop}\Maven Downloader"; Filename: "{app}\mavdown.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked
