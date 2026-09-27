"""Management of the v4l2loopback virtual camera kernel module."""

from __future__ import annotations

import glob
import os
import shutil
import shlex
import stat
import re
import fcntl
import struct
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


def is_loopback_device(path: str) -> bool:
    """Verify the kernel driver through VIDIOC_QUERYCAP, not a card label."""
    if not re.fullmatch(r"/dev/video[0-9]+", path):
        return False
    fd = None
    try:
        if not stat.S_ISCHR(os.lstat(path).st_mode):
            return False
        fd = os.open(path, os.O_RDWR | os.O_NONBLOCK | os.O_NOFOLLOW)
        if not stat.S_ISCHR(os.fstat(fd).st_mode):
            return False
        capability = bytearray(104)
        # _IOR('V', 0, struct v4l2_capability), size 104 on Linux.
        fcntl.ioctl(fd, 0x80685600, capability, True)
        driver = bytes(capability[:16]).split(b"\0", 1)[0]
        caps, device_caps = struct.unpack_from("=II", capability, 84)
        effective = device_caps if caps & 0x80000000 else caps
        return driver == b"v4l2 loopback" and bool(effective & 0x00000002)
    except OSError:
        return False
    finally:
        if fd is not None:
            os.close(fd)


def list_loopback_devices() -> list[LoopbackDevice]:
    """List writable video-output devices using the v4l2loopback driver."""
    devices = []
    for dev in sorted(glob.glob("/dev/video*")):
        if is_loopback_device(dev):
            name = _read(f"/sys/class/video4linux/{os.path.basename(dev)}/name")
            devices.append(LoopbackDevice(dev, name or "v4l2loopback"))
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
    manual = shlex.join(cmd)

    if os.geteuid() == 0:
        full = cmd
    elif _have_sudo():
        full = ["sudo", "-n"] + cmd
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
        full = ["sudo", "-n"] + cmd
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
    """Never substitute another device for an explicitly requested target."""
    if preferred:
        return preferred if is_loopback_device(preferred) else None
    devices = list_loopback_devices()
    return devices[0].path if devices else None
