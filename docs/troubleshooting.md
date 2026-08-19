# Troubleshooting

## v4l2loopback won't load

Symptoms: `linuxshare-cli` reports it can't load the module, or
`lsmod | grep v4l2loopback` shows nothing.

1. Confirm the DKMS module built for your kernel:
   ```bash
   sudo dkms status
   sudo modprobe v4l2loopback exclusive_caps=1 card_label="LinuxShare Virtual Camera"
   ```
2. If the build failed, install matching kernel headers and rebuild:
   ```bash
   # Debian/Ubuntu
   sudo apt install linux-headers-$(uname -r)
   sudo dpkg-reconfigure v4l2loopback-dkms

   # Arch
   sudo pacman -S linux-headers   # match your kernel
   ```
3. Reboot if you just updated your kernel.

### No passwordless sudo

LinuxShare tries to `modprobe` for you. If it can't elevate, it prints the exact
command to run manually:

```bash
sudo modprobe v4l2loopback exclusive_caps=1 card_label="LinuxShare Virtual Camera"
```

Run it once, then start LinuxShare again.

## Wayland portal errors

Symptoms: no "choose what to share" dialog, or a D-Bus/portal error.

1. Ensure a portal service and a backend for your desktop are installed:
   ```bash
   # GNOME
   sudo apt install xdg-desktop-portal xdg-desktop-portal-gnome
   # KDE
   sudo apt install xdg-desktop-portal xdg-desktop-portal-kde
   # wlroots (Sway, Hyprland, ...)
   sudo apt install xdg-desktop-portal xdg-desktop-portal-wlr
   ```
2. Check the service:
   ```bash
   systemctl --user status xdg-desktop-portal
   systemctl --user restart xdg-desktop-portal
   ```
3. Make sure PipeWire is running:
   ```bash
   systemctl --user status pipewire
   ```
4. Install the GStreamer PipeWire element:
   ```bash
   # Debian/Ubuntu
   sudo apt install gstreamer1.0-pipewire gstreamer1.0-plugins-good
   # Arch
   sudo pacman -S gst-plugin-pipewire gst-plugins-good
   ```

## No video (black frame) in Teams / Zoom

1. The module must be loaded with `exclusive_caps=1` (LinuxShare does this by
   default). Reload it if needed:
   ```bash
   sudo modprobe -r v4l2loopback
   sudo modprobe v4l2loopback exclusive_caps=1 card_label="LinuxShare Virtual Camera"
   ```
2. Restart the video app so it re-enumerates cameras.
3. Verify frames are flowing independently:
   ```bash
   ffplay /dev/video0
   ```
4. If you have multiple loopback devices, point LinuxShare at the right one:
   ```bash
   linuxshare-cli --device /dev/video2
   ```

## The camera isn't listed in the app

- Start LinuxShare **before** opening the video app, or restart the app.
- Some browsers require HTTPS and camera permission for Google Meet — grant
  camera access when prompted.
- Confirm the device exists: `ls -l /dev/video*` and
  `v4l2-ctl --list-devices` (from `v4l-utils`).

## GUI won't start

- `PyGObject (python-gobject) is required` → install GTK bindings
  (see [install.md](install.md)).
- No tray icon: your desktop may lack a StatusNotifier host. The app still works
  from its window; install `libappindicator`/`ayatana-appindicator` for a tray.

## X11 capture is slow or wrong size

- Pass an explicit output: `linuxshare-cli --display HDMI-1`.
- Lower the framerate: `--fps 24`.
- Check `linuxshare-cli --list-displays` to confirm geometry.

## Still stuck?

Run the dependency check and include its output when filing an issue:

```bash
linuxshare-cli --check
echo "session: $XDG_SESSION_TYPE"
```
