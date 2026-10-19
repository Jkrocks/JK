"""Entry point for the packaged Tejas AI desktop app (PyInstaller)."""
import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()  # needed for the maths worker inside a packaged app
    from tejas_ai.desktop import main
    main()
