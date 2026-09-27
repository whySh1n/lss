# LinuxShare project review

**Historical baseline review.** Findings below describe the original commit.
See [FIXES.md](FIXES.md) for the remediation and current validation results.

Date: 2026-09-27. Reviewed commit: `0b3449cbabb634f5a27fb173bffe500283ac9b23`.

## Verdict

A small, readable prototype with useful separation between capture, device
management and UI. It is **not ready for sensitive screen sharing or a release
claiming working Wayland and isolated window capture**. The original unit tests
pass, but miss important privacy and process-lifecycle behavior. This review
adds an installer, safety tests and defect reproductions; it does not fix the
application findings below.

## Findings, in priority order

| ID / priority | Evidence | Impact and recommended action |
| --- | --- | --- |
| R1 / High, privacy | `linuxshare_gui/picker.py:104` stores a window ID, but `linuxshare_gui/window.py:88` only reads and forwards the selected display. | Selecting a window can capture the previously selected monitor instead. Disable this option until actual window capture is implemented; never silently fall back to a larger source. Require an explicit source preview. Confirmed by code tracing; no private screen was captured. |
| R2 / High, functionality | `linuxshare_cli/capture.py:165` launches bare `pipewiresrc`; there is no portal session creation, source selection, Start request or remote FD handoff anywhere in the capture path. | The promised Wayland screen/window chooser is not implemented. Implement the portal lifecycle and pass the authorized PipeWire connection and node to the pipeline, including cancellation and session closure. Until then, explicitly report Wayland unsupported. |
| R3 / Medium, availability | `linuxshare_cli/capture.py:232` pipes stdout and stderr but never drains them while running. CLI only reads stderr after the child exits. | A noisy child fills a pipe and stalls indefinitely. Reproduced with a harmless Python child writing 1 MiB to stderr. Drain continuously with bounded diagnostics; discard unused stdout and close handles on cleanup. |
| R4 / Medium, device safety | `linuxshare_cli/v4l2.py:183` accepts any existing preferred path and silently falls back when it is missing. | Device selection does not enforce a character device or loopback driver. A regular file is accepted in the reproduction; downstream tools determine whether writing succeeds. Reject non-loopback targets and fail explicitly for a missing requested device. Card-label substring matching is also not reliable driver identification. |
| R5 / Medium, reliability | `linuxshare_gui/capture.py:91` returns early whenever state is `sharing`, even if the child has died. There is no child-exit monitor. | GUI can retain a false sharing status and refuse to restart. Reproduced with a stopped mock child. Watch process exit, publish errors, clean up resources and transition to idle/error. |
| R6 / Medium, reliability | `linuxshare_gui/settings.py:42` catches JSON parsing errors but not the subsequent `int(...)` conversion. | Valid JSON containing `{"fps":"bad"}` crashes settings loading. Reproduced. Validate field types and catch conversion failures; write configuration atomically. |
| R7 / High, privacy risk needing live verification | `linuxshare_gui/app.py:87` cleans up only through its custom Quit action. No close-request/shutdown cleanup is registered; capture uses an independent Popen child. | Closing the last window may leave capture running after the GUI exits. Add unconditional application-shutdown cleanup, synchronize in-flight start/stop and verify both titlebar close and process termination. This is a code-review risk, not a demonstrated live-screen leak. |
| R8 / Medium, setup correctness | `linuxshare_cli/dependencies.py:32,41` requires unused `pw-record` but calls GStreamer optional. Packaging omits a required PipeWire GStreamer plugin dependency. | Dependency checks may pass without the pipeline tools/plugins or fail for an unused tool. Check actual GStreamer elements, portal backend, module, device permissions and selected backend. |
| R9 / Medium, supply chain | `packaging/arch/PKGBUILD:28` uses `sha256sums=('SKIP')`. | Release archives are not checksum verified by the package recipe. Publish immutable versioned releases and verified checksums; exercise Arch/Debian package builds in CI. |

Additional issues: kernel-module cleanup is not guaranteed on all controller
startup failures; unloading the global module can affect other consumers;
manual modprobe instructions lose quoting around the default card label;
GTK4 tray code depends on removed `Gtk.Menu`, so its implemented path cannot
produce the advertised menu. The settings device list falls back to video0
without verifying it is virtual. CLI FPS is unrestricted. These deserve
follow-up after the release blockers.

## Security assessment

Positive observations: reviewed subprocess calls use argument lists rather
than `shell=True`; status markup is escaped; no application network listener,
telemetry client, credential store, or direct upload code was found in the
reviewed Python modules. Screen delivery is through a local video device.
This does not isolate the feed from other local processes with device access.

Bandit 1.9.4 reported **21 low-severity findings, zero medium/high** across
1,344 counted code lines. Findings concern subprocess usage, PATH resolution
and swallowed exceptions. Manual review found higher-impact privacy issues
that this scanner cannot detect. No confirmed remote code-execution issue was
found; that is not a security certification. Do not run the entire app as root
or grant blanket passwordless sudo to make capture work. Keep OS multimedia
packages patched and use narrowly scoped device/module administration.

