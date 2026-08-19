# CLI usage

`linuxshare-cli` captures your screen into a v4l2loopback virtual camera.

## Synopsis

```
linuxshare-cli [OPTIONS]
```

## Options

| Flag | Description | Default |
|---|---|---|
| `--display NAME` | X11 output to share (e.g. `HDMI-1`). Ignored on Wayland (portal chooses). | auto / primary |
| `--device /dev/videoN` | v4l2loopback device to write to. | first loopback device |
| `--fps N` | Capture framerate. | `30` |
| `--list-displays` | List displays and exit. | — |
| `--check` | Run dependency check and exit. | — |
| `--version` | Print version and exit. | — |
| `--verbose` | Debug output on stderr. | — |
| `-h`, `--help` | Show help. | — |

## Typical workflow

1. **Check dependencies**
   ```bash
   linuxshare-cli --check
   ```

2. **See what you can share** (X11 lists outputs; Wayland shows a `portal` entry)
   ```bash
   linuxshare-cli --list-displays
   ```

3. **Start sharing**
   ```bash
   linuxshare-cli
   ```
   Output:
   ```
   Sharing screen -> /dev/video0
   Select 'LinuxShare Virtual Camera' as your camera in your video app.
   Press Ctrl+C to stop.
   ```

4. **Select the camera** in Teams/Zoom/Slack/Meet.

5. **Stop** with `Ctrl+C`. LinuxShare terminates ffmpeg/GStreamer and unloads
   the module if it loaded it.

## Examples

```bash
# Share the primary screen at default 30 fps
linuxshare-cli

# Share a specific X11 output at 60 fps into a chosen device
linuxshare-cli --display DP-1 --fps 60 --device /dev/video0

# Debug a capture problem
linuxshare-cli --verbose
```

## X11 vs Wayland

- **X11**: frames are grabbed with `ffmpeg -f x11grab`. `--display` selects the
  output geometry from `xrandr`.
- **Wayland**: capture goes through `xdg-desktop-portal` + PipeWire. A portal
  dialog asks which screen/window to share, so `--display` is not used.

## Exit status

- `0` — success
- `1` — error (missing dependency, no device, capture failure)
