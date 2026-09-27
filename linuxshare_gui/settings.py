"""Configuration management and settings dialog for the GUI.

The config helpers are deliberately free of any GTK imports so they can
be unit-tested without a display server. The settings *dialog* is built
lazily and only imports GTK when constructed.
"""

from __future__ import annotations

import json
import os
import tempfile
import sys
from dataclasses import asdict, dataclass

CONFIG_DIR = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
    "linuxshare",
)
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

VALID_FPS = (15, 24, 30, 60)


@dataclass
class Config:
    """Persisted user settings."""

    fps: int = 30
    device: str = ""
    autostart: bool = False

    def normalise(self) -> "Config":
        """Clamp values to valid ranges."""
        if self.fps not in VALID_FPS:
            self.fps = 30
        return self


def default_config() -> Config:
    return Config()


def load_config(path: str = CONFIG_PATH) -> Config:
    """Load config from *path*, returning defaults if missing/invalid."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return default_config()
    if not isinstance(data, dict):
        return default_config()
    fps = data.get("fps", 30)
    cfg = Config(
        fps=fps if type(fps) is int else 30,
        device=data.get("device", "") if isinstance(data.get("device", ""), str) else "",
        autostart=data.get("autostart") is True,
    )
    return cfg.normalise()


def save_config(config: Config, path: str = CONFIG_PATH) -> None:
    """Atomically replace configuration, with private file permissions."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, mode=0o700, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".linuxshare-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(asdict(config.normalise()), fh, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


# --- Autostart (XDG desktop entry) --------------------------------------

AUTOSTART_DIR = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
    "autostart",
)
AUTOSTART_PATH = os.path.join(AUTOSTART_DIR, "linuxshare-gui.desktop")

_AUTOSTART_ENTRY = """[Desktop Entry]
Type=Application
Name=LinuxShare
Exec={executable} -m linuxshare_gui.main
Icon=linuxshare
X-GNOME-Autostart-enabled=true
Comment=Start LinuxShare screen sharing on login
"""


def set_autostart(enabled: bool) -> None:
    """Create or remove the autostart desktop entry."""
    if enabled:
        os.makedirs(AUTOSTART_DIR, exist_ok=True)
        with open(AUTOSTART_PATH, "w", encoding="utf-8") as fh:
            executable = sys.executable.replace("\\", "\\\\").replace('"', '\\"')
            executable = executable.replace("$", "\\$").replace("`", "\\`").replace("%", "%%")
            fh.write(_AUTOSTART_ENTRY.format(executable='"' + executable + '"'))
    else:
        try:
            os.remove(AUTOSTART_PATH)
        except OSError:
            pass


def build_settings_dialog(parent, config: Config, on_save):  # pragma: no cover
    """Build and return an Adw/Gtk settings dialog.

    Imported lazily to avoid a hard GTK dependency in tests.

    :param parent: parent window.
    :param config: current :class:`Config`.
    :param on_save: callback invoked with the new :class:`Config`.
    """
    import gi

    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk

    from . import capture as gui_capture

    dialog = Gtk.Dialog(title="Settings", transient_for=parent, modal=True)
    dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
    dialog.add_button("Save", Gtk.ResponseType.OK)

    content = dialog.get_content_area()
    content.set_margin_top(12)
    content.set_margin_bottom(12)
    content.set_margin_start(12)
    content.set_margin_end(12)
    content.set_spacing(12)

    # FPS selector.
    fps_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    fps_row.append(Gtk.Label(label="Framerate (FPS):", xalign=0))
    fps_combo = Gtk.DropDown.new_from_strings([str(f) for f in VALID_FPS])
    try:
        fps_combo.set_selected(VALID_FPS.index(config.fps))
    except ValueError:
        fps_combo.set_selected(VALID_FPS.index(30))
    fps_row.append(fps_combo)
    content.append(fps_row)

    # Device selector.
    dev_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    dev_row.append(Gtk.Label(label="Virtual camera device:", xalign=0))
    devices = [""] + [d.path for d in gui_capture.list_loopback_devices()]
    dev_combo = Gtk.DropDown.new_from_strings(["Auto (verified loopback only)"] + devices[1:])
    if config.device in devices:
        dev_combo.set_selected(devices.index(config.device))
    dev_row.append(dev_combo)
    content.append(dev_row)

    # Autostart toggle.
    auto_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
    auto_row.append(Gtk.Label(label="Start on login:", xalign=0))
    auto_switch = Gtk.Switch(active=config.autostart)
    auto_switch.set_halign(Gtk.Align.START)
    auto_row.append(auto_switch)
    content.append(auto_row)

    def _on_response(dlg, response):
        if response == Gtk.ResponseType.OK:
            new_cfg = Config(
                fps=VALID_FPS[fps_combo.get_selected()],
                device=devices[dev_combo.get_selected()],
                autostart=auto_switch.get_active(),
            )
            set_autostart(new_cfg.autostart)
            save_config(new_cfg)
            on_save(new_cfg)
        dlg.destroy()

    dialog.connect("response", _on_response)
    return dialog
