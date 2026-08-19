"""System tray icon with AppIndicator, falling back to Gtk.StatusIcon.

Tray support on Linux is fragmented. This module attempts, in order:

1. ``AyatanaAppIndicator3`` / ``AppIndicator3`` (works under most desktops
   and Wayland via the StatusNotifierItem spec).
2. A no-op stub if neither is available, so the app still runs.
"""

from __future__ import annotations

from typing import Callable


class TrayIcon:
    """Abstraction over the available tray backend."""

    def __init__(
        self,
        on_show: Callable[[], None],
        on_stop: Callable[[], None],
        on_quit: Callable[[], None],
        icon_name: str = "linuxshare",
    ) -> None:
        self.on_show = on_show
        self.on_stop = on_stop
        self.on_quit = on_quit
        self.icon_name = icon_name
        self._backend = None
        self._indicator = None
        self._setup()

    def _setup(self) -> None:  # pragma: no cover - depends on system libs
        indicator = self._try_appindicator()
        if indicator is not None:
            self._backend = "appindicator"
            self._indicator = indicator
            return
        self._backend = "none"

    def _build_menu(self):  # pragma: no cover - requires GTK
        import gi

        gi.require_version("Gtk", "4.0")
        from gi.repository import Gtk

        menu = Gtk.Menu() if hasattr(Gtk, "Menu") else None
        if menu is None:
            # GTK4 dropped Gtk.Menu; AppIndicator needs GTK3 menus. When only
            # GTK4 is present we expose actions via the app instead.
            return None
        show_item = Gtk.MenuItem(label="Show window")
        show_item.connect("activate", lambda *_: self.on_show())
        stop_item = Gtk.MenuItem(label="Stop sharing")
        stop_item.connect("activate", lambda *_: self.on_stop())
        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", lambda *_: self.on_quit())
        for item in (show_item, stop_item, quit_item):
            menu.append(item)
        menu.show_all()
        return menu

    def _try_appindicator(self):  # pragma: no cover - depends on system libs
        import gi

        for lib, ver in (("AyatanaAppIndicator3", "0.1"), ("AppIndicator3", "0.1")):
            try:
                gi.require_version(lib, ver)
                mod = __import__("gi.repository", fromlist=[lib])
                appindicator = getattr(mod, lib)
            except (ValueError, ImportError, AttributeError):
                continue

            menu = self._build_menu()
            if menu is None:
                continue
            indicator = appindicator.Indicator.new(
                "linuxshare",
                self.icon_name,
                appindicator.IndicatorCategory.APPLICATION_STATUS,
            )
            indicator.set_status(appindicator.IndicatorStatus.ACTIVE)
            indicator.set_menu(menu)
            return indicator
        return None

    @property
    def available(self) -> bool:
        """Whether a real tray backend is active."""
        return self._backend == "appindicator"

    def set_sharing(self, sharing: bool) -> None:  # pragma: no cover
        """Update the icon/label to reflect sharing state."""
        if self._backend == "appindicator" and self._indicator is not None:
            label = "Sharing" if sharing else ""
            try:
                self._indicator.set_label(label, "")
            except Exception:  # noqa: BLE001
                pass
