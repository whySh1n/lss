"""Regression tests for the security/reliability review findings."""
import json
import sys
from unittest import mock


from linuxshare_cli import capture, v4l2
from linuxshare_gui import capture as gui_capture
from linuxshare_gui.settings import load_config


def test_device_rejects_regular_file(tmp_path):
    target = tmp_path / "not-a-camera"
    target.touch()
    assert v4l2.pick_device(str(target)) is None


def test_invalid_config_falls_back(tmp_path):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"fps": "bad"}))
    assert load_config(str(config)).fps == 30


def test_controller_recovers_after_child_exit():
    controller = gui_capture.CaptureController()
    controller.state = controller.STATE_SHARING
    controller.session = mock.Mock()
    controller.session.is_running.return_value = False
    with mock.patch.object(gui_capture, "is_module_loaded", return_value=True), \
         mock.patch.object(gui_capture, "pick_device", return_value="/dev/video9"), \
         mock.patch.object(gui_capture, "detect_session_type", return_value="x11"), \
         mock.patch.object(gui_capture._cap, "CaptureSession") as session:
        controller.start()
    session.assert_called_once()
    controller.shutdown()


def test_chatty_child_can_finish():
    session = capture.CaptureSession("x11", "/dev/video9", capture.Display("test", 640, 480))
    session.command = [sys.executable, "-c",
                       "import os; os.write(2, b'x' * 1048576)"]
    session.start()
    try:
        assert session.process.wait(timeout=2) == 0
    finally:
        session.stop()