Scope excludes a full OS/package CVE inventory, dependency provenance audit,
fuzzing, exploitation testing, and network behavior of conferencing clients.
The CLI declares no third-party Python runtime requirements; native FFmpeg,
GTK, GStreamer, PipeWire and kernel dependencies still carry security risk.

## Tests performed

Environment: Omarchy (Arch derivative), Python 3.14.7. Tools installed in a
temporary virtual environment; no system packages installed or module loaded.

| Check | Result |
| --- | --- |
| Original pytest suite | 42 passed |
| Expanded suite | 48 passed, 4 strict expected failures (R3–R6) |
| Flake8 7.4.1, single worker | Passed, no findings |
| Python compileall | Passed |
| Bandit | 21 low findings; raw JSON retained |
| Bash syntax and installer dry run | Passed |
| Installer safety tests | Six passes: dry run, invalid arguments, existing file and dangling symlink preservation |
| Real user-local install in `/tmp/linuxshare install review` | Passed; installed CLI reports version 0.1.0 |
| Repeated install destination | Correctly refused overwrite |
| Wheel and source distribution | Both built successfully; setuptools warns about deprecated license metadata |
| System GTK4 bindings | Import succeeded |
| Runtime `--check` | Missing v4l2loopback module; live capture unavailable |

Expected failures deliberately assert desired behavior and expose unfixed
bugs. They must not be interpreted as working features. They are strict, so a
future fix requires removing the marker. The pipe test starts only a synthetic
child process and always terminates it.

Not performed: real X11/Wayland capture, GUI interaction, camera output in
Teams/Zoom/Meet, long-duration performance, Secure Boot/module signing,
Debian/Ubuntu installation, or native distribution package builds. No screen
contents were recorded or transmitted. Passing the build/unit suite does not
validate desktop integration. Live testing should first use a disposable
session containing no private content.

Evidence files: [tests.txt](tests.txt), [lint.txt](lint.txt),
[bandit.json](bandit.json), [install-test.txt](install-test.txt),
[build.txt](build.txt). Reproduce with `python -m pytest -q`,
`flake8 -j 1 linuxshare_cli linuxshare_gui tests`, and
`bandit -r linuxshare_cli linuxshare_gui` after installing the relevant tools.

## Installer delivered

Run `./install.sh --dry-run` to inspect paths, then `./install.sh` to install
under `~/.local`. A custom absolute prefix is supported. It uses a Python venv
with distro GTK bindings, installs this checkout, tests the CLI entry point,
and creates two launchers. It rejects root execution and existing target
files/symlinks. It does not elevate privileges, modify desktop/kernel settings,
or start sharing. OS dependencies remain a separate prerequisite documented
in `docs/install.md`. Build tools require network access to the package index.
A failed install leaves its environment for inspection rather than recursively
deleting directories. This is an installation helper, not an updater or an
atomic package manager. The source checkout should be trusted.

## Recommended feature roadmap

1. **Release blockers:** real portal integration; fail-closed source selection;
   verified loopback devices; accurate process state; stop on every shutdown
   path; bounded log draining. Add regression tests and disposable-desktop
   integration tests covering selection, cancellation, source loss and close.
2. **Privacy controls:** preview of the exact outgoing frame, persistent sharing
   indicator, a clearly accessible emergency stop, and pause that emits a
   neutral frame. Verify what receivers see after stopping (including cached
   last frames). Make login startup open the UI without automatically sharing.
3. **Guided diagnostics:** `--doctor` with JSON output and clear checks for
   portal backend, GStreamer plugins, matching kernel headers, module signing,
   video permissions and device contention. Add an explicit camera chooser.
4. **Quality controls:** 720p/1080p profiles, FPS limits, aspect-preserving scale,
   cursor visibility and measured CPU/latency statistics. Handle monitor
   disconnects and resolution changes by stopping safely and asking again.
5. **Distribution quality:** CI across supported Python versions, wheel/sdist
   installation smoke tests, distro package jobs, checksummed releases,
   GTK4-compatible status indicator, and accurate capability documentation.

Audio sharing and session presets could follow, but should have their own
explicit consent and privacy controls. First make the currently advertised
screen-sharing behavior accurate and dependable.

## Primary reference

The official [XDG ScreenCast portal specification](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.ScreenCast.html)
defines CreateSession, SelectSources, Start and OpenPipeWireRemote. Comparing
that lifecycle with the local capture implementation supports R2. PipeWire's
[GStreamer source implementation](https://github.com/PipeWire/pipewire/blob/master/src/gst/gstpipewiresrc.c)
exposes connection/target properties; launching the element alone does not
implement the application's portal consent workflow.
