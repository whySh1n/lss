"""Run with: dbus-run-session -- python3 tests/portal_integration.py.

Uses a fake portal on a private bus and /dev/null as the transferred FD.
Never requests access to the real desktop or camera.
"""
import os
from pathlib import Path
import subprocess
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gi.repository import Gio, GLib  # noqa: E402
from linuxshare_cli.portal import BUS, PATH, Portal  # noqa: E402

XML = """<node><interface name='org.freedesktop.portal.ScreenCast'>
<method name='CreateSession'>
<arg type='a{sv}' direction='in'/>
<arg type='o' direction='out'/></method>
<method name='SelectSources'>
<arg type='o' direction='in'/>
<arg type='a{sv}' direction='in'/>
<arg type='o' direction='out'/></method>
<method name='Start'>
<arg type='o' direction='in'/>
<arg type='s' direction='in'/>
<arg type='a{sv}' direction='in'/>
<arg type='o' direction='out'/></method>
<method name='OpenPipeWireRemote'>
<arg type='o' direction='in'/>
<arg type='a{sv}' direction='in'/>
<arg type='h' direction='out'/></method>
<property name='AvailableSourceTypes' type='u' access='read'/>
<property name='AvailableCursorModes' type='u' access='read'/>
</interface></node>"""
SESSION_XML = """<node><interface name='org.freedesktop.portal.Session'>
<method name='Close'/></interface></node>"""
SESSION = "/org/freedesktop/portal/desktop/session/test"


def serve():
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    loop = GLib.MainLoop()

    def method(_bus, sender, _path, _iface, name, params, invocation):
        print(name, flush=True)
        if name == "Close":
            invocation.return_value(None)
            return
        if name == "OpenPipeWireRemote":
            fd = os.open("/dev/null", os.O_RDONLY)
            descriptors = Gio.UnixFDList.new()
            index = descriptors.append(fd)
            os.close(fd)
            invocation.return_value_with_unix_fd_list(GLib.Variant("(h)", (index,)), descriptors)
            return
        options = params.unpack()[-1]
        request = ("/org/freedesktop/portal/desktop/request/"
                   + sender[1:].replace(".", "_") + "/" + options["handle_token"])
        data = {}
        if name == "CreateSession":
            data["session_handle"] = GLib.Variant("s", SESSION)
        elif name == "Start":
            data["streams"] = GLib.Variant("a(ua{sv})", [(72, {
                "pipewire-serial": GLib.Variant("t", 123)})])
        invocation.return_value(GLib.Variant("(o)", (request,)))

        def respond():
            bus.emit_signal(sender, request, "org.freedesktop.portal.Request", "Response",
                            GLib.Variant("(ua{sv})", (0, data)))
            return False
        GLib.idle_add(respond)

    bus.register_object(PATH, Gio.DBusNodeInfo.new_for_xml(XML).interfaces[0],
                        method, lambda *_: GLib.Variant("u", 3), None)
    bus.register_object(SESSION, Gio.DBusNodeInfo.new_for_xml(SESSION_XML).interfaces[0],
                        method, None, None)
    bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus",
                  "org.freedesktop.DBus", "RequestName",
                  GLib.Variant("(su)", (BUS, 0)), None, Gio.DBusCallFlags.NONE, 3000, None)
    print("READY", flush=True)
    loop.run()


def client():
    server = subprocess.Popen([sys.executable, __file__, "--server"], stdout=subprocess.PIPE,
                              text=True)
    instance = None
    try:
        assert server.stdout.readline().strip() == "READY"
        instance = Portal(threading.Event())
        fd, node, serial = instance.open()
        assert (node, serial) == (72, 123)
        assert os.read(fd, 1) == b""
        instance.close()
        names = [server.stdout.readline().strip() for _ in range(5)]
        assert names == ["CreateSession", "SelectSources", "Start", "OpenPipeWireRemote", "Close"]
        print("PASS: real Gio private-bus consent sequence, Unix FD transfer, session close")
    finally:
        if instance:
            instance.close()
        server.terminate()
        server.wait(timeout=5)
        server.stdout.close()


if __name__ == "__main__":
    serve() if "--server" in sys.argv else client()
