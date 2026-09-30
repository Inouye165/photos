@echo off
rem =======================================================
rem  LuminaPhoto — One-Click Desktop Launcher
rem =======================================================

cd /d "%~dp0"

where pythonw >nul 2>nul
if %ERRORLEVEL% equ 0 (
    start "" pythonw start_desktop.py
) else (
    start "" python start_desktop.py
)
exit /b 0
