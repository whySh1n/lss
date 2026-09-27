"""Installer argument and destination safety checks (no pip/network)."""
import os
from pathlib import Path
import subprocess

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "install.sh"
pytestmark = pytest.mark.skipif(os.geteuid() == 0, reason="User-only installer")


def run(*args):
    return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True,
                          text=True, check=False)


def test_dry_run_does_not_create_prefix(tmp_path):
    prefix = tmp_path / "path with spaces"
    assert run("--prefix", str(prefix), "--dry-run").returncode == 0
    assert not prefix.exists()


@pytest.mark.parametrize("args", [("--prefix",), ("--prefix", "relative"),
                                  ("--unknown",)])
def test_invalid_arguments(args):
    assert run(*args).returncode == 2


def test_existing_launcher_preserved(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    target = bindir / "linuxshare-cli"
    target.write_text("keep me")
    assert run("--prefix", str(tmp_path)).returncode == 1
    assert target.read_text() == "keep me"


def test_broken_symlink_preserved(tmp_path):
    libdir = tmp_path / "lib"
    libdir.mkdir()
    target = libdir / "linuxshare-venv"
    target.symlink_to(tmp_path / "missing")
    assert run("--prefix", str(tmp_path)).returncode == 1
    assert target.is_symlink()
