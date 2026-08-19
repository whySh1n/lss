# Contributing to LinuxShare

Thanks for your interest in improving LinuxShare! This document explains how to
set up a development environment, run the tests, and submit changes.

## Development environment

Requires Python 3.10+.

```bash
git clone https://github.com/whySh1n/linux-screen-share.git
cd linux-screen-share

python -m venv .venv
source .venv/bin/activate

# Install the project plus dev tools (pytest, flake8, black)
pip install -e ".[dev]"
```

For GUI work you also need the system GTK bindings, which cannot be installed
from PyPI:

```bash
# Debian/Ubuntu
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1

# Arch
sudo pacman -S python-gobject gtk4 libadwaita
```

> The unit tests are designed to run **without** GTK or real hardware — they
> mock all subprocess and system calls — so CI runs them on a headless runner.

## Running the tests

```bash
pytest tests/
```

## Linting and formatting

```bash
black --check .
flake8 .
```

Run `black .` (without `--check`) to auto-format before committing.

## Commit message format

Use short, imperative present-tense subjects, optionally with a scope prefix:

```
cli: handle missing DISPLAY gracefully
gui: add FPS selector to settings dialog
docs: expand Wayland troubleshooting
```

Keep the subject ≤ 72 characters. Add a body explaining *why* when the change
is non-trivial.

## Pull request checklist

- [ ] `pytest tests/` passes
- [ ] `black --check .` and `flake8 .` pass
- [ ] New behaviour is covered by tests where practical
- [ ] Docs / man page / README updated if user-facing behaviour changed
- [ ] `CHANGELOG.md` updated under the *Unreleased* section

## Reporting bugs

Open an issue including:

- Distro and version
- `echo $XDG_SESSION_TYPE` (X11 or Wayland)
- Output of `linuxshare-cli --check`
- Steps to reproduce and what you expected
