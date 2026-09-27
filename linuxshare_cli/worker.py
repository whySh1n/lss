"""Supervise X11 capture; parent stdin EOF also stops the backend on a crash."""
import signal
import os
import subprocess
import sys
import threading


def main():
    stopped = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())

    def lifeline():
        while os.read(0, 1):
            pass
        stopped.set()

    threading.Thread(target=lifeline, daemon=True).start()
    child = subprocess.Popen(sys.argv[1:], stdin=subprocess.DEVNULL)
    try:
        while child.poll() is None and not stopped.wait(0.05):
            pass
        return child.returncode if child.returncode is not None else 0
    finally:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == "__main__":
    sys.exit(main())
