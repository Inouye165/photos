"""
LuminaPhoto Application Launcher.
Starts the FastAPI server on 0.0.0.0 (home network & mobile accessible) on port 8000.
"""

import os
import sys
import socket
import webbrowser
import logging
import time
import threading
import urllib.request
import uvicorn

class EndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "/api/backup/status" not in record.getMessage()

logging.getLogger("uvicorn.access").addFilter(EndpointFilter())

def get_local_ips():
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

def wait_for_server_and_open_browser(url: str, port: int, timeout: float = 60.0):
    """
    Waits for the FastAPI server to be fully initialized and responding
    to health checks before launching the web browser.
    Prevents 'Unable to connect' or 'Can't find this page' browser errors on startup.
    """
    start_time = time.time()
    health_url = f"http://127.0.0.1:{port}/api/health"
    print("   [INFO] Waiting for server to initialize before opening browser...")

    while time.time() - start_time < timeout:
        try:
            req = urllib.request.Request(
                health_url,
                headers={"User-Agent": "LuminaPhoto-Launcher"}
            )
            with urllib.request.urlopen(req, timeout=1.0) as response:
                if response.status == 200:
                    time.sleep(0.2)  # Brief grace period for ASGI static routes
                    print(f"   [INFO] Server is ready! Opening browser: {url}")
                    webbrowser.open(url)
                    return
        except Exception:
            pass
        time.sleep(0.3)

    # Fallback if timeout is reached
    print(f"   [WARN] Server health check timed out after {int(timeout)}s. Attempting to open browser: {url}")
    try:
        webbrowser.open(url)
    except Exception:
        pass

def free_port_if_in_use(port: int):
    """Ensure port is free before starting Uvicorn, avoiding WinError 10048."""
    import subprocess
    try:
        cmd = f'netstat -ano | findstr :{port}'
        output = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL)
        pids = set()
        for line in output.strip().splitlines():
            parts = line.split()
            if len(parts) >= 5 and "LISTENING" in parts[3].upper():
                pid = int(parts[4])
                if pid > 0 and pid != os.getpid():
                    pids.add(pid)
        for pid in pids:
            print(f"   [INFO] Port {port} in use by PID {pid}. Freeing port...")
            subprocess.run(f'taskkill /F /PID {pid}', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(0.5)
    except Exception:
        pass

if __name__ == "__main__":
    port = 8500
    host = "0.0.0.0"
    free_port_if_in_use(port)
    local_url = f"http://localhost:{port}"
    ips = get_local_ips()
    network_urls = [f"http://{ip}:{port}" for ip in ips]

    print("=" * 65)
    print("   LuminaPhoto — AI Semantic Photo Studio")
    print("   In-Place Pointer Catalog & Home Network Host")
    print("=" * 65)
    print(f"   * Local Computer:    {local_url}")
    for nurl in network_urls:
        print(f"   * Phone / Wi-Fi LAN: {nurl}")
    print("=" * 65)
    print("   Note: In-place pointer catalog. Deletions safely protect to OS Recycle Bin.")
    print("=" * 65)

    # Launch browser polling in background thread; only opens once server responds OK
    threading.Thread(
        target=wait_for_server_and_open_browser,
        args=(local_url, port),
        daemon=True
    ).start()

    # Launch Uvicorn on 0.0.0.0
    uvicorn.run("backend.app:app", host=host, port=port, reload=False)


