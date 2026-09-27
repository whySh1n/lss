"""Tests for v4l2loopback management."""

from unittest import mock

from linuxshare_cli import v4l2


def test_is_module_loaded_true():
    proc = "v4l2loopback 40960 0 - Live 0x0\nnvidia 1000 0 - Live 0x0\n"
    with mock.patch.object(v4l2, "_read", return_value=proc):
        assert v4l2.is_module_loaded("v4l2loopback") is True


def test_is_module_loaded_false():
    proc = "nvidia 1000 0 - Live 0x0\n"
    with mock.patch.object(v4l2, "_read", return_value=proc):
        assert v4l2.is_module_loaded("v4l2loopback") is False


def test_modprobe_command_builds_args():
    cmd = v4l2.modprobe_command(label="Test Cam", video_nr=5)
    assert cmd[0] == "modprobe"
    assert "v4l2loopback" in cmd
    assert "card_label=Test Cam" in cmd
    assert "video_nr=5" in cmd
    assert "exclusive_caps=1" in cmd


def test_load_module_already_loaded():
    with mock.patch.object(v4l2, "is_module_loaded", return_value=True):
        ok, msg = v4l2.load_module()
    assert ok is True
    assert "already" in msg.lower()


def test_load_module_as_root_success():
    with (
        mock.patch.object(v4l2, "is_module_loaded", return_value=False),
        mock.patch("os.geteuid", return_value=0),
        mock.patch("subprocess.run") as run,
    ):
        run.return_value = mock.Mock(returncode=0, stderr="")
        ok, msg = v4l2.load_module()
    assert ok is True
    # Ensure sudo was NOT prefixed when already root.
    args = run.call_args[0][0]
    assert args[0] == "modprobe"


def test_load_module_with_sudo():
    with (
        mock.patch.object(v4l2, "is_module_loaded", return_value=False),
        mock.patch("os.geteuid", return_value=1000),
        mock.patch.object(v4l2, "_have_sudo", return_value=True),
        mock.patch("subprocess.run") as run,
    ):
        run.return_value = mock.Mock(returncode=0, stderr="")
        ok, _ = v4l2.load_module()
    assert ok is True
    args = run.call_args[0][0]
    assert args[0] == "sudo"


def test_load_module_no_privileges_returns_instructions():
    with (
        mock.patch.object(v4l2, "is_module_loaded", return_value=False),
        mock.patch("os.geteuid", return_value=1000),
        mock.patch.object(v4l2, "_have_sudo", return_value=False),
    ):
        ok, msg = v4l2.load_module()
    assert ok is False
    assert "sudo modprobe" in msg


def test_load_module_modprobe_failure():
    with (
        mock.patch.object(v4l2, "is_module_loaded", return_value=False),
        mock.patch("os.geteuid", return_value=0),
        mock.patch("subprocess.run") as run,
    ):
        run.return_value = mock.Mock(returncode=1, stderr="boom")
        ok, msg = v4l2.load_module()
    assert ok is False
    assert "boom" in msg


def test_unload_module_not_loaded():
    with mock.patch.object(v4l2, "is_module_loaded", return_value=False):
        ok, msg = v4l2.unload_module()
    assert ok is True


def test_unload_module_success_as_root():
    with (
        mock.patch.object(v4l2, "is_module_loaded", return_value=True),
        mock.patch("os.geteuid", return_value=0),
        mock.patch("subprocess.run") as run,
    ):
        run.return_value = mock.Mock(returncode=0, stderr="")
        ok, _ = v4l2.unload_module()
    assert ok is True
    args = run.call_args[0][0]
    assert args[:2] == ["modprobe", "-r"]


def test_pick_device_prefers_existing():
    with mock.patch.object(v4l2, "is_loopback_device", return_value=True):
        assert v4l2.pick_device("/dev/video9") == "/dev/video9"


def test_pick_device_falls_back_to_first_loopback():
    dev = v4l2.LoopbackDevice(path="/dev/video0", name="Dummy")
    with (
        mock.patch("os.path.exists", return_value=False),
        mock.patch.object(v4l2, "list_loopback_devices", return_value=[dev]),
    ):
        assert v4l2.pick_device(None) == "/dev/video0"


def test_pick_device_none_when_no_devices():
    with (
        mock.patch("os.path.exists", return_value=False),
        mock.patch.object(v4l2, "list_loopback_devices", return_value=[]),
    ):
        assert v4l2.pick_device(None) is None
