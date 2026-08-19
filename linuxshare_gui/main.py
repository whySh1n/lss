"""Entry point for the linuxshare-gui command."""

from __future__ import annotations

import sys


def main() -> None:
    """Launch the GTK application."""
    try:
        import gi  # noqa: F401
    except ImportError:
        sys.stderr.write(
            "PyGObject (python-gobject) is required for the GUI.\n"
            "Install it:\n"
            "  Arch:   sudo pacman -S python-gobject gtk4 libadwaita\n"
            "  Debian: sudo apt install python3-gi python3-gi-cairo "
            "gir1.2-gtk-4.0 gir1.2-adw-1\n"
        )
        sys.exit(1)

    # Imported here so the helpful message above shows first if gi missing.
    from .app import LinuxShareApp

    app = LinuxShareApp()
    sys.exit(app.run(sys.argv))


if __name__ == "__main__":
    main()
