"""Wayland capture helper: owns consent, PipeWire FD and pipeline lifetime.

Runs in a separate process so GTK and the portal never share a GLib context.
Closing stdin (the parent's lifeline) cancels pending consent and capture.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
import uuid

BUS = "org.freedesktop.portal.Desktop"
PATH = "/org/freedesktop/portal/desktop"
IFACE = "org.freedesktop.portal.ScreenCast"


class PortalError(RuntimeError):
    pass


class Portal:
    def __init__(self, cancelled):
        from gi.repository import Gio, GLib

        self.Gio, self.GLib = Gio, GLib
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.cancelled = cancelled
        self.session = None
        self.closed_subscription = None
        self.fd = None

    def call(self, method, parameters):
        return self.bus.call_sync(
            BUS, PATH, IFACE, method, parameters, None,
            self.Gio.DBusCallFlags.NONE, 10000, None,
        )

    def request(self, method, signature, args, options):
        token = "linuxshare_" + uuid.uuid4().hex
        sender = self.bus.get_unique_name()[1:].replace(".", "_")
        path = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"
        result = []
        options = dict(options, handle_token=self.GLib.Variant("s", token))

        def response(_bus, _sender, _path, _iface, _signal, value):
            result.append(value.unpack())

        subscription = self.bus.signal_subscribe(
            BUS, "org.freedesktop.portal.Request", "Response", path, None,
            self.Gio.DBusSignalFlags.NONE, response,
        )
        completed = False
        try:
            reply = self.call(method, self.GLib.Variant(signature, (*args, options)))
            if reply.unpack()[0] != path:
                raise PortalError("Portal returned an unexpected request handle")
            deadline = time.monotonic() + 120
            while not result:
                self.pump()
                if self.cancelled.is_set():
                    raise PortalError("Screen sharing cancelled or portal closed")
                if time.monotonic() >= deadline:
                    raise PortalError("Portal selection timed out")
                time.sleep(0.01)
            code, data = result[0]
            completed = True
            if code != 0:
                raise PortalError("Screen sharing cancelled or denied by the portal")
            return data
        finally:
            if not completed:
                self.close_object(path, "org.freedesktop.portal.Request")
            self.bus.signal_unsubscribe(subscription)

    def pump(self):
        context = self.GLib.MainContext.default()
        while context.pending():
            context.iteration(False)

    def open(self):
        variant = self.GLib.Variant
        data = self.request("CreateSession", "(a{sv})", (), {
            "session_handle_token": variant("s", "linuxshare_" + uuid.uuid4().hex),
        })
        self.session = data["session_handle"]
        self.closed_subscription = self.bus.signal_subscribe(
            BUS, "org.freedesktop.portal.Session", "Closed", self.session, None,
            self.Gio.DBusSignalFlags.NONE, lambda *_: self.cancelled.set(),
        )
        # Ask only for source types supported by this compositor.
        props = self.bus.call_sync(
            BUS, PATH, "org.freedesktop.DBus.Properties", "GetAll",
            variant("(s)", (IFACE,)), None,
            self.Gio.DBusCallFlags.NONE, 10000, None,
        ).unpack()[0]
        types = int(props.get("AvailableSourceTypes", 1)) & 3
        if not types:
            raise PortalError("Portal offers no monitor/window sources")
        options = {"types": variant("u", types), "multiple": variant("b", False)}
        if int(props.get("AvailableCursorModes", 0)) & 2:
            options["cursor_mode"] = variant("u", 2)
        self.request("SelectSources", "(oa{sv})", (self.session,), options)
        data = self.request("Start", "(osa{sv})", (self.session, ""), {})
        streams = data.get("streams", [])
        if len(streams) != 1:
            raise PortalError("Expected exactly one authorized stream")
        node, properties = streams[0]
        reply, descriptors = self.bus.call_with_unix_fd_list_sync(
            BUS, PATH, IFACE, "OpenPipeWireRemote",
            variant("(oa{sv})", (self.session, {})), None,
            self.Gio.DBusCallFlags.NONE, 10000, None, None,
        )
        self.fd = descriptors.get(reply.unpack()[0])
        return self.fd, node, properties.get("pipewire-serial")

    def close_object(self, path, interface):
        try:
            self.bus.call_sync(BUS, path, interface, "Close", None, None,
                               self.Gio.DBusCallFlags.NONE, 2000, None)
        except self.GLib.Error:
            # Already closed/revoked sessions need no further cleanup.
            return

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        if self.closed_subscription is not None:
            self.bus.signal_unsubscribe(self.closed_subscription)
            self.closed_subscription = None
        if self.session:
            self.close_object(self.session, "org.freedesktop.portal.Session")
            self.session = None


def pipeline(device, fps, fd, node, serial=None):
    target = f"target-object={int(serial)}" if serial is not None else f"path={int(node)}"
    return ["gst-launch-1.0", "-q", "-e", "pipewiresrc", f"fd={fd}", target,
            "!", "videoconvert", "!", "videorate", "!",
            f"video/x-raw,framerate={fps}/1,format=YUY2", "!", "v4l2sink",
            f"device={device}", "sync=false"]


def main():
    cancelled = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: cancelled.set())
    signal.signal(signal.SIGINT, lambda *_: cancelled.set())

    def lifeline():
        while os.read(0, 1):
            pass
        cancelled.set()

    threading.Thread(target=lifeline, daemon=True).start()
    portal = None
    child = None
    try:
        from .capture import validate_options
        device, fps = sys.argv[1], int(sys.argv[2])
        validate_options(device, fps)
        portal = Portal(cancelled)
        fd, node, serial = portal.open()
        if cancelled.is_set():
            return 1
        child = subprocess.Popen(pipeline(device, fps, fd, node, serial),
                                 pass_fds=(fd,), stdin=subprocess.DEVNULL)
        print("LINUXSHARE_READY", flush=True)
        while child.poll() is None and not cancelled.is_set():
            portal.pump()
            time.sleep(0.05)
        return child.returncode if child.returncode is not None else 0
    except Exception as exc:
        print(f"Wayland capture failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        if portal is not None:
            portal.close()


if __name__ == "__main__":
    sys.exit(main())
