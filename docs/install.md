# Installation guide

LinuxShare targets **Arch Linux** and **Debian/Ubuntu**, on both X11 and
Wayland sessions. It needs a few system packages (kernel module, ffmpeg,
PipeWire, GTK bindings) plus the Python package itself.

## 1. System dependencies

### Arch Linux

```bash
sudo pacman -S python python-gobject gtk4 libadwaita \
    ffmpeg pipewire xdg-desktop-portal v4l2loopback-dkms \
    gstreamer gst-plugin-pipewire gst-plugins-base gst-plugins-good xorg-xrandr
```

Optional (recommended):

```bash
sudo pacman -S xdotool xorg-xrandr libappindicator-gtk3
```

### Debian / Ubuntu

```bash
sudo apt update
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 \
    ffmpeg pipewire xdg-desktop-portal v4l2loopback-dkms \
    gstreamer1.0-tools gstreamer1.0-pipewire gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good python3-venv x11-xserver-utils
```

Optional (recommended):

```bash
sudo apt install xdotool x11-xserver-utils gir1.2-ayatanaappindicator3-0.1
```

## 2. The v4l2loopback module

`v4l2loopback-dkms` builds a kernel module against your running kernel. Make
sure your kernel headers are installed:

```bash
# Debian/Ubuntu
sudo apt install linux-headers-$(uname -r)

# Arch
sudo pacman -S linux-headers   # or linux-lts-headers, etc.
```

Load it once as an administrator (LinuxShare does not load or unload modules):

```bash
sudo modprobe v4l2loopback exclusive_caps=1 card_label="LinuxShare Virtual Camera"
```

To load it automatically at boot, create `/etc/modules-load.d/v4l2loopback.conf`
containing `v4l2loopback`, and options in
`/etc/modprobe.d/v4l2loopback.conf`:

```
options v4l2loopback exclusive_caps=1 card_label="LinuxShare Virtual Camera"
```

## 3. Install LinuxShare

### From source (any distro)

```bash
git clone https://github.com/whySh1n/linux-screen-share.git
cd linux-screen-share
./install.sh
```

### Arch (PKGBUILD)

```bash
cd packaging/arch
makepkg -si
```

### Editable/dev install

```bash
pip install -e ".[dev]"
```

## 4. Verify

```bash
linuxshare-cli --check
```

All required entries should read `found`. If any are missing, the report prints
the exact install command for your distro.

## User-local installer

From a trusted checkout, run:

```bash
./install.sh --dry-run
./install.sh
~/.local/bin/linuxshare-cli --check
```

The script installs this checkout into `~/.local/lib/linuxshare-venv`, with
launchers in `~/.local/bin`. Add that bin directory to your PATH if necessary.
Use `--prefix /absolute/path` to choose another destination. Python 3.10+,
venv and pip are required (Debian/Ubuntu: `python3-venv`). Build dependencies
are downloaded from the Python package index. Distro GTK bindings are exposed
through `--system-site-packages`; this environment is not a security sandbox.
System dependencies above must be installed separately. The script does not
use sudo, load kernel modules, start capture, configure login startup, or add
a desktop menu entry. It refuses existing destinations, including symlinks.
If installation fails, it leaves the environment for inspection; remove that
specific environment before retrying. To uninstall, remove the two installed
launcher symlinks and the `lib/linuxshare-venv` directory under your chosen
prefix. Do not remove the entire prefix.

See [fix validation](../reports/FIXES.md) for the automated results and remaining
live compositor/camera test requirements. Install the portal backend matching
your desktop (GNOME, KDE, Hyprland, or wlroots); the generic portal package
alone is insufficient. The optional tray uses a separate GTK3 process and
requires AppIndicator or Ayatana AppIndicator bindings.
