"""Screen capture backends for X11 and Wayland.

The capture layer builds and manages the external process (ffmpeg for
X11, GStreamer/PipeWire for Wayland) that pumps screen frames into a
v4l2loopback virtual camera device.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass


class CaptureError(RuntimeError):
    """Raised when a capture cannot be started."""


@dataclass
class Display:
    """A shareable output (monitor) or the whole desktop."""

    name: str
    width: int
    height: int
    x: int = 0
    y: int = 0
    primary: bool = False

    @property
    def resolution(self) -> str:
        return f"{self.width}x{self.height}"

    @property
    def offset(self) -> str:
        return f"{self.x},{self.y}"


def detect_session_type() -> str:
    """Detect the current display server.

    Returns ``"wayland"``, ``"x11"`` or ``"unknown"`` based on
    ``$XDG_SESSION_TYPE`` (falling back to ``$WAYLAND_DISPLAY`` /
    ``$DISPLAY``).
    """
    session = os.environ.get("XDG_SESSION_TYPE", "").strip().lower()
    if session in ("x11", "wayland"):
        return session
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    if os.environ.get("DISPLAY"):
        return "x11"
    return "unknown"


def _parse_xrandr(output: str) -> list[Display]:
    """Parse ``xrandr --query`` output into a list of Displays."""
    displays: list[Display] = []
    # Matches: "HDMI-1 connected primary 1920x1080+0+0 ..."
    line_re = re.compile(
        r"^(?P<name>\S+)\s+connected\s+(?P<primary>primary\s+)?"
        r"(?P<w>\d+)x(?P<h>\d+)\+(?P<x>\d+)\+(?P<y>\d+)"
    )
    for line in output.splitlines():
        m = line_re.match(line)
        if not m:
            continue
        displays.append(
            Display(
                name=m.group("name"),
                width=int(m.group("w")),
                height=int(m.group("h")),
                x=int(m.group("x")),
                y=int(m.group("y")),
                primary=bool(m.group("primary")),
            )
        )
    return displays


def list_displays_x11() -> list[Display]:
    """List connected outputs under X11 using xrandr."""
    if not shutil.which("xrandr"):
        return []
    try:
        out = subprocess.run(
            ["xrandr", "--query"], capture_output=True, text=True, check=False
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return _parse_xrandr(out)


def list_displays_wayland() -> list[Display]:
    """List outputs under Wayland.

    Actual output selection under Wayland is delegated to the
    xdg-desktop-portal picker at capture time, so this returns a single
    logical "portal" entry describing that behaviour.
    """
    return [
        Display(
            name="portal",
            width=0,
            height=0,
            primary=True,
        )
    ]


def list_displays(session_type: str | None = None) -> list[Display]:
    """List available displays for the given (or detected) session type."""
    session_type = session_type or detect_session_type()
    if session_type == "wayland":
        return list_displays_wayland()
    return list_displays_x11()


def pick_display(displays: list[Display], name: str | None = None) -> Display | None:
    """Pick a display by *name*, else the primary, else the first."""
    if not displays:
        return None
    if name:
        for d in displays:
            if d.name == name:
                return d
        return None
    for d in displays:
        if d.primary:
            return d
    return displays[0]


def build_x11_command(
    device: str,
    display: Display | None,
    fps: int = 30,
    x11_display: str | None = None,
) -> list[str]:
    """Build the ffmpeg command capturing an X11 screen into *device*."""
    x11_display = x11_display or os.environ.get("DISPLAY", ":0")
    if display and display.width and display.height:
        video_size = display.resolution
        grab = f"{x11_display}+{display.offset}"
    else:
        video_size = None
        grab = x11_display

    cmd = ["ffmpeg", "-loglevel", "error", "-f", "x11grab", "-framerate", str(fps)]
    if video_size:
        cmd += ["-video_size", video_size]
    cmd += ["-i", grab]
    cmd += [
        "-pix_fmt",
        "yuv420p",
        "-f",
        "v4l2",
        device,
    ]
    return cmd


def build_wayland_command(device: str, fps: int = 30) -> list[str]:
    """Build a GStreamer command for Wayland screencast into *device*.

    Uses ``pipewiresrc`` fed by the xdg-desktop-portal ScreenCast session.
    The portal will prompt the user to select a screen/window.
    """
    if not shutil.which("gst-launch-1.0"):
        raise CaptureError(
            "gst-launch-1.0 not found. Install GStreamer "
            "(Arch: gstreamer gst-plugins-good; Debian: gstreamer1.0-tools "
            "gstreamer1.0-plugins-good) for Wayland capture."
        )
    return [
        "gst-launch-1.0",
        "-e",
        "pipewiresrc",
        "!",
        "videoconvert",
        "!",
        f"video/x-raw,framerate={fps}/1,format=YUY2",
        "!",
        "v4l2sink",
        f"device={device}",
    ]


def build_capture_command(
    session_type: str,
    device: str,
    display: Display | None = None,
    fps: int = 30,
) -> list[str]:
    """Build the appropriate capture command for the session type."""
    if session_type == "wayland":
        return build_wayland_command(device, fps=fps)
    if session_type == "x11":
        return build_x11_command(device, display, fps=fps)
    raise CaptureError(
        f"Unsupported or undetected session type: {session_type!r}. "
        "Set XDG_SESSION_TYPE to 'x11' or 'wayland'."
    )


class CaptureSession:
    """Manages the lifecycle of a capture subprocess."""

    def __init__(
        self,
        session_type: str,
        device: str,
        display: Display | None = None,
        fps: int = 30,
    ) -> None:
        self.session_type = session_type
        self.device = device
        self.display = display
        self.fps = fps
        self.command = build_capture_command(session_type, device, display, fps)
        self.process: subprocess.Popen | None = None

    def start(self) -> None:
        """Start the capture subprocess."""
        if self.process is not None and self.process.poll() is None:
            raise CaptureError("Capture already running.")
        try:
            self.process = subprocess.Popen(  # noqa: S603
                self.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise CaptureError(f"Failed to start capture: {exc}") from exc

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def stop(self, timeout: float = 5.0) -> None:
        """Terminate the capture subprocess cleanly."""
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:  # pragma: no cover
                self.process.kill()
                self.process.wait()
        self.process = None
