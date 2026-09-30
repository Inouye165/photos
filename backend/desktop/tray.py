"""
Windows System Tray integration for LuminaPhoto using pystray.
Provides status indicators, quick actions, autostart toggle, and clean shutdown.
"""

import os
import sys
import threading
import webbrowser
from typing import Optional, Callable, List

import pystray
from PIL import Image

from backend.desktop.icon import get_lumina_icon_image
from backend.desktop.autostart import is_autostart_enabled, set_autostart

class LuminaTrayApp:
    def __init__(
        self,
        local_url: str = "http://localhost:8500",
        network_urls: Optional[List[str]] = None,
        on_open_window: Optional[Callable[[], None]] = None,
        on_open_browser: Optional[Callable[[], None]] = None,
        on_quit: Optional[Callable[[], None]] = None
    ):
        self.local_url = local_url
        self.network_urls = network_urls or []
        self.on_open_window = on_open_window or self._default_open_browser
        self.on_open_browser = on_open_browser or self._default_open_browser
        self.on_quit = on_quit
        self.icon: Optional[pystray.Icon] = None
        self._is_running = False

    def _default_open_browser(self):
        webbrowser.open(self.local_url)

    def _open_network_url(self, url: str):
        def _handler(icon, item):
            webbrowser.open(url)
        return _handler

    def _toggle_autostart(self, icon, item):
        currently_enabled = is_autostart_enabled()
        new_state = not currently_enabled
        success = set_autostart(new_state)
        if success and self.icon:
            msg = "LuminaPhoto will start when you log in." if new_state else "Auto-start on logon disabled."
            try:
                self.icon.notify(msg, "Windows Auto-Start")
            except Exception:
                pass

    def _open_photos_folder(self, icon, item):
        try:
            repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            os.startfile(repo_root)
        except Exception as e:
            print(f"[WARN] Could not open folder: {e}")

    def _handle_open_window(self, icon, item):
        if self.on_open_window:
            self.on_open_window()

    def _handle_open_browser(self, icon, item):
        if self.on_open_browser:
            self.on_open_browser()

    def _handle_quit(self, icon, item):
        self.stop()
        if self.on_quit:
            self.on_quit()

    def _build_menu(self) -> pystray.Menu:
        menu_items = []

        # 1. Main entry: Open Desktop App
        menu_items.append(pystray.MenuItem("Open LuminaPhoto", self._handle_open_window, default=True))
        menu_items.append(pystray.MenuItem("Open in Web Browser", self._handle_open_browser))

        # 2. Local Wi-Fi / Phone links
        if self.network_urls:
            wifi_subitems = []
            for nurl in self.network_urls:
                wifi_subitems.append(pystray.MenuItem(nurl, self._open_network_url(nurl)))
            menu_items.append(pystray.MenuItem("Phone / Wi-Fi Access", pystray.Menu(*wifi_subitems)))

        menu_items.append(pystray.Menu.SEPARATOR)

        # 3. System actions & folder
        menu_items.append(pystray.MenuItem(
            "Start with Windows",
            self._toggle_autostart,
            checked=lambda item: is_autostart_enabled()
        ))
        menu_items.append(pystray.MenuItem("Open Project Folder", self._open_photos_folder))

        menu_items.append(pystray.Menu.SEPARATOR)

        # 4. Quit
        menu_items.append(pystray.MenuItem("Exit LuminaPhoto", self._handle_quit))

        return pystray.Menu(*menu_items)

    def start(self, detached: bool = False):
        """Starts the tray icon."""
        if self._is_running:
            return

        icon_img = get_lumina_icon_image(64)
        self.icon = pystray.Icon(
            "LuminaPhoto",
            icon_img,
            "LuminaPhoto — AI Photo Studio",
            menu=self._build_menu()
        )
        self._is_running = True

        if detached:
            self.icon.run_detached()
        else:
            self.icon.run()

    def notify(self, title: str, message: str):
        """Displays a Windows notification balloon."""
        if self.icon and self._is_running:
            try:
                self.icon.notify(message, title)
            except Exception:
                pass

    def stop(self):
        """Stops and removes the tray icon."""
        self._is_running = False
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass
            self.icon = None
