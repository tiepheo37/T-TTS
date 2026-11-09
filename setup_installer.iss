; Inno Setup Script cho T-TTS v3.0.1 Desktop Offline
; Tác giả: Nguyễn Văn Tiệp
; Công nghệ: VieNeu-TTS v3 Turbo ONNX CPU (100% Offline, Native PySide6)

[Setup]
AppName=T-TTS v3.0.1 — Hệ Thống Trợ Lý Giọng Nói Quân Đội
AppVersion=3.0.1
AppVerName=T-TTS v3.0.1 (Tác giả: Nguyễn Văn Tiệp)
AppPublisher=Nguyễn Văn Tiệp
AppComments=Phần mềm chuyển văn bản thành giọng nói tiếng Việt Native Desktop 100% Offline. Tác giả: Nguyễn Văn Tiệp. Công nghệ: VieNeu-TTS v3 Turbo ONNX CPU.
DefaultDirName={autopf}\T-TTS
DefaultGroupName=T-TTS
UninstallDisplayIcon={app}\T-TTS.exe
SetupIconFile=app_icon.ico
Compression=lzma2/max
SolidCompression=yes
CloseApplications=yes
RestartApplications=yes
OutputDir=dist
OutputBaseFilename=T-TTS_Setup_v3.0.1_Offline
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
InfoBeforeFile=setup_intro.txt

[Dirs]
Name: "{app}\output"; Permissions: users-full
Name: "{app}\data"; Permissions: users-full

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Core binary files, libraries and icon
Source: "release_test\T-TTS_v3.0.1_Desktop\T-TTS.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "release_test\T-TTS_v3.0.1_Desktop\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "release_test\T-TTS_v3.0.1_Desktop\models\*"; DestDir: "{app}\models"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "release_test\T-TTS_v3.0.1_Desktop\gui\*"; DestDir: "{app}\gui"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "release_test\T-TTS_v3.0.1_Desktop\HUONG_DAN_SU_DUNG.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "release_test\T-TTS_v3.0.1_Desktop\CHAN_DOAN_VA_KHAC_PHUC_SU_CO.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "release_test\T-TTS_v3.0.1_Desktop\portable.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "app_icon.ico"; DestDir: "{app}"; Flags: ignoreversion

; User data folders: preserve on uninstall and never overwrite on upgrade
Source: "release_test\T-TTS_v3.0.1_Desktop\data\*"; DestDir: "{app}\data"; Flags: ignoreversion recursesubdirs createallsubdirs uninsneveruninstall onlyifdoesntexist; Permissions: users-full
Source: "release_test\T-TTS_v3.0.1_Desktop\output\*"; DestDir: "{app}\output"; Flags: ignoreversion recursesubdirs createallsubdirs uninsneveruninstall onlyifdoesntexist; Permissions: users-full

[Icons]
Name: "{group}\T-TTS v3.0.1"; Filename: "{app}\T-TTS.exe"; IconFilename: "{app}\T-TTS.exe"
Name: "{group}\Thư mục Âm thanh (Output)"; Filename: "{app}\output"
Name: "{group}\Hướng Dẫn Sử Dụng"; Filename: "{app}\HUONG_DAN_SU_DUNG.txt"
Name: "{group}\Gỡ cài đặt T-TTS"; Filename: "{uninstallexe}"
Name: "{autodesktop}\T-TTS v3.0.1"; Filename: "{app}\T-TTS.exe"; Tasks: desktopicon; IconFilename: "{app}\T-TTS.exe"
Name: "{autodesktop}\Thư mục Âm thanh T-TTS"; Filename: "{app}\output"; Tasks: desktopicon

[Run]
Filename: "{app}\T-TTS.exe"; Description: "{cm:LaunchProgram,T-TTS v3.0.1 — Hệ Thống Trợ Lý Giọng Nói Quân Đội}"; Flags: nowait postinstall skipifsilent
