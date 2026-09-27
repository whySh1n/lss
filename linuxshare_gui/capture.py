"""Shared capture backend for the GUI.

Wraps the CLI capture logic and adds threaded start/stop with callbacks
suitable for driving GTK status updates via ``GLib.idle_add``.
"""

from __future__ import annotations

import threading
import time
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
    STATE_STARTING = "starting"
    STATE_SHARING = "sharing"
    STATE_ERROR = "error"

    def __init__(self) -> None:
        self.session: _cap.CaptureSession | None = None
        self.device: str | None = None
        self.state = self.STATE_IDLE
        self._lock = threading.RLock()
        self._closed = False
        self.on_state_change: Callable[[str, str], None] | None = None

    def _emit(self, state: str, message: str = "") -> None:
        self.state = state
        if self.on_state_change:
            self.on_state_change(state, message)

    def start(self, display=None, fps=30, device=None, window_id=None) -> None:
        with self._lock:
            if self._closed or (self.session and self.session.is_running()):
                return
            self._cleanup()
            try:
                if not is_module_loaded():
                    raise CaptureError(
                        "Load the camera first: sudo modprobe v4l2loopback "
                        "exclusive_caps=1 card_label='LinuxShare Virtual Camera'"
                    )
                dev = pick_device(device)
                if not dev:
                    raise CaptureError("No writable, verified loopback output device")
                self.device = dev
                self.session = _cap.CaptureSession(
                    detect_session_type(), dev, display, fps, window_id=window_id,
                )
                self._emit(self.STATE_STARTING, "Waiting for capture/portal consent")
                self.session.start()
            except (CaptureError, OSError) as exc:
                self._cleanup()
                self._emit(self.STATE_ERROR, str(exc))
                return
            threading.Thread(target=self._watch, args=(self.session,),
                             daemon=True).start()

    def _watch(self, session):
        while True:
            with self._lock:
                if self.session is not session:
                    return
                if not session.is_running():
                    session.stop()
                    message = session.error_message() or "Capture process exited"
                    self.session = None
                    self.device = None
                    self._emit(self.STATE_ERROR, message)
                    return
                if self.state == self.STATE_STARTING and session.ready.is_set():
                    self._emit(self.STATE_SHARING, self.device or "")
            time.sleep(0.1)

    def _cleanup(self):
        if self.session is not None:
            self.session.stop()
            self.session = None
        self.device = None

    def stop(self) -> None:
        with self._lock:
            self._cleanup()
            self._emit(self.STATE_IDLE)

    def shutdown(self) -> None:
        """Permanently reject queued starts before stopping the current child."""
        with self._lock:
            self._closed = True
            self._cleanup()
            self._emit(self.STATE_IDLE)

    def is_sharing(self) -> bool:
        with self._lock:
            return self.state in (self.STATE_STARTING, self.STATE_SHARING)
