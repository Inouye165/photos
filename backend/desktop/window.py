"""
Native Desktop WebView2 Window for LuminaPhoto using pywebview.
Provides a native window feel with dark mode styling, minimize-to-tray on close,
and seamless desktop integration.
"""

import os
import sys
import threading
from typing import Optional, Callable

import webview
from backend.desktop.icon import ensure_icon_files

class LuminaDesktopWindow:
    def __init__(
        self,
        url: str = "http://localhost:8500",
        title: str = "LuminaPhoto — AI Semantic Photo Studio",
        on_notify: Optional[Callable[[str, str], None]] = None,
        on_exit: Optional[Callable[[], None]] = None
    ):
        self.url = url
        self.title = title
        self.on_notify = on_notify
        self.on_exit = on_exit
        self.window: Optional[webview.Window] = None
        self._allow_close = False
        self._closing_notified = False

    def create(self) -> webview.Window:
        """Creates the pywebview window instance."""
        ensure_icon_files()
        
        self.window = webview.create_window(
            title=self.title,
            url=self.url,
            width=1280,
            height=820,
            min_size=(960, 600),
            background_color="#0b0f19",
            text_select=True,
            confirm_close=False
        )

        self.window.events.closing += self._on_closing
        return self.window

    def _on_closing(self) -> bool:
        """
        Intercepts window close button (X).
        If close wasn't explicitly requested via Exit, minimizes to system tray instead.
        """
        if self._allow_close:
            return True

        # Hide window to tray
        if self.window:
            try:
                self.window.hide()
            except Exception as e:
                print(f"[DEBUG] Window hide exception: {e}")

        # Send balloon notification on first close
        if not self._closing_notified and self.on_notify:
            self._closing_notified = True
            self.on_notify(
                "LuminaPhoto Background",
                "LuminaPhoto is still running in your system tray.\nAccess it anytime or right-click the tray icon to exit."
            )

        return False

    def show(self):
        """Shows and restores the window."""
        if self.window:
            try:
                self.window.show()
                self.window.restore()
            except Exception as e:
                print(f"[DEBUG] Window show exception: {e}")

    def close(self):
        """Allows window to close and destroys it."""
        self._allow_close = True
        if self.window:
            try:
                self.window.destroy()
            except Exception:
                pass

    def start(self):
        """Starts the pywebview GUI loop on the main thread."""
        webview.start(private_mode=False, storage_path=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".lumina_cache", "webview"))
