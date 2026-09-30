# LinuxShare — share your Linux screen as a virtual webcam

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://github.com/whySh1n/linux-screen-share/actions/workflows/test.yml/badge.svg)](https://github.com/whySh1n/linux-screen-share/actions/workflows/test.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)

**LinuxShare** offers private screen/voice calls and a separate virtual-camera mode.
The virtual-camera mode captures your screen (or a selected window on X11) and streams it
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

Capture backends are implemented for **X11** (via `ffmpeg -f x11grab`) and **Wayland** (via
`xdg-desktop-portal` + **PipeWire**).

---

## Validation status

Automated tests cover selection, consent protocol, cancellation, device checks
and process cleanup. Live compositor/camera interoperability still needs
validation; see [fix validation](reports/FIXES.md). X11 window capture follows
FFmpeg's window behavior: obscuring windows may affect captured pixels.
Use a clean desktop for sensitive material. Closing the app stops capture;
receiving apps may retain their last frame.

---

## Private browser-link calls (new in 0.2)

Open **Private screen & voice call** in LinuxShare, or run `linuxshare-call`.
Share a single-use link, approve one guest, and talk while sharing a screen.
The guest needs only a browser. **End call & revoke access** stops media and
invalidates the invitation; old links cannot reconnect.

The default launch is a **same-computer local demonstration**. Internet calls
require your own HTTPS signaling deployment and private TURN service; no public
hosting is bundled. Set `LINUXSHARE_CALL_URL` to your deployed service.
See [private calls and deployment](docs/private-calls.md) and
[security model](SECURITY.md). No product can guarantee 100% security or erase
recordings made by a recipient. Calls run in a browser tab; close/end that tab
to revoke remote access.

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
- 🧹 Stops child processes on close; leaves shared kernel modules under administrator control

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

### User-local source installation

```bash
./install.sh --dry-run
./install.sh
```

Install OS dependencies first (below). The script uses a virtual environment,
not the externally managed system Python. See [installation](docs/install.md).
The local Arch recipe can be built from `packaging/arch` in a trusted checkout
with `makepkg -si`; no AUR publication is assumed.

### Arch Linux (manual)

```bash
sudo pacman -S python python-gobject gtk4 libadwaita ffmpeg pipewire \
    xdg-desktop-portal v4l2loopback-dkms gstreamer gst-plugin-pipewire gst-plugins-base gst-plugins-good xorg-xrandr
./install.sh
```

### Debian / Ubuntu

```bash
sudo apt update
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 \
    ffmpeg pipewire xdg-desktop-portal v4l2loopback-dkms \
    gstreamer1.0-tools gstreamer1.0-pipewire gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good python3-venv x11-xserver-utils
./install.sh
```

> `v4l2loopback-dkms` builds a kernel module. After install, reboot or run
> `sudo modprobe v4l2loopback exclusive_caps=1 card_label="LinuxShare Virtual Camera"` once.

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
Starting capture -> /dev/video0
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
- Load the module with `exclusive_caps=1`.
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

[MIT](LICENSE) © LinuxShare Contributors
