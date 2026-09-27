# GUI usage

`linuxshare-gui` is a GTK4 / libadwaita application for point-and-click screen
sharing.

## Launch

```bash
linuxshare-gui
```

Or from your desktop's app launcher (installed as **LinuxShare**).

## Main window

- **Monitors** — a card for each connected output. Pick one to share it.
  On Wayland a single **Portal** card appears; the actual screen/window is
  chosen in the system portal prompt when you start sharing.
- **Windows** — on X11, a list of open windows you can share individually.
  On Wayland this section explains that window selection happens in the portal.
- **Start / Stop sharing** — toggles capture. While sharing, the button reads
  *Stop sharing*.
- **Status bar** — shows the current state:
  - `Idle`
  - `Sharing on /dev/video0`
  - `Error: ...`

## Tray icon

If a tray backend (AppIndicator / StatusNotifier) is available, LinuxShare adds
a tray icon with a right-click menu:

- **Show window**
- **Stop sharing**
- **Quit**

## Settings

Open **☰ → Settings**:

- **Framerate (FPS)** — 15 / 24 / 30 / 60
- **Virtual camera device** — choose which `/dev/videoN` to use
- **Start on login** — installs an autostart entry

Settings are saved to `~/.config/linuxshare/config.json` and used by the GUI. CLI options are supplied separately.

## Selecting the camera

Start sharing, then in your video app pick **LinuxShare Virtual Camera**. If the
app was already open, restart it so it re-scans cameras.

## About

**☰ → About** shows the version, license and project link.

Closing the window cancels pending consent and stops capture. Startup on login
opens the application; it never starts sharing automatically. The tray helper
is optional and uses GTK3 separately from the GTK4 UI. X11 window selection
passes an explicit FFmpeg window ID; it never falls back to the monitor.
Window occlusion may affect pixels on X11; Wayland uses portal-selected sources.
