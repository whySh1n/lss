"""Portal protocol and consent cleanup tests; no real desktop is accessed."""
import threading
from types import SimpleNamespace
from unittest import mock

import pytest

from linuxshare_cli.portal import Portal, PortalError, pipeline


class Variant:
    def __init__(self, signature, value):
        self.signature, self.value = signature, value

    def unpack(self):
        return self.value


def portal():
    instance = Portal.__new__(Portal)
    instance.GLib = SimpleNamespace(Variant=Variant, Error=RuntimeError)
    instance.Gio = SimpleNamespace(DBusCallFlags=SimpleNamespace(NONE=0),
                                   DBusSignalFlags=SimpleNamespace(NONE=0))
    instance.bus = mock.Mock()
    instance.bus.get_unique_name.return_value = ":1.99"
    instance.cancelled = threading.Event()
    instance.session = None
    instance.fd = None
    instance.closed_subscription = None
    instance.pump = mock.Mock()
    return instance


def test_request_subscribes_before_call_and_unpacks_response():
    instance = portal()

    def call(_method, parameters):
        assert instance.bus.signal_subscribe.called
        path = instance.bus.signal_subscribe.call_args.args[3]
        callback = instance.bus.signal_subscribe.call_args.args[6]
        assert parameters.unpack()[0]["handle_token"].unpack() in path
        callback(None, None, path, None, None,
                 Variant("(ua{sv})", (0, {"session_handle": "/session"})))
        return Variant("(o)", (path,))

    instance.call = call
    assert instance.request("CreateSession", "(a{sv})", (), {}) == {
        "session_handle": "/session"}
    instance.bus.signal_unsubscribe.assert_called_once()


def test_cancel_closes_pending_request():
    instance = portal()
    instance.cancelled.set()
    instance.call = lambda *_: Variant("(o)", (
        instance.bus.signal_subscribe.call_args.args[3],))
    instance.close_object = mock.Mock()
    with pytest.raises(PortalError, match="cancelled"):
        instance.request("Start", "(osa{sv})", ("/session", ""), {})
    assert instance.close_object.call_args.args[1] == "org.freedesktop.portal.Request"
    instance.bus.signal_unsubscribe.assert_called_once()


def test_portal_denial_is_not_a_valid_stream():
    instance = portal()

    def call(*_):
        args = instance.bus.signal_subscribe.call_args.args
        args[6](None, None, args[3], None, None, Variant("(ua{sv})", (1, {})))
        return Variant("(o)", (args[3],))
    instance.call = call
    with pytest.raises(PortalError, match="denied"):
        instance.request("Start", "(osa{sv})", ("/session", ""), {})


def test_open_follows_consent_sequence_and_extracts_fd():
    instance = portal()
    instance.request = mock.Mock(side_effect=[
        {"session_handle": "/session"}, {},
        {"streams": [(72, {"pipewire-serial": 123})]},
    ])
    instance.bus.call_sync.return_value = Variant("(a{sv})", ({
        "AvailableSourceTypes": 1, "AvailableCursorModes": 2},))
    fds = mock.Mock()
    fds.get.return_value = 43
    instance.bus.call_with_unix_fd_list_sync.return_value = (Variant("(h)", (0,)), fds)
    assert instance.open() == (43, 72, 123)
    assert [call.args[0] for call in instance.request.call_args_list] == [
        "CreateSession", "SelectSources", "Start"]
    options = instance.request.call_args_list[1].args[3]
    assert options["types"].unpack() == 1
    assert options["multiple"].unpack() is False
    assert "restore_token" not in options
    fds.get.assert_called_once_with(0)


def test_close_releases_fd_session_and_subscription_once():
    instance = portal()
    instance.fd = 43
    instance.session = "/session"
    instance.closed_subscription = 7
    instance.close_object = mock.Mock()
    with mock.patch("os.close") as close:
        instance.close()
        instance.close()
    close.assert_called_once_with(43)
    instance.close_object.assert_called_once_with("/session", "org.freedesktop.portal.Session")
    instance.bus.signal_unsubscribe.assert_called_once_with(7)


def test_pipeline_binds_authorized_fd_and_prefers_serial():
    command = pipeline("/dev/video9", 24, 43, 72, 123)
    assert "fd=43" in command
    assert "target-object=123" in command
    assert "path=72" not in command
    assert "videorate" in command
    assert "path=72" in pipeline("/dev/video9", 30, 43, 72)
