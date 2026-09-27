"""Tests for the dependency checker."""

from unittest import mock

from linuxshare_cli import dependencies as deps


def test_command_exists_true():
    with mock.patch("shutil.which", return_value="/usr/bin/ffmpeg"):
        assert deps.command_exists("ffmpeg") is True


def test_command_exists_false():
    with mock.patch("shutil.which", return_value=None):
        assert deps.command_exists("nope") is False


def test_module_available_true():
    with (
        mock.patch("shutil.which", return_value="/usr/bin/modinfo"),
        mock.patch("subprocess.run") as run,
    ):
        run.return_value = mock.Mock(returncode=0)
        assert deps.module_available("v4l2loopback") is True


def test_module_available_missing_modinfo():
    with mock.patch("shutil.which", return_value=None):
        assert deps.module_available("v4l2loopback") is False


def test_module_available_returncode_nonzero():
    with (
        mock.patch("shutil.which", return_value="/usr/bin/modinfo"),
        mock.patch("subprocess.run") as run,
    ):
        run.return_value = mock.Mock(returncode=1)
        assert deps.module_available("v4l2loopback") is False


def test_check_dependencies_all_found():
    with (
        mock.patch.object(deps, "command_exists", return_value=True),
        mock.patch.object(deps, "module_available", return_value=True),
    ):
        results = deps.check_dependencies("x11")
    assert all(r.found for r in results)
    assert deps.missing_required(results) == []


def test_check_dependencies_missing_required():
    def fake_exists(cmd):
        return cmd != "ffmpeg"

    with (
        mock.patch.object(deps, "command_exists", side_effect=fake_exists),
        mock.patch.object(deps, "module_available", return_value=True),
    ):
        results = deps.check_dependencies("x11")
    missing = deps.missing_required(results)
    assert any(m.name == "ffmpeg" for m in missing)


def test_missing_module_is_required():
    with (
        mock.patch.object(deps, "command_exists", return_value=True),
        mock.patch.object(deps, "module_available", return_value=False),
    ):
        results = deps.check_dependencies("wayland")
    missing = deps.missing_required(results)
    assert any(m.name == "v4l2loopback" for m in missing)


def test_format_report_contains_install_hints():
    with (
        mock.patch.object(deps, "command_exists", return_value=False),
        mock.patch.object(deps, "module_available", return_value=False),
    ):
        results = deps.check_dependencies("x11")
    report = deps.format_report(results)
    assert "pacman -S" in report
    assert "apt install" in report
    assert "MISSING" in report


def test_session_specific_commands_x11_vs_wayland():
    with (
        mock.patch.object(deps, "command_exists", return_value=True),
        mock.patch.object(deps, "module_available", return_value=True),
    ):
        x11 = {r.name for r in deps.check_dependencies("x11")}
        way = {r.name for r in deps.check_dependencies("wayland")}
    assert "xrandr" in x11
    assert "gst-launch-1.0" in way
    assert "pipewiresrc" in way
    assert "pw-record" not in way
