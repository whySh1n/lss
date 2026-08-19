# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-08-19

### Added
- CLI tool `linuxshare-cli`:
  - Auto-detection of X11 vs Wayland via `$XDG_SESSION_TYPE`.
  - X11 capture with `ffmpeg -f x11grab`.
  - Wayland capture via `xdg-desktop-portal` + PipeWire (GStreamer pipeline).
  - Automatic `v4l2loopback` load/unload with graceful fallback messaging.
  - Flags: `--display`, `--device`, `--fps`, `--list-displays`, `--check`,
    `--version`, `--verbose`.
  - Dependency checker with distro-specific install hints.
  - Clean SIGINT/SIGTERM shutdown.
- GTK4 GUI `linuxshare-gui`:
  - Monitor picker with selectable cards.
  - X11 window list (Wayland uses the portal picker).
  - Start/stop control and status bar.
  - System tray icon (AppIndicator with graceful fallback).
  - Settings dialog (FPS, device, autostart) saved to
    `~/.config/linuxshare/config.json`.
  - About dialog.
- Packaging: Arch `PKGBUILD`, Debian packaging files.
- Documentation: README, install/usage/troubleshooting guides, man page.
- Desktop entry and SVG icon.
- Unit tests and GitHub Actions CI (tests + lint).

[Unreleased]: https://github.com/tomaszczopek/linux-screen-share/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/tomaszczopek/linux-screen-share/releases/tag/v0.1.0
