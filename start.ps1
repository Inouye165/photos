# LuminaPhoto One-Click Launcher for Windows PowerShell
# Starts both the backend API and frontend web application

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host "             LuminaPhoto Application Launcher              " -ForegroundColor Green
Write-Host "===========================================================" -ForegroundColor Cyan

# 1. Check if frontend build exists or is outdated, build if needed
$FrontendDist = Join-Path $ScriptDir "frontend\dist\index.html"
$NeedsBuild = -not (Test-Path $FrontendDist)
if (-not $NeedsBuild) {
    $DistTime = (Get-Item $FrontendDist).LastWriteTime
    $NewerSource = Get-ChildItem -Path (Join-Path $ScriptDir "frontend\src") -Recurse | Where-Object { $_.LastWriteTime -gt $DistTime } | Select-Object -First 1
    if ($NewerSource) {
        $NeedsBuild = $true
    }
}

if ($NeedsBuild) {
    Write-Host "[INFO] Building latest frontend assets..." -ForegroundColor Yellow
    Push-Location (Join-Path $ScriptDir "frontend")
    npm run build
    Pop-Location
}

# 2. Free port 8500 if already in use by a previous instance
$PortProcesses = Get-NetTCPConnection -LocalPort 8500 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
foreach ($PidToKill in $PortProcesses) {
    if ($PidToKill -and $PidToKill -gt 0) {
        Write-Host "[INFO] Freeing port 8500: stopping previous instance (PID: $PidToKill)..." -ForegroundColor Yellow
        Stop-Process -Id $PidToKill -Force -ErrorAction SilentlyContinue
    }
}
Start-Sleep -Milliseconds 600

# 3. Detect shell and python executables
$ShellExe = if (Get-Command pwsh.exe -ErrorAction SilentlyContinue) { "pwsh.exe" } else { "powershell.exe" }
$PythonCmd = (Get-Command python.exe, py.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -First 1)
if (-not $PythonCmd) { $PythonCmd = "python" }

# 4. Launch in a standalone external terminal window
# Using Start-Process opens an independent console window that is not bound to the IDE.
Write-Host "[INFO] Launching LuminaPhoto server in an independent terminal window..." -ForegroundColor Green

$HostTitle = "LuminaPhoto Server"
$RunScript = "`$Host.UI.RawUI.WindowTitle = '$HostTitle'; Set-Location -LiteralPath '$ScriptDir'; & '$PythonCmd' start_app.py"

Start-Process $ShellExe -WorkingDirectory $ScriptDir -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy", "Bypass",
    "-Command", $RunScript
)

Write-Host ""
Write-Host "[SUCCESS] LuminaPhoto server launched in an external terminal window." -ForegroundColor Cyan
Write-Host "[INFO] You can now safely close this IDE without stopping the server!" -ForegroundColor Yellow
Write-Host "[INFO] Web app URL: http://localhost:8500" -ForegroundColor Green
Write-Host ""


