"""Entry point for the packaged Tejas AI desktop app (PyInstaller)."""
import multiprocessing
import os
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()  # needed for the maths worker inside a packaged app
    # A windowed app on Windows has no console: give output somewhere to go (a log file),
    # otherwise libraries that print or log crash.
    if sys.stdout is None or sys.stderr is None:
        home = os.environ.get("TEJAS_AI_HOME") or os.path.join(os.path.expanduser("~"), ".tejas-ai")
        os.makedirs(home, exist_ok=True)
        log = open(os.path.join(home, "desktop.log"), "a", buffering=1, encoding="utf-8")
        sys.stdout = sys.stdout or log
        sys.stderr = sys.stderr or log
    from tejas_ai.desktop import main
    main()
