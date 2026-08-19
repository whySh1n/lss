"""Gtk.Application subclass wiring together window, actions and tray."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, Gtk  # noqa: E402

try:
    gi.require_version("Adw", "1")
    from gi.repository import Adw  # noqa: E402

    _HAVE_ADW = True
except (ValueError, ImportError):  # pragma: no cover
    _HAVE_ADW = False

from .window import MainWindow  # noqa: E402

APP_ID = "io.github.linuxshare.LinuxShare"

_AppBase = Adw.Application if _HAVE_ADW else Gtk.Application


class LinuxShareApp(_AppBase):  # type: ignore[misc, valid-type]
    """The main GTK application."""

    def __init__(self) -> None:
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        self.window: MainWindow | None = None
        self.tray = None

    def do_startup(self) -> None:  # noqa: D401
        _AppBase.do_startup(self)
        self._add_action("settings", self._on_settings)
        self._add_action("about", self._on_about)
        self._add_action("stop", self._on_stop)
        self._add_action("quit", self._on_quit)

    def do_activate(self) -> None:
        if self.window is None:
            self.window = MainWindow(self)
            self._setup_tray()
        self.window.present()

    def _add_action(self, name: str, callback) -> None:  # noqa: ANN001
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        self.add_action(action)

    def _setup_tray(self) -> None:
        from .tray import TrayIcon

        try:
            self.tray = TrayIcon(
                on_show=self._present_window,
                on_stop=lambda: self.window and self.window.stop_sharing(),
                on_quit=self._quit,
            )
        except Exception:  # noqa: BLE001  # pragma: no cover
            self.tray = None

    # -- Action handlers -------------------------------------------------

    def _present_window(self) -> None:
        if self.window is not None:
            self.window.present()

    def _on_settings(self, *_args) -> None:
        if self.window is not None:
            self.window.open_settings()

    def _on_about(self, *_args) -> None:
        if self.window is not None:
            self.window.open_about()

    def _on_stop(self, *_args) -> None:
        if self.window is not None:
            self.window.stop_sharing()

    def _on_quit(self, *_args) -> None:
        self._quit()

    def _quit(self) -> None:
        if self.window is not None:
            try:
                self.window.controller.stop()
            except Exception:  # noqa: BLE001
                pass
        self.quit()
