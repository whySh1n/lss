"""Run GTK3 AppIndicator in a helper, isolated from the GTK4 application."""
from __future__ import annotations

import subprocess
import sys
import threading


class TrayIcon:
    def __init__(self, on_show, on_stop, on_quit, icon_name="linuxshare"):
        from gi.repository import GLib

        self._actions = {"show": on_show, "stop": on_stop, "quit": on_quit}
        self._idle_add = GLib.idle_add
        self._process = subprocess.Popen(
            [sys.executable, "-m", "linuxshare_gui.tray_helper", icon_name],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True,
        )
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        with self._process.stdout as stream:
            for line in stream:
                action = self._actions.get(line.strip())
                if action:
                    self._idle_add(self._dispatch, action)

    @staticmethod
    def _dispatch(action):
        action()
        return False

    @property
    def available(self):
        return self._process.poll() is None

    def set_sharing(self, sharing):
        if self.available:
            try:
                self._process.stdin.write("sharing\n" if sharing else "idle\n")
                self._process.stdin.flush()
            except (BrokenPipeError, OSError):
                self.close()

    def close(self):
        try:
            self._process.stdin.close()
        except (BrokenPipeError, OSError):
            pass  # Helper already exited.
        if self.available:
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
