# LinuxShare — share your Linux screen as a virtual webcam

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://miro.medium.com/v2/resize:fit:1358/format:webp/0*nWaYk40syKdArGZM.png)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)

**LinuxShare** captures your screen (or a selected window on X11) and streams it
into a [`v4l2loopback`](https://github.com/umlaeute/v4l2loopback) virtual camera
device. That virtual camera then appears as a normal webcam inside **Microsoft
Teams, Zoom, Slack, Google Meet** and any other app that reads a V4L2 device —
so you can share your screen even in clients whose Linux screen-share is broken
or missing.

It ships in two flavours:

| | Command | Best for |
|---|---|---|
| **CLI** | `linuxshare-cli` | terminals, scripts, servers, minimal setups |
| **GUI** | `linuxshare-gui` | point-and-click monitor/window picking, tray control |

Works on both **X11** (via `ffmpeg -f x11grab`) and **Wayland** (via
`xdg-desktop-portal` + **PipeWire**).

---

## Screenshots

<!-- Add screenshots of the GUI here -->
_GUI screenshots go here._

---

## Features

- 🖥️ Share the **entire screen** or a **specific monitor**
- 🪟 Share an **individual window** (X11)
- 🔌 Feeds a **v4l2loopback** virtual camera any video app can select
- 🧭 **Auto-detects X11 vs Wayland**
- 🎛️ **CLI** with flags for display, device, framerate
- 🖼️ **GTK4 / libadwaita GUI** with monitor/window picker
- 📌 **System tray** icon (show / stop / quit)
- ⚙️ **Settings** (FPS, device, autostart) saved to `~/.config/linuxshare/config.json`
- 🧩 Clear **dependency checks** with copy-paste install commands
- 🧹 Clean shutdown — unloads the module if it loaded it

---

## Requirements

System packages:

- `v4l2loopback-dkms` — the virtual camera kernel module
- `ffmpeg` — X11 capture + encoding
- `pipewire`, `xdg-desktop-portal` — Wayland capture
- `gstreamer` + good plugins — Wayland capture pipeline
- For the GUI: `python3-gi`, `python3-gi-cairo`, `gir1.2-gtk-4.0`, `gir1.2-adw-1`

---

## Installation

### Arch Linux (AUR)

```bash
# Using an AUR helper
yay -S linux-screen-share

# Or manually from the bundled PKGBUILD
cd packaging/arch
makepkg -si
```

### Arch Linux (manual)

```bash
sudo pacman -S python python-gobject gtk4 libadwaita ffmpeg pipewire \
    xdg-desktop-portal v4l2loopback-dkms gstreamer gst-plugins-good
pip install --user .
```

### Debian / Ubuntu

```bash
sudo apt update
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 \
    ffmpeg pipewire xdg-desktop-portal v4l2loopback-dkms \
    gstreamer1.0-tools gstreamer1.0-plugins-good
pip install --user .
```

> `v4l2loopback-dkms` builds a kernel module. After install, reboot or run
> `sudo modprobe v4l2loopback` once.

---

## Quick start

### CLI

```bash
# Check everything is installed
linuxshare-cli --check

# List displays
linuxshare-cli --list-displays

# Start sharing the primary screen (Ctrl+C to stop)
linuxshare-cli

# Share a specific X11 output at 60 fps into /dev/video0
linuxshare-cli --display HDMI-1 --fps 60 --device /dev/video0
```

The tool prints which `/dev/videoN` device is in use, e.g.:

```
Sharing screen -> /dev/video0
Select 'LinuxShare Virtual Camera' as your camera in your video app.
Press Ctrl+C to stop.
```

### GUI

```bash
linuxshare-gui
```

Pick a monitor (or a window on X11), press **Start sharing**, and select the
**LinuxShare Virtual Camera** in your video app.

---

## Selecting the virtual camera in your video app

Once LinuxShare is running, open your app and pick the camera named
**“LinuxShare Virtual Camera”**:

- **Microsoft Teams** → *Settings → Devices → Camera*
- **Zoom** → *Settings → Video → Camera* (select it, then *Start Video*)
- **Slack** → *Huddle/Call → camera dropdown*
- **Google Meet** (browser) → *⋮ → Settings → Video → Camera*

If the app was already open, restart it so it re-scans video devices.

---

## Troubleshooting

**`v4l2loopback` not loading**
```bash
sudo modprobe v4l2loopback exclusive_caps=1 card_label="LinuxShare Virtual Camera"
lsmod | grep v4l2loopback   # confirm it is loaded
```
Reboot after installing `v4l2loopback-dkms` if the module fails to build for your
running kernel (the DKMS build needs the matching kernel headers).

**Wayland portal errors / no prompt appears**
Ensure a portal backend is installed and running (`xdg-desktop-portal` plus your
desktop's backend, e.g. `xdg-desktop-portal-gnome`, `-kde`, or `-wlr`).
```bash
systemctl --user status xdg-desktop-portal
```

**No video (black frame) in Teams/Zoom**
- Load the module with `exclusive_caps=1` (LinuxShare does this by default).
- Restart the video app so it re-detects the camera.
- Confirm frames are flowing: `ffplay /dev/video0`.

**GUI won't start — `PyGObject` missing**
Install the GTK bindings (see [Installation](#installation)).

More detail in [`docs/troubleshooting.md`](docs/troubleshooting.md).

---

## Documentation

- [Installation guide](docs/install.md)
- [CLI usage](docs/usage-cli.md)
- [GUI usage](docs/usage-gui.md)
- [Troubleshooting](docs/troubleshooting.md)
- Man page: `man linuxshare-cli`

---

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for how to set
up a dev environment, run the tests, and open a pull request.

```bash
pip install -e ".[dev]"
pytest tests/
```

---

## License

[MIT](LICENSE) © Tomasz Czopek
