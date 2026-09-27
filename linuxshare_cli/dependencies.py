"""Dependency checking for linuxshare.

Verifies that the external system tools and kernel modules required for
screen capture are available, and produces clear, actionable error
messages when something is missing.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass

# Map of executable name -> human friendly package hints per distro.
REQUIRED_COMMANDS = {}
X11_COMMANDS = {
    "ffmpeg": {"description": "X11 capture", "arch": "ffmpeg", "debian": "ffmpeg"},
    "xrandr": {"description": "Monitor enumeration", "arch": "xorg-xrandr",
               "debian": "x11-xserver-utils"},
}
WAYLAND_COMMANDS = {
    "gst-launch-1.0": {"description": "Wayland capture pipeline", "arch": "gstreamer",
                       "debian": "gstreamer1.0-tools"},
    "gst-inspect-1.0": {"description": "Pipeline plugin checks", "arch": "gstreamer",
                        "debian": "gstreamer1.0-tools"},
}
OPTIONAL_COMMANDS = {
    "xdotool": {"description": "X11 window listing", "arch": "xdotool",
                "debian": "xdotool"},
}


def gst_element_available(element):
    try:
        return subprocess.run(["gst-inspect-1.0", element],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              timeout=5, check=False).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def portal_available():
    try:
        from gi.repository import Gio, GLib
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        value = bus.call_sync(
            "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
            "org.freedesktop.DBus.Properties", "Get",
            GLib.Variant("(ss)", ("org.freedesktop.portal.ScreenCast",
                                  "AvailableSourceTypes")),
            None, Gio.DBusCallFlags.NONE, 3000, None,
        )
        return bool(value.unpack()[0] & 3)
    except (ImportError, ValueError, RuntimeError):
        return False
    except Exception:
        return False  # D-Bus unavailable or portal backend does not implement screencast.


@dataclass
class DependencyResult:
    """Result of a dependency scan."""

    name: str
    description: str
    found: bool
    optional: bool
    arch_pkg: str
    debian_pkg: str


def command_exists(command: str) -> bool:
    """Return True if *command* is found on PATH."""
    return shutil.which(command) is not None


def module_available(module: str = "v4l2loopback") -> bool:
    """Return True if a kernel module is loadable or already loaded.

    Checks ``modinfo`` (module installed) rather than requiring it to be
    currently loaded, since loading happens later.
    """
    if not command_exists("modinfo"):
        # Cannot determine; assume not available so we surface a hint.
        return False
    try:
        result = subprocess.run(
            ["modinfo", module],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _scan(commands: dict, optional: bool) -> list[DependencyResult]:
    results = []
    for name, meta in commands.items():
        results.append(
            DependencyResult(
                name=name,
                description=meta["description"],
                found=command_exists(name),
                optional=optional,
                arch_pkg=meta["arch"],
                debian_pkg=meta["debian"],
            )
        )
    return results


def check_dependencies(session_type: str | None = None) -> list[DependencyResult]:
    """Scan all relevant dependencies.

    :param session_type: ``"x11"``, ``"wayland"`` or ``None`` (check both).
    :returns: list of :class:`DependencyResult`.
    """
    results: list[DependencyResult] = []
    results.extend(_scan(REQUIRED_COMMANDS, optional=False))

    if session_type in (None, "x11"):
        results.extend(_scan(X11_COMMANDS, optional=(session_type is None)))
    if session_type in (None, "wayland"):
        results.extend(_scan(WAYLAND_COMMANDS, optional=(session_type is None)))

    results.extend(_scan(OPTIONAL_COMMANDS, optional=True))
    if session_type in (None, "wayland"):
        for element, arch, debian in (
            ("pipewiresrc", "gst-plugin-pipewire", "gstreamer1.0-pipewire"),
            ("videoconvert", "gst-plugins-base", "gstreamer1.0-plugins-base"),
            ("videorate", "gst-plugins-base", "gstreamer1.0-plugins-base"),
            ("v4l2sink", "gst-plugins-good", "gstreamer1.0-plugins-good"),
        ):
            results.append(DependencyResult(
                element, "GStreamer element", gst_element_available(element),
                session_type is None, arch, debian))
        results.append(DependencyResult(
            "ScreenCast portal", "PyGObject and a working desktop portal backend",
            portal_available(), session_type is None,
            "python-gobject xdg-desktop-portal", "python3-gi xdg-desktop-portal"))

    # v4l2loopback kernel module.
    results.append(
        DependencyResult(
            name="v4l2loopback",
            description="v4l2loopback kernel module (virtual camera)",
            found=module_available("v4l2loopback"),
            optional=False,
            arch_pkg="v4l2loopback-dkms",
            debian_pkg="v4l2loopback-dkms",
        )
    )
    return results


def missing_required(results: list[DependencyResult]) -> list[DependencyResult]:
    """Return the subset of *results* that are required and missing."""
    return [r for r in results if not r.found and not r.optional]


def format_report(results: list[DependencyResult]) -> str:
    """Return a human readable dependency report."""
    lines = ["Dependency check:"]
    for r in results:
        mark = "OK " if r.found else ("-- " if r.optional else "!! ")
        status = "found" if r.found else "MISSING"
        tag = " (optional)" if r.optional else ""
        lines.append(f"  [{mark}] {r.name}: {status}{tag} - {r.description}")

    missing = missing_required(results)
    if missing:
        lines.append("")
        lines.append("Some required dependencies are missing. Install them:")
        arch_pkgs = " ".join(sorted({m.arch_pkg for m in missing}))
        deb_pkgs = " ".join(sorted({m.debian_pkg for m in missing}))
        lines.append(f"  Arch:   sudo pacman -S {arch_pkgs}")
        lines.append(f"  Debian: sudo apt install {deb_pkgs}")
        lines.append("  Also install your desktop's portal backend and matching kernel headers.")
    return "\n".join(lines)
