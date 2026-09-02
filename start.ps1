# LuminaPhoto One-Click Launcher for Windows PowerShell
# Starts both the backend API and frontend web application

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "===========================================================" -ForegroundColor Cyan
Write-Host "             LuminaPhoto Application Launcher              " -ForegroundColor Green
Write-Host "===========================================================" -ForegroundColor Cyan

# 1. Check if frontend build exists, build if missing
$FrontendDist = Join-Path $ScriptDir "frontend\dist\index.html"
if (-not (Test-Path $FrontendDist)) {
    Write-Host "[INFO] First-time setup: Building optimized frontend assets..." -ForegroundColor Yellow
    Push-Location (Join-Path $ScriptDir "frontend")
    npm run build
    Pop-Location
}

# 2. Launch the application (starts FastAPI server, LAN Wi-Fi host & opens browser)
Write-Host "[INFO] Starting LuminaPhoto server..." -ForegroundColor Green
python start_app.py
