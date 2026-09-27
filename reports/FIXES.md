# Review remediation — 0.1.1

The issues R1–R9 in the [baseline review](REVIEW.md) have code changes and
regression coverage. This is a remediation report, not a claim of exhaustive
security assurance or validated interoperability with every desktop.

| Finding | Remediation |
| --- | --- |
| R1: window selection shared a monitor | Picker selection passes the explicit window ID to FFmpeg `-window_id`; monitor dimensions are omitted for window capture. No source or invalid ID fails closed. Selection controls are disabled during capture. |
| R2: missing Wayland portal implementation | A dedicated helper performs CreateSession, SelectSources, Start and OpenPipeWireRemote, owns the transferred FD, and connects the authorized stream to GStreamer. Uses stream serial when supplied, otherwise node ID. Pending requests, cancellation, revocation and shutdown close the session. |
| R3: blocked output pipes | Diagnostics are continuously drained into a bounded 64 KiB buffer; unused stdout is discarded. Handles are closed and children reaped. |
| R4: unchecked device paths | Only non-symlink `/dev/videoN` character devices with the v4l2loopback kernel driver and video-output capability pass VIDIOC_QUERYCAP validation. An invalid explicit target never falls back to another device. |
| R5: stale sharing state | Controller watches child exit, publishes diagnostics, cleans up and permits restart. Consent has a separate cancellable starting state. |
| R6: malformed settings crashes | Strict field types and defaults handle malformed values; settings use atomic replacement and mode 0600. |
| R7: capture survived GUI closure | Close-request, application shutdown and Quit converge on controller shutdown, rejecting queued starts. Helpers watch parent stdin EOF and stop/reap their backend if the parent disappears. GUI handles SIGINT/SIGTERM. |
| R8: incorrect dependency checks | Actual Wayland commands, PipeWire/GStreamer elements and ScreenCast portal availability are checked. Removed unused pw-record requirement. Arch/Debian runtime dependencies include the required plugins. |
| R9: skipped archive checksums | The Arch recipe builds the trusted local checkout and downloads no release archive. Removed the unchecked remote source rather than inventing a checksum. Future downloaded release sources must carry verified checksums. |

Additional corrections: no implicit kernel-module load/unload during capture;
properly quoted manual modprobe instructions; noninteractive sudo in legacy
module helpers; FPS limited to 1–60; no fake video0 default in settings;
GTK3 AppIndicator runs in a separate helper from GTK4 and receives sharing
state updates; monitor/window selections clear each other; negative monitor
offsets parse; autostart uses the installed interpreter and opens only the UI.
Installation instructions use a venv and describe required portal backends.
The broken CI badge and unverified AUR availability claim were removed.

## Validation

- **80 tests passed**, zero expected failures. Regression cases include noisy
  subprocesses, EOF cleanup/reaping, window targeting, device driver/capability
  checks, invalid settings, restart and shutdown races, portal protocol and
  cancellation, and installer safety.
- **Private D-Bus integration passed** using real Gio, a fake portal and
  `/dev/null`: full request sequence, Unix FD transfer, session Close. It does
  not open a real desktop chooser or record anything.
- **Flake8 and compileall passed.** Bash syntax checks passed for the installer
  and Arch recipe.
- **Bandit:** 27 low findings, no medium/high findings; low findings concern
  subprocess/PATH use and explicit best-effort cleanup. Static analysis alone
  does not prove security.
- **Fresh temporary installation passed** in a path containing spaces. Installed
  entry point reports version 0.1.1. Wheel and source distribution build passed.
- CI added for Python 3.10/3.12/3.14 plus private D-Bus integration. Local Python
  was 3.14; CI execution status is separate from these local results.

Evidence: [tests](tests-after-fixes.txt), [lint](lint-after-fixes.txt),
[Bandit](bandit-after-fixes.json), [installer](install-after-fixes.txt),
[build](build-after-fixes.txt).

## Remaining validation limits

This host has no v4l2loopback module, so real camera frames, conferencing-client
compatibility and long-duration capture have not been tested. Live GTK/tray
interaction, native Arch/Debian package installation and Secure Boot/module
signing also remain unverified. Test on a disposable desktop before relying on
this release for sensitive material. X11 window capture follows FFmpeg's
window semantics, including stopping when a selected window is closed,
unmapped or shrunk beyond capture dimensions; occlusion can affect X11 pixels.
Receiving applications may retain a last frame after capture stops. Those are
platform/integration constraints rather than promises of private isolation.

The recommended future features (preview, pause/neutral frames, quality
presets, expanded diagnostics and audio) remain roadmap items, not part of
this bug-fix release.

## Installation

From this trusted checkout: `./install.sh --dry-run`, then `./install.sh`.
It installs for the current user, never loads a kernel module, and refuses
existing destinations. See [installation](../docs/install.md) for system
packages, removal and retry instructions. No changes have been made to this
machine's kernel modules, desktop configuration or installed system packages.

## Protocol references

Implementation follows the official [ScreenCast portal API](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.ScreenCast.html)
and [FFmpeg X11 capture options](https://ffmpeg.org/ffmpeg-devices.html#x11grab).
