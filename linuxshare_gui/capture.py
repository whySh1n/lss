"""Shared capture backend for the GUI.

Wraps the CLI capture logic and adds threaded start/stop with callbacks
suitable for driving GTK status updates via ``GLib.idle_add``.
"""

from __future__ import annotations

import threading
from typing import Callable

from linuxshare_cli import capture as _cap
from linuxshare_cli import v4l2 as _v4l2

# Re-export helpers the GUI needs.
Display = _cap.Display
CaptureError = _cap.CaptureError
detect_session_type = _cap.detect_session_type
list_displays = _cap.list_displays
list_displays_x11 = _cap.list_displays_x11
list_loopback_devices = _v4l2.list_loopback_devices
pick_device = _v4l2.pick_device
is_module_loaded = _v4l2.is_module_loaded
load_module = _v4l2.load_module
unload_module = _v4l2.unload_module
DEFAULT_CARD_LABEL = _v4l2.DEFAULT_CARD_LABEL


def list_windows_x11() -> list[tuple[str, str]]:
    """List open windows under X11 using xdotool.

    :returns: list of ``(window_id, title)`` tuples. Empty if xdotool is
        unavailable or not on X11.
    """
    import shutil
    import subprocess

    if shutil.which("xdotool") is None:
        return []
    try:
        ids = subprocess.run(
            ["xdotool", "search", "--onlyvisible", "--name", ""],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return []

    windows: list[tuple[str, str]] = []
    for wid in ids:
        try:
            title = subprocess.run(
                ["xdotool", "getwindowname", wid],
                capture_output=True,
                text=True,
                check=False,
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            title = ""
        if title:
            windows.append((wid, title))
    return windows


class CaptureController:
    """High level controller wrapping a :class:`CaptureSession`.

    Runs the capture in a background thread and reports state transitions
    through callbacks. Callbacks are invoked from a worker thread; GUI
    code should marshal them onto the main loop with ``GLib.idle_add``.
    """

    STATE_IDLE = "idle"
    STATE_SHARING = "sharing"
    STATE_ERROR = "error"

    def __init__(self) -> None:
        self.session: _cap.CaptureSession | None = None
        self.device: str | None = None
        self.state = self.STATE_IDLE
        self._loaded_by_us = False
        self._lock = threading.Lock()
        self.on_state_change: Callable[[str, str], None] | None = None

    def _emit(self, state: str, message: str = "") -> None:
        self.state = state
        if self.on_state_change:
            self.on_state_change(state, message)

    def start(
        self,
        display: Display | None = None,
        fps: int = 30,
        device: str | None = None,
    ) -> None:
        """Start a capture session (ensures the module + device exist)."""
        with self._lock:
            if self.state == self.STATE_SHARING:
                return

            if not is_module_loaded():
                ok, msg = load_module()
                if not ok:
                    self._emit(self.STATE_ERROR, msg)
                    return
                self._loaded_by_us = True

            dev = pick_device(device)
            if not dev:
                self._emit(
                    self.STATE_ERROR,
                    "No v4l2loopback device found. Load the module first.",
                )
                return
            self.device = dev

            session_type = detect_session_type()
            try:
                self.session = _cap.CaptureSession(
                    session_type=session_type,
                    device=dev,
                    display=display,
                    fps=fps,
                )
                self.session.start()
            except CaptureError as exc:
                self._emit(self.STATE_ERROR, str(exc))
                return

            self._emit(self.STATE_SHARING, dev)

    def stop(self) -> None:
        """Stop the active capture session."""
        with self._lock:
            if self.session is not None:
                self.session.stop()
                self.session = None
            if self._loaded_by_us:
                unload_module()
                self._loaded_by_us = False
            self.device = None
            self._emit(self.STATE_IDLE, "")

    def is_sharing(self) -> bool:
        return self.state == self.STATE_SHARING and (
            self.session is not None and self.session.is_running()
        )
