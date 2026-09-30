r"""
Windows Auto-Start Manager for LuminaPhoto.
Manages automatic startup on user logon via Windows Registry (HKCU\...\Run)
and the Windows Startup directory.
"""

import os
import sys
import winreg
from typing import Dict, Any, Optional

REG_SUBKEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "LuminaPhoto"

def get_pythonw_executable() -> str:
    """Returns the path to pythonw.exe corresponding to current Python environment."""
    current_exe = sys.executable
    dirname = os.path.dirname(current_exe)
    pythonw = os.path.join(dirname, "pythonw.exe")
    if os.path.exists(pythonw):
        return pythonw
    return current_exe

def get_startup_command() -> str:
    """Returns the launch command string for silent background execution on logon."""
    pythonw = get_pythonw_executable()
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    launcher = os.path.join(repo_root, "start_desktop.py")
    return f'"{pythonw}" "{launcher}" --minimized'

def is_autostart_enabled() -> bool:
    """Checks whether LuminaPhoto is configured to start on Windows logon."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_SUBKEY, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
            return bool(value)
    except FileNotFoundError:
        return False
    except Exception as e:
        print(f"[WARN] Error reading autostart registry: {e}")
        return False

def set_autostart(enabled: bool) -> bool:
    """Enables or disables LuminaPhoto startup on user logon."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_SUBKEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                cmd = get_startup_command()
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
                print(f"[INFO] LuminaPhoto autostart enabled: {cmd}")
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                    print("[INFO] LuminaPhoto autostart disabled")
                except FileNotFoundError:
                    pass
        return True
    except Exception as e:
        print(f"[ERROR] Failed to set autostart: {e}")
        return False

def get_autostart_status() -> Dict[str, Any]:
    """Returns detailed autostart status dictionary."""
    enabled = is_autostart_enabled()
    cmd = get_startup_command()
    return {
        "enabled": enabled,
        "app_name": APP_NAME,
        "command": cmd if enabled else None,
        "target_executable": get_pythonw_executable(),
        "is_windows": sys.platform == "win32"
    }

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Manage LuminaPhoto Windows Autostart")
    parser.add_argument("--status", action="store_true", help="Print current autostart status")
    parser.add_argument("--enable", action="store_true", help="Enable startup on boot")
    parser.add_argument("--disable", action="store_true", help="Disable startup on boot")
    args = parser.parse_args()

    if args.enable:
        set_autostart(True)
    elif args.disable:
        set_autostart(False)
    
    status = get_autostart_status()
    print(f"LuminaPhoto Autostart: {'ENABLED' if status['enabled'] else 'DISABLED'}")
