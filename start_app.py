"""
LuminaPhoto Application Launcher.
Starts the FastAPI server on 0.0.0.0 (home network & mobile accessible) on port 8000.
"""

import os
import sys
import socket
import webbrowser
import uvicorn

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

if __name__ == "__main__":
    port = 8500
    host = "0.0.0.0"
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

    # Open local browser
    try:
        webbrowser.open(local_url)
    except Exception:
        pass

    # Launch Uvicorn on 0.0.0.0
    uvicorn.run("backend.app:app", host=host, port=port, reload=False)
