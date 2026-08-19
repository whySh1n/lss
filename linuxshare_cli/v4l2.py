"""Management of the v4l2loopback virtual camera kernel module."""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
from dataclasses import dataclass

DEFAULT_CARD_LABEL = "LinuxShare Virtual Camera"


@dataclass
class LoopbackDevice:
    """Represents a /dev/videoN device."""

    path: str
    name: str


def _read(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def is_module_loaded(module: str = "v4l2loopback") -> bool:
    """Return True if the given kernel module is currently loaded."""
    proc_modules = _read("/proc/modules")
    if proc_modules:
        for line in proc_modules.splitlines():
            if line.split(" ", 1)[0] == module:
                return True
        return False
    # Fallback to lsmod if /proc/modules is unreadable.
    if shutil.which("lsmod"):
        try:
            out = subprocess.run(
                ["lsmod"], capture_output=True, text=True, check=False
            ).stdout
            return any(line.split(" ", 1)[0] == module for line in out.splitlines())
        except (OSError, subprocess.SubprocessError):
            return False
    return False


def list_loopback_devices() -> list[LoopbackDevice]:
    """List v4l2loopback devices currently present on the system.

    Detects loopback devices by inspecting the sysfs card name; falls back
    to listing all /dev/video* nodes if sysfs is unavailable.
    """
    devices: list[LoopbackDevice] = []
    for dev in sorted(glob.glob("/dev/video*")):
        idx = dev.replace("/dev/video", "")
        name = _read(f"/sys/class/video4linux/video{idx}/name")
        # v4l2loopback devices report the card label / "Dummy video device".
        is_loopback = (
            "loopback" in name.lower()
            or "dummy" in name.lower()
            or (DEFAULT_CARD_LABEL.lower() in name.lower())
        )
        if is_loopback:
            devices.append(LoopbackDevice(path=dev, name=name or "v4l2loopback"))
    return devices


def list_all_video_devices() -> list[str]:
    """Return every /dev/video* node present."""
    return sorted(glob.glob("/dev/video*"))


def _have_sudo() -> bool:
    """Return True if we can elevate privileges non-interactively or as root."""
    if os.geteuid() == 0:
        return True
    if not shutil.which("sudo"):
        return False
    try:
        # `sudo -n true` succeeds only if a passwordless sudo is available.
        result = subprocess.run(
            ["sudo", "-n", "true"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def modprobe_command(
    exclusive_caps: int = 1,
    label: str = DEFAULT_CARD_LABEL,
    video_nr: int | None = None,
) -> list[str]:
    """Build the ``modprobe`` command used to load v4l2loopback."""
    args = [
        "modprobe",
        "v4l2loopback",
        f"exclusive_caps={exclusive_caps}",
        f"card_label={label}",
    ]
    if video_nr is not None:
        args.append(f"video_nr={video_nr}")
    return args


def load_module(
    label: str = DEFAULT_CARD_LABEL,
    video_nr: int | None = None,
) -> tuple[bool, str]:
    """Attempt to load the v4l2loopback module.

    :returns: ``(success, message)``. When privileges are unavailable the
        message contains the exact command the user should run manually.
    """
    if is_module_loaded():
        return True, "v4l2loopback already loaded."

    cmd = modprobe_command(label=label, video_nr=video_nr)
    manual = " ".join(cmd)

    if os.geteuid() == 0:
        full = cmd
    elif _have_sudo():
        full = ["sudo"] + cmd
    else:
        return (
            False,
            "Cannot load v4l2loopback automatically (no root / passwordless "
            f"sudo). Run this manually:\n  sudo {manual}",
        )

    try:
        result = subprocess.run(full, capture_output=True, text=True, check=False)
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
        return False, f"Failed to run modprobe: {exc}"

    if result.returncode == 0:
        return True, "v4l2loopback loaded successfully."
    return (
        False,
        f"modprobe failed (exit {result.returncode}): "
        f"{result.stderr.strip() or 'unknown error'}",
    )


def unload_module() -> tuple[bool, str]:
    """Attempt to unload the v4l2loopback module."""
    if not is_module_loaded():
        return True, "v4l2loopback not loaded."

    cmd = ["modprobe", "-r", "v4l2loopback"]
    if os.geteuid() == 0:
        full = cmd
    elif _have_sudo():
        full = ["sudo"] + cmd
    else:
        return (
            False,
            "Cannot unload v4l2loopback automatically. Run:\n"
            "  sudo modprobe -r v4l2loopback",
        )

    try:
        result = subprocess.run(full, capture_output=True, text=True, check=False)
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
        return False, f"Failed to run modprobe -r: {exc}"

    if result.returncode == 0:
        return True, "v4l2loopback unloaded."
    return (
        False,
        f"Failed to unload (exit {result.returncode}): "
        f"{result.stderr.strip() or 'unknown error'}",
    )


def pick_device(preferred: str | None = None) -> str | None:
    """Choose a loopback device path.

    Returns *preferred* if it exists, otherwise the first detected
    loopback device, otherwise None.
    """
    if preferred and os.path.exists(preferred):
        return preferred
    devices = list_loopback_devices()
    if devices:
        return devices[0].path
    return None
