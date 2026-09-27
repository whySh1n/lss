"""Tests for capture logic and X11/Wayland detection."""

from unittest import mock
import io

import pytest

from linuxshare_cli import capture as cap

# -- Session detection ---------------------------------------------------


def test_detect_x11_from_xdg(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    assert cap.detect_session_type() == "x11"


def test_detect_wayland_from_xdg(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert cap.detect_session_type() == "wayland"


def test_detect_wayland_from_wayland_display(monkeypatch):
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.delenv("DISPLAY", raising=False)
    assert cap.detect_session_type() == "wayland"


def test_detect_x11_from_display(monkeypatch):
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("DISPLAY", ":0")
    assert cap.detect_session_type() == "x11"


def test_detect_unknown(monkeypatch):
    monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)
    assert cap.detect_session_type() == "unknown"


def test_detect_case_insensitive(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "X11")
    assert cap.detect_session_type() == "x11"


# -- xrandr parsing ------------------------------------------------------

_XRANDR = """Screen 0: minimum 320 x 200, current 3840 x 1080, maximum 16384 x 16384
HDMI-1 connected primary 1920x1080+0+0 (normal left inverted right) 509mm x 286mm
   1920x1080     60.00*+
DP-1 connected 1920x1080+1920+0 (normal left inverted right) 509mm x 286mm
   1920x1080     60.00*+
VGA-1 disconnected (normal left inverted right)
"""


def test_parse_xrandr_two_outputs():
    displays = cap._parse_xrandr(_XRANDR)
    assert len(displays) == 2
    assert displays[0].name == "HDMI-1"
    assert displays[0].primary is True
    assert displays[0].resolution == "1920x1080"
    assert displays[1].name == "DP-1"
    assert displays[1].offset == "1920,0"
    assert displays[1].primary is False


def test_pick_display_by_name():
    displays = cap._parse_xrandr(_XRANDR)
    picked = cap.pick_display(displays, "DP-1")
    assert picked.name == "DP-1"


def test_pick_display_primary_default():
    displays = cap._parse_xrandr(_XRANDR)
    picked = cap.pick_display(displays, None)
    assert picked.name == "HDMI-1"


def test_pick_display_unknown_name_returns_none():
    displays = cap._parse_xrandr(_XRANDR)
    assert cap.pick_display(displays, "NOPE") is None


def test_pick_display_empty_list():
    assert cap.pick_display([], None) is None


# -- Command building ----------------------------------------------------


def test_build_x11_command_with_display():
    d = cap.Display(name="HDMI-1", width=1920, height=1080, x=0, y=0, primary=True)
    cmd = cap.build_x11_command("/dev/video0", d, fps=30, x11_display=":0")
    assert "ffmpeg" in cmd
    assert "x11grab" in cmd
    assert "-video_size" in cmd
    assert "1920x1080" in cmd
    assert cmd[-1] == "/dev/video0"
    assert ":0+0,0" in cmd


def test_build_x11_command_without_display():
    with pytest.raises(cap.CaptureError, match="Select an available"):
        cap.build_x11_command("/dev/video1", None, fps=24, x11_display=":1")


def test_build_wayland_command_requires_gstreamer():
    with mock.patch("shutil.which", return_value=None):
        with pytest.raises(cap.CaptureError):
            cap.build_wayland_command("/dev/video0")


def test_build_wayland_command_ok():
    with mock.patch("shutil.which", return_value="/usr/bin/gst-launch-1.0"):
        cmd = cap.build_wayland_command("/dev/video0", fps=30)
    assert "linuxshare_cli.portal" in cmd
    assert "/dev/video0" in cmd


def test_build_capture_command_dispatch_x11():
    d = cap.Display(name="HDMI-1", width=1920, height=1080)
    cmd = cap.build_capture_command("x11", "/dev/video0", d, 30)
    assert "x11grab" in cmd


def test_build_capture_command_unknown_raises():
    with pytest.raises(cap.CaptureError):
        cap.build_capture_command("unknown", "/dev/video0", None, 30)


# -- CaptureSession ------------------------------------------------------


def test_capture_session_start_stop():
    d = cap.Display(name="HDMI-1", width=1920, height=1080)
    session = cap.CaptureSession("x11", "/dev/video0", d, 30)

    fake_proc = mock.Mock()
    fake_proc.stderr = io.BytesIO()
    fake_proc.stdout = None
    fake_proc.stdin = io.BytesIO()
    fake_proc.poll.return_value = None
    with mock.patch("subprocess.Popen", return_value=fake_proc) as popen:
        session.start()
        assert popen.called
        assert session.is_running() is True

    # Simulate stop.
    fake_proc.wait.return_value = 0
    session.stop()
    fake_proc.terminate.assert_called_once()
    assert session.process is None


def test_capture_session_start_failure_raises():
    session = cap.CaptureSession("x11", "/dev/video0", cap.Display("test", 640, 480), 30)
    with mock.patch("subprocess.Popen", side_effect=OSError("no ffmpeg")):
        with pytest.raises(cap.CaptureError):
            session.start()
