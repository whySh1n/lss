"""Source selection, process cleanup and kernel-device validation."""
import io
import stat
import struct
import sys
import time
from unittest import mock

import pytest

from linuxshare_cli import capture, v4l2
from linuxshare_gui.capture import CaptureController
from linuxshare_gui.settings import Config, load_config, save_config


def test_window_never_uses_monitor_geometry():
    command = capture.build_x11_command(
        "/dev/video9", capture.Display("private-monitor", 1920, 1080), window_id="42")
    assert command[command.index("-window_id") + 1] == "42"
    assert "-video_size" not in command
    assert "1920x1080" not in command


@pytest.mark.parametrize("window", ["0", "-1", "no", "42; touch /tmp/bad"])
def test_invalid_window_rejected(window):
    with pytest.raises(capture.CaptureError):
        capture.build_x11_command("/dev/video9", None, window_id=window)


@pytest.mark.parametrize("fps", [-1, 0, 61, True, "30"])
def test_invalid_fps_rejected(fps):
    with pytest.raises(capture.CaptureError):
        capture.validate_options("/dev/video9", fps)


def test_missing_preferred_device_does_not_fall_back():
    with mock.patch.object(v4l2, "is_loopback_device", return_value=False), \
         mock.patch.object(v4l2, "list_loopback_devices") as listing:
        assert v4l2.pick_device("/dev/video9") is None
    listing.assert_not_called()


@pytest.mark.parametrize("driver, caps, valid", [
    (b"v4l2 loopback", 2, True), (b"uvcvideo", 2, False),
    (b"v4l2 loopback", 1, False),
])
def test_device_driver_and_output_capability(driver, caps, valid):
    def ioctl(_fd, _request, buffer, _mutate):
        buffer[:len(driver)] = driver
        struct.pack_into("=II", buffer, 84, caps, 0)
    with mock.patch("os.lstat", return_value=mock.Mock(st_mode=stat.S_IFCHR)), \
         mock.patch("os.fstat", return_value=mock.Mock(st_mode=stat.S_IFCHR)), \
         mock.patch("os.open", return_value=42), \
         mock.patch("os.close") as close, \
         mock.patch("fcntl.ioctl", side_effect=ioctl):
        assert v4l2.is_loopback_device("/dev/video9") is valid
    close.assert_called_once_with(42)


def test_settings_written_atomically_and_private(tmp_path):
    path = tmp_path / "settings.json"
    save_config(Config(fps=60), str(path))
    assert load_config(str(path)).fps == 60
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert list(tmp_path.iterdir()) == [path]


def test_shutdown_rejects_queued_start():
    controller = CaptureController()
    controller.shutdown()
    with mock.patch("linuxshare_gui.capture.is_module_loaded") as probe:
        controller.start()
    probe.assert_not_called()


def test_child_exit_transitions_to_error():
    controller = CaptureController()
    session = mock.Mock()
    session.is_running.return_value = False
    session.error_message.return_value = "backend failed"
    controller.session = session
    controller.state = controller.STATE_SHARING
    controller._watch(session)
    assert controller.state == controller.STATE_ERROR
    assert controller.session is None
    session.stop.assert_called_once()


def test_session_terminates_child_and_closes_streams():
    session = capture.CaptureSession("x11", "/dev/video9", capture.Display("test", 2, 2))
    session.command = [sys.executable, "-c", "import time; time.sleep(30)"]
    session.start()
    child = session.process
    session.stop(timeout=1)
    assert child.poll() is not None
    assert child.stdin.closed and child.stderr.closed


def test_diagnostic_buffer_is_bounded():
    session = capture.CaptureSession("x11", "/dev/video9", capture.Display("test", 2, 2))
    session._drain(io.BytesIO(b"x" * 1048576))
    assert len(session.error_message()) <= 65536


def test_start_failure_does_not_unload_global_module():
    controller = CaptureController()
    with mock.patch("linuxshare_gui.capture.is_module_loaded", return_value=True), \
         mock.patch("linuxshare_gui.capture.pick_device", return_value=None), \
         mock.patch("linuxshare_gui.capture.unload_module") as unload:
        controller.start()
    assert controller.state == controller.STATE_ERROR
    unload.assert_not_called()


def test_start_then_shutdown_race_is_serialized():
    controller = CaptureController()
    with mock.patch("linuxshare_gui.capture.is_module_loaded", return_value=True), \
         mock.patch("linuxshare_gui.capture.pick_device", return_value="/dev/video9"), \
         mock.patch("linuxshare_gui.capture.detect_session_type", return_value="x11"), \
         mock.patch("linuxshare_gui.capture._cap.CaptureSession") as factory:
        session = factory.return_value
        session.is_running.return_value = True
        controller.start(display=capture.Display("test", 2, 2))
        controller.shutdown()
        controller.start()
        time.sleep(0.15)
    factory.assert_called_once()
    assert controller.state == controller.STATE_IDLE
    assert controller.session is None


def test_parent_lifeline_eof_stops_backend(tmp_path):
    import os
    pidfile = tmp_path / "backend.pid"
    session = capture.CaptureSession("x11", "/dev/video9", capture.Display("test", 2, 2))
    session.command = [sys.executable, "-c",
                       "import os,sys,time; from pathlib import Path; "
                       "Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(30)",
                       str(pidfile)]
    session.start()
    try:
        deadline = time.monotonic() + 3
        while not pidfile.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert pidfile.exists()
        pid = int(pidfile.read_text())
        session.process.stdin.close()
        assert session.process.wait(timeout=3) == 0
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
    finally:
        session.stop()
