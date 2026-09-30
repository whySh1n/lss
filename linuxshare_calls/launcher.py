"""Open configured internet service, or start a loopback-only demonstration."""

import argparse
import asyncio
import importlib.util
import os
import secrets
import signal
import socket
import subprocess
import sys
import threading
from urllib.parse import urlsplit
import webbrowser


def service_url(value):
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
        or parsed.query
        or parsed.path not in ("", "/")
    ):
        raise ValueError(
            "Call service must be an HTTPS origin, for example https://calls.example.org"
        )
    return value.rstrip("/")


def open_call():
    """Called by GTK; return the local helper, if any, for app shutdown cleanup."""
    remote = os.environ.get("LINUXSHARE_CALL_URL", "").strip()
    if remote:
        webbrowser.open(service_url(remote), new=2)
        return None
    if importlib.util.find_spec("aiohttp") is None:
        raise RuntimeError("Install the calls extra, or configure LINUXSHARE_CALL_URL")
    return subprocess.Popen(
        [sys.executable, "-m", "linuxshare_calls.launcher", "--parent-lifeline"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def close_call(process):
    if process is None:
        return
    if process.stdin:
        process.stdin.close()
    try:
        process.wait(timeout=4)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


async def local_demo(parent_lifeline=False):
    from aiohttp import web
    from .server import Config, make_app

    loop = asyncio.get_running_loop()
    stopped = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stopped.set)
    if parent_lifeline:

        def watch():
            while os.read(0, 1):
                pass
            loop.call_soon_threadsafe(stopped.set)

        threading.Thread(target=watch, daemon=True).start()
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.setblocking(False)
    origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
    key = secrets.token_urlsafe(32)
    app = make_app(Config(origin, key, development=True))
    runner = web.AppRunner(app, access_log=None, shutdown_timeout=2)
    try:
        await runner.setup()
        await web.SockSite(runner, listener).start()
        # Fragment never reaches HTTP/access logs; the client clears it immediately.
        webbrowser.open(f"{origin}/#create={key}", new=2)
        print(
            "Local demonstration opened. Links work only on this computer.", flush=True
        )
        await stopped.wait()
    finally:
        await runner.cleanup()
        listener.close()


def main():
    parser = argparse.ArgumentParser(description="Open LinuxShare private calls")
    parser.add_argument(
        "--parent-lifeline", action="store_true", help=argparse.SUPPRESS
    )
    args = parser.parse_args()
    remote = os.environ.get("LINUXSHARE_CALL_URL", "").strip()
    if remote:
        webbrowser.open(service_url(remote), new=2)
    else:
        asyncio.run(local_demo(args.parent_lifeline))


if __name__ == "__main__":
    main()
