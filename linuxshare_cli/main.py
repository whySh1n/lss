"""Command line entry point for linuxshare-cli."""

from __future__ import annotations

import argparse
import signal
import shlex
import sys
import time

from . import __version__
from . import capture as cap
from . import dependencies as deps
from . import v4l2


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser."""
    parser = argparse.ArgumentParser(
        prog="linuxshare-cli",
        description=(
            "Share your Linux screen as a virtual webcam that Teams, Zoom, "
            "Slack, Google Meet and other apps can select."
        ),
    )
    parser.add_argument(
        "--display",
        metavar="NAME",
        help="display/output to share (default: auto-detect primary)",
    )
    parser.add_argument(
        "--device",
        metavar="/dev/videoN",
        help="v4l2loopback device to use (default: first available)",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=30,
        help="capture framerate (default: 30)",
    )
    parser.add_argument(
        "--list-displays",
        action="store_true",
        help="list available displays and exit",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="run a dependency check and exit",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"linuxshare-cli {__version__}",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="enable verbose/debug output",
    )
    return parser


def _log(verbose: bool, message: str) -> None:
    if verbose:
        print(f"[debug] {message}", file=sys.stderr)


def cmd_list_displays(session_type: str) -> int:
    """Print available displays."""
    displays = cap.list_displays(session_type)
    if not displays:
        print("No displays detected.")
        return 1
    print(f"Displays ({session_type}):")
    for d in displays:
        if d.name == "portal":
            print("  portal - selected interactively via desktop portal (Wayland)")
        else:
            tag = " [primary]" if d.primary else ""
            print(f"  {d.name} - {d.resolution} @ {d.offset}{tag}")
    return 0


def run(argv: list[str] | None = None) -> int:
    """Main program logic. Returns an exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if not 1 <= args.fps <= 60:
        parser.error("--fps must be between 1 and 60")

    session_type = cap.detect_session_type()
    _log(args.verbose, f"Detected session type: {session_type}")

    if args.list_displays:
        return cmd_list_displays(session_type)

    # Dependency check.
    results = deps.check_dependencies(
        session_type if session_type in ("x11", "wayland") else None
    )
    if args.check:
        print(deps.format_report(results))
        return 0 if not deps.missing_required(results) else 1

    missing = deps.missing_required(results)
    if missing:
        print(deps.format_report(results), file=sys.stderr)
        return 1

    if session_type not in ("x11", "wayland"):
        print(
            "Could not detect X11 or Wayland session. "
            "Set XDG_SESSION_TYPE=x11 or wayland.",
            file=sys.stderr,
        )
        return 1

    # System-wide modules are managed by the administrator, not a capture app.
    if not v4l2.is_module_loaded():
        print("Load the camera first: sudo " + shlex.join(
            v4l2.modprobe_command()), file=sys.stderr)
        return 1

    device = v4l2.pick_device(args.device)
    if not device:
        print(
            "No v4l2loopback device found. Ensure the module is loaded "
            "(sudo modprobe v4l2loopback).",
            file=sys.stderr,
        )
        return 1

    # Pick display (X11); Wayland uses the portal.
    display = None
    if session_type == "x11":
        displays = cap.list_displays_x11()
        display = cap.pick_display(displays, args.display)
        if args.display and display is None:
            print(f"Display {args.display!r} not found.", file=sys.stderr)
            return 1

    try:
        session = cap.CaptureSession(
            session_type=session_type,
            device=device,
            display=display,
            fps=args.fps,
        )
    except cap.CaptureError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    _log(args.verbose, f"Capture command: {' '.join(session.command)}")

    stop_requested = {"flag": False}

    def handle_sigint(signum, frame):  # noqa: ANN001, ARG001
        stop_requested["flag"] = True

    signal.signal(signal.SIGINT, handle_sigint)
    signal.signal(signal.SIGTERM, handle_sigint)

    try:
        session.start()
    except cap.CaptureError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if session_type == "wayland":
        print("A desktop portal prompt may ask which screen/window to share.")
    print(f"Starting capture -> {device}")
    print(f"Select '{v4l2.DEFAULT_CARD_LABEL}' as your camera in your video app.")
    print("Press Ctrl+C to stop.")

    exit_code = 0
    try:
        while not stop_requested["flag"]:
            if not session.is_running():
                # Process ended unexpectedly.
                session.stop()
                msg = session.error_message()
                print(
                    f"Capture stopped unexpectedly.{(' ' + msg) if msg else ''}",
                    file=sys.stderr,
                )
                exit_code = 1
                break
            time.sleep(0.2)
    finally:
        print("\nStopping capture...")
        session.stop()

    return exit_code


def main() -> None:
    """Console-script entry point."""
    sys.exit(run())


if __name__ == "__main__":
    main()
