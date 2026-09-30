"""
LuminaPhoto Desktop Launcher.
Starts the FastAPI server, system tray icon, and native desktop window.
Supports silent background boot on Windows login (--minimized) and browser mode (--browser-only).
"""

import os
import sys
import time
import socket
import argparse
import threading
import webbrowser
import urllib.request
import logging
from typing import List

import uvicorn

from backend.desktop.icon import ensure_icon_files
from backend.desktop.tray import LuminaTrayApp
from backend.desktop.autostart import is_autostart_enabled

class EndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "/api/backup/status" not in record.getMessage()

logging.getLogger("uvicorn.access").addFilter(EndpointFilter())

def get_local_ips() -> List[str]:
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        s.connect(("8.8.8.8", 80))
        primary_ip = s.getsockname()[0]
        s.close()
        if primary_ip and not primary_ip.startswith("127."):
            ips.append(primary_ip)
    except Exception:
        pass
    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except Exception:
        pass
    return ips or ["127.0.0.1"]

def wait_for_server(port: int, timeout: float = 45.0) -> bool:
    """Waits for FastAPI /api/health before continuing."""
    start_time = time.time()
    health_url = f"http://127.0.0.1:{port}/api/health"
    while time.time() - start_time < timeout:
        try:
            req = urllib.request.Request(
                health_url,
                headers={"User-Agent": "LuminaPhoto-Launcher"}
            )
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                if resp.status == 200:
                    time.sleep(0.15)
                    return True
        except Exception:
            pass
        time.sleep(0.2)
    return False

def main():
    parser = argparse.ArgumentParser(description="LuminaPhoto Desktop Application")
    parser.add_argument("--port", type=int, default=8500, help="Server port (default: 8500)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Server host (default: 0.0.0.0)")
    parser.add_argument("--minimized", "--headless", action="store_true", help="Start minimized in system tray (for Windows logon)")
    parser.add_argument("--no-window", action="store_true", help="Run in system tray without opening desktop window")
    parser.add_argument("--browser-only", action="store_true", help="Open default web browser instead of native desktop window")
    args = parser.parse_args()

    port = args.port
    host = args.host
    local_url = f"http://localhost:{port}"
    ips = get_local_ips()
    network_urls = [f"http://{ip}:{port}" for ip in ips]

    # Pre-generate icons for tray and window
    ensure_icon_files()

    print("=" * 65)
    print("   LuminaPhoto Desktop — System Tray & Background Service")
    print("=" * 65)
    print(f"   * Local Host:        {local_url}")
    for nurl in network_urls:
        print(f"   * Phone / Wi-Fi LAN: {nurl}")
    print(f"   * Autostart on boot: {'ENABLED' if is_autostart_enabled() else 'DISABLED'}")
    print("=" * 65)

    # 1. Start Uvicorn in background daemon thread
    config = uvicorn.Config(
        "backend.app:app",
        host=host,
        port=port,
        reload=False,
        log_level="warning"
    )
    server = uvicorn.Server(config)
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    # 2. Wait for server to respond
    server_ok = wait_for_server(port, timeout=40.0)
    if not server_ok:
        print("[WARN] Server health check timed out. Attempting to proceed...")

    # Desktop window reference (if used)
    desktop_window = None

    def on_quit():
        """Clean shutdown handler triggered from System Tray."""
        print("[INFO] Shutting down LuminaPhoto...")
        server.should_exit = True
        if desktop_window:
            desktop_window.close()
        # Allow brief time for server to finalize WAL / background threads
        time.sleep(0.5)
        sys.exit(0)

    def on_open_window():
        """Brings desktop window to front, or creates one if not open, or falls back to browser."""
        if desktop_window:
            desktop_window.show()
        else:
            webbrowser.open(local_url)

    def on_open_browser():
        webbrowser.open(local_url)

    # 3. Create System Tray instance
    tray_app = LuminaTrayApp(
        local_url=local_url,
        network_urls=network_urls,
        on_open_window=on_open_window,
        on_open_browser=on_open_browser,
        on_quit=on_quit
    )

    is_silent = args.minimized or args.no_window

    # Mode A: Silent Tray only (for Windows logon autostart)
    if is_silent:
        tray_app.start(detached=False)
        return

    # Mode B: Browser only
    if args.browser_only:
        webbrowser.open(local_url)
        tray_app.start(detached=False)
        return

    # Mode C: Native Desktop App Window with pywebview + System Tray
    try:
        from backend.desktop.window import LuminaDesktopWindow
        desktop_window = LuminaDesktopWindow(
            url=local_url,
            title="LuminaPhoto — AI Semantic Photo Studio",
            on_notify=tray_app.notify,
            on_exit=on_quit
        )
        desktop_window.create()

        # Run tray detached so pywebview can own the main GUI thread on Windows
        tray_app.start(detached=True)

        # Notify user tray is available
        tray_app.notify(
            "LuminaPhoto is Running",
            f"Active on {local_url}\nRight-click tray icon anytime for settings and Wi-Fi access."
        )

        # Start desktop window GUI event loop (blocks until user quits or window closes)
        desktop_window.start()

    except Exception as e:
        print(f"[WARN] Could not initialize native WebView window ({e}). Falling back to browser...")
        webbrowser.open(local_url)
        tray_app.start(detached=False)

if __name__ == "__main__":
    main()
