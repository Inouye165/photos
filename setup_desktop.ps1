# LuminaPhoto Desktop Setup & Shortcut Creator
# Installs desktop dependencies and creates Windows Desktop / Start Menu shortcuts

param (
    [switch]$EnableAutostart,
    [switch]$DisableAutostart
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host "          LuminaPhoto Desktop Integration Setup            " -ForegroundColor Green
Write-Host "===========================================================" -ForegroundColor Cyan

# 1. Verify / Install Desktop Python Dependencies
Write-Host "[1/4] Checking Python desktop dependencies (pystray, pywebview)..." -ForegroundColor Yellow
python -c "import pystray, webview" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "      Installing pystray & pywebview..." -ForegroundColor Cyan
    pip install pystray pywebview
} else {
    Write-Host "      Dependencies already installed." -ForegroundColor Green
}

# 2. Check / Build frontend distribution
$FrontendDist = Join-Path $ScriptDir "frontend\dist\index.html"
if (-not (Test-Path $FrontendDist)) {
    Write-Host "[2/4] Building optimized frontend assets..." -ForegroundColor Yellow
    Push-Location (Join-Path $ScriptDir "frontend")
    npm run build
    Pop-Location
} else {
    Write-Host "[2/4] Frontend assets already built." -ForegroundColor Green
}

# 3. Generate icon files (.ico and .png)
Write-Host "[3/4] Ensuring application icons are generated..." -ForegroundColor Yellow
$IconPath = Join-Path $ScriptDir ".lumina_cache\lumina.ico"
python -c "from backend.desktop.icon import ensure_icon_files; ensure_icon_files()"
if (Test-Path $IconPath) {
    Write-Host "      Icon ready at $IconPath" -ForegroundColor Green
}

# 4. Create Desktop & Start Menu Shortcuts
Write-Host "[4/4] Creating Windows shortcuts..." -ForegroundColor Yellow
$WshShell = New-Object -ComObject WScript.Shell
$DesktopPath = [System.Environment]::GetFolderPath("Desktop")
$StartMenuPath = [System.Environment]::GetFolderPath("StartMenu")
$ProgramsPath = Join-Path $StartMenuPath "Programs"

$TargetScript = Join-Path $ScriptDir "LuminaPhoto.vbs"

# Desktop Shortcut
$ShortcutDesktop = $WshShell.CreateShortcut((Join-Path $DesktopPath "LuminaPhoto.lnk"))
$ShortcutDesktop.TargetPath = "wscript.exe"
$ShortcutDesktop.Arguments = "`"$TargetScript`""
$ShortcutDesktop.WorkingDirectory = $ScriptDir
$ShortcutDesktop.Description = "LuminaPhoto - AI Semantic Photo Studio"
if (Test-Path $IconPath) {
    $ShortcutDesktop.IconLocation = "$IconPath,0"
}
$ShortcutDesktop.Save()
Write-Host "      Created Desktop shortcut: LuminaPhoto.lnk" -ForegroundColor Green

# Start Menu Shortcut
$ShortcutPrograms = $WshShell.CreateShortcut((Join-Path $ProgramsPath "LuminaPhoto.lnk"))
$ShortcutPrograms.TargetPath = "wscript.exe"
$ShortcutPrograms.Arguments = "`"$TargetScript`""
$ShortcutPrograms.WorkingDirectory = $ScriptDir
$ShortcutPrograms.Description = "LuminaPhoto - AI Semantic Photo Studio"
if (Test-Path $IconPath) {
    $ShortcutPrograms.IconLocation = "$IconPath,0"
}
$ShortcutPrograms.Save()
Write-Host "      Created Start Menu shortcut: LuminaPhoto.lnk" -ForegroundColor Green

# Autostart configuration
if ($EnableAutostart) {
    python -m backend.desktop.autostart --enable
} elseif ($DisableAutostart) {
    python -m backend.desktop.autostart --disable
} else {
    $status = python -m backend.desktop.autostart --status
    Write-Host "`n$status" -ForegroundColor Cyan
    Write-Host "Tip: Run `.\setup_desktop.ps1 -EnableAutostart` to start LuminaPhoto automatically on boot." -ForegroundColor DarkGray
}

Write-Host "`n[SUCCESS] LuminaPhoto Desktop setup completed successfully!" -ForegroundColor Green
Write-Host "You can now launch LuminaPhoto anytime via your Desktop shortcut or start_desktop.py." -ForegroundColor Green
