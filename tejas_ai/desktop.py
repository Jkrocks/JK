"""Tejas AI desktop app (Windows, macOS, Linux).

A small control window that:
  - runs the Tejas home server in the background,
  - checks the brain (Ollama + model), ears (Whisper) and voice (Piper),
  - downloads what's missing in one click (needs internet once),
  - opens Tejas in its own app window, and shows the address for phones and TVs.
"""
from __future__ import annotations

import asyncio
import multiprocessing
import os
import shutil
import socket
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

from . import __version__, certs, setup
from .config import Config, home

def log(msg: str) -> None:
    """Startup diary in ~/.tejas-ai/desktop.log, to help fix problems on a family's computer."""
    import datetime
    try:
        with open(home() / "desktop.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")
    except OSError:
        pass


BG, PANEL, EDGE, TEXT, DIM, MINT, GOLD, BAD = "#050b0b", "#0f1d1b", "#1d3330", "#e9f2f0", "#8ea6a1", "#74f0c9", "#e8c88a", "#ff7b72"


def port_busy(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def find_app_browser() -> str | None:
    """Edge or Chrome can show Tejas as a clean app window (with working microphone)."""
    cands = []
    if sys.platform == "win32":
        for base in (os.environ.get("PROGRAMFILES(X86)", ""), os.environ.get("PROGRAMFILES", ""), os.environ.get("LOCALAPPDATA", "")):
            cands += [Path(base) / "Microsoft/Edge/Application/msedge.exe", Path(base) / "Google/Chrome/Application/chrome.exe"]
    elif sys.platform == "darwin":
        cands += [Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                  Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
                  Path("/Applications/Chromium.app/Contents/MacOS/Chromium")]
    else:
        for n in ("google-chrome", "chromium", "chromium-browser", "microsoft-edge"):
            p = shutil.which(n)
            if p:
                cands.append(Path(p))
    return next((str(c) for c in cands if c.exists()), None)


def open_app_window(url: str) -> None:
    exe = find_app_browser()
    if exe:
        profile = home() / "app-window"
        profile.mkdir(exist_ok=True)
        subprocess.Popen([exe, f"--app={url}", f"--user-data-dir={profile}", "--window-size=1440,900",
                          "--no-first-run", "--no-default-browser-check"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        webbrowser.open(url)


class ServerThread(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.urls = {"local": "http://localhost:8000", "lan": []}
        self.error: str | None = None
        self.ready = threading.Event()
        self.servers = []

    def run(self):
        from .__main__ import make_servers, serve
        try:
            log(f"server thread starting (python {sys.version.split()[0]}, frozen={getattr(sys, 'frozen', False)})")
            cfg = Config()
            if port_busy(cfg.get("server.http_port", 8000)):
                log("port already in use: using the Tejas that is already running")
                self.urls["lan"] = [f"https://{ip}:{cfg.get('server.https_port', 8443)}" for ip in certs.lan_ips()]
                self.ready.set()  # already running (started elsewhere): just use it
                return
            self.servers, self.urls = make_servers()
            log(f"servers created: {self.urls}")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            task = loop.create_task(serve(self.servers))
            loop.call_later(1.5, self.ready.set)
            loop.run_until_complete(task)
        except Exception as e:  # show it in the window instead of crashing
            import traceback
            log("server error:\n" + traceback.format_exc())
            self.error = f"{type(e).__name__}: {e}"
            self.ready.set()

    def stop(self):
        for s in self.servers:
            s.should_exit = True


def run_gui(root) -> None:
    import tkinter as tk
    from tkinter import ttk

    server = ServerThread()
    server.start()

    root.title("Tejas AI")
    root.configure(bg=BG)
    root.geometry("720x720")
    root.minsize(700, 660)
    icon = Path(__file__).parent / "web" / "icons" / "icon-192.png"
    try:
        root.iconphoto(True, tk.PhotoImage(file=str(icon)))
    except Exception:
        pass
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("T.Horizontal.TProgressbar", troughcolor=PANEL, background=MINT, bordercolor=EDGE,
                    lightcolor=MINT, darkcolor=MINT)

    def label(parent, text, size=11, color=TEXT, bold=False, **kw):
        return tk.Label(parent, text=text, bg=kw.pop("bg", BG), fg=color,
                        font=("Segoe UI" if sys.platform == "win32" else "Helvetica", size, "bold" if bold else "normal"),
                        anchor="w", justify="left", **kw)

    def button(parent, text, cmd, primary=False):
        b = tk.Button(parent, text=text, command=cmd, relief="flat", bd=0, padx=16, pady=9, cursor="hand2",
                      bg=MINT if primary else PANEL, fg="#06201a" if primary else TEXT,
                      activebackground=GOLD, activeforeground="#06201a", highlightthickness=0,
                      font=("Segoe UI" if sys.platform == "win32" else "Helvetica", 11, "bold"))
        return b

    head = tk.Frame(root, bg=BG)
    head.pack(fill="x", padx=24, pady=(22, 6))
    label(head, "Tejas AI", 20, bold=True).pack(anchor="w")
    label(head, f"Your family's offline companion · V{__version__}", 10, DIM).pack(anchor="w")

    card = tk.Frame(root, bg=PANEL, highlightbackground=EDGE, highlightthickness=1)
    card.pack(fill="x", padx=24, pady=12)
    rows = {}
    for key, title in (("server", "Home server"), ("engine", "Thinking engine (Ollama)"), ("brain", "Brain model"),
                       ("ears", "Ears (speech recognition)"), ("voice", "Voice")):
        r = tk.Frame(card, bg=PANEL)
        r.pack(fill="x", padx=16, pady=7)
        label(r, title, 11, bg=PANEL).pack(side="left")
        v = label(r, "…", 11, DIM, bg=PANEL)
        v.pack(side="right")
        rows[key] = v

    msg = label(root, "", 10, DIM, wraplength=540)
    msg.pack(fill="x", padx=24)
    bar = ttk.Progressbar(root, style="T.Horizontal.TProgressbar", mode="determinate", maximum=1.0)
    bar.pack(fill="x", padx=24, pady=(6, 10))

    btns = tk.Frame(root, bg=BG)
    btns.pack(fill="x", padx=24, pady=4)
    open_btn = button(btns, "Open Tejas", lambda: open_app_window(server.urls["local"]), primary=True)
    open_btn.pack(side="left")
    setup_btn = button(btns, "Download brain, ears & voice", lambda: start_setup())
    setup_btn.pack(side="left", padx=8)
    ollama_btn = button(btns, "1. Get Ollama", lambda: webbrowser.open(setup.ollama_download_url()), primary=True)
    quit_btn = button(btns, "Quit Tejas", lambda: quit_all())
    quit_btn.pack(side="right")

    online = tk.Frame(root, bg=BG)
    online.pack(fill="x", padx=24, pady=(10, 0))
    online_lbl = label(online, "", 10, DIM, wraplength=540)
    online_lbl.pack(fill="x")
    obtns = tk.Frame(online, bg=BG)
    obtns.pack(fill="x", pady=(6, 0))
    key_link = button(obtns, "Get a free key", lambda: webbrowser.open(setup.GROQ_KEYS_PAGE))
    key_link.pack(side="left")
    key_btn = button(obtns, "Paste key", lambda: ask_key(), primary=True)
    key_btn.pack(side="left", padx=8)
    off_btn = button(obtns, "Go fully offline", lambda: go_offline())

    def ask_key():
        from tkinter import simpledialog
        key = simpledialog.askstring("Free online brain",
                                     "Paste your Groq key (it starts with gsk_):", parent=root, show="•")
        if not key or not key.strip():
            return
        msg.config(text="Checking the key…")

        def work():
            problem = setup.check_groq_key(key)
            if problem:
                root.after(0, lambda: msg.config(text=problem))
                return
            setup.use_groq(key)
            log("online brain switched on")
            root.after(0, lambda: (msg.config(text="Online brain is on. Open Tejas and say hi!"), refresh_once()))
        threading.Thread(target=work, daemon=True).start()

    def go_offline():
        setup.use_offline()
        msg.config(text="Fully offline: Tejas now thinks with Ollama on this computer.")
        refresh_once()

    phone = tk.Frame(root, bg=BG)
    phone.pack(fill="x", padx=24, pady=(14, 0))
    qr_label = tk.Label(phone, bg=BG, bd=0)
    qr_label.pack(side="left", padx=(0, 16))
    lan = label(phone, "", 10, DIM, wraplength=330)
    lan.pack(side="left", fill="x", expand=True)
    qr_state = {"url": None, "img": None}
    label(root, "Closing this window keeps Tejas running (it just tucks away). Use Quit Tejas to stop it.", 9, DIM,
          wraplength=540).pack(fill="x", padx=24, side="bottom", pady=14)

    state = {"busy": False}

    def mark(key, ok, text):
        rows[key].config(text=("✓ " if ok else "• ") + text, fg=MINT if ok else (GOLD if ok is None else BAD))

    def refresh():
        cfg = Config()
        model, whisper = cfg.get("llm.model"), cfg.get("stt.model", "small")
        if server.error:
            mark("server", False, "error")
            msg.config(text=server.error)
        else:
            mark("server", server.ready.is_set() or None, "running" if server.ready.is_set() else "starting")
        if setup.online_brain():
            mark("engine", True, "Groq (online, free)")
            mark("brain", True, cfg.get("llm.model"))
            local_ears = setup.whisper_ready(whisper)
            mark("ears", True, f"Whisper {whisper}" if local_ears else "Groq Whisper (online)")
            mark("voice", True if setup.voices_ready() else None, "ready" if setup.voices_ready() else "using device voice")
            ollama_btn.pack_forget()
            setup_btn.config(state="disabled" if state["busy"] or not setup.ollama_installed() else "normal")
            online_lbl.config(text="Using the free online brain. Questions go to Groq over the internet.")
            key_btn.config(text="Change key")
            if not off_btn.winfo_ismapped():
                off_btn.pack(side="left")
            if not state["busy"] and (not msg.cget("text") or msg.cget("text").startswith("Step")):
                msg.config(text="Ready. Open Tejas and say hi!")
            phone_and_repeat()
            return
        online_lbl.config(text="No Ollama yet, or want it faster? Use a free online brain: get a free Groq key, then paste it.")
        key_btn.config(text="Paste key")
        off_btn.pack_forget()
        installed = setup.ollama_installed()
        running = setup.ollama_running() or (installed and setup.start_ollama())
        mark("engine", running, "running" if running else ("installed, not running" if installed else "not installed"))
        have = setup.ollama_models() if running else []
        has_model = any(m in (model, f"{model}:latest") for m in have)
        mark("brain", has_model, model if has_model else f"{model} needed")
        mark("ears", setup.whisper_ready(whisper), f"Whisper {whisper}" if setup.whisper_ready(whisper) else "not downloaded")
        mark("voice", True if setup.voices_ready() else None, "ready" if setup.voices_ready() else "using device voice")
        if installed:
            ollama_btn.pack_forget()
        elif not ollama_btn.winfo_ismapped():
            ollama_btn.pack(side="left", before=open_btn, padx=(0, 8))
            if not state["busy"]:
                msg.config(text="Quickest start: get a free key and paste it below. Or, for fully offline: install Ollama (step 1).")
        ready_all = has_model and setup.whisper_ready(whisper) and setup.voices_ready()
        setup_btn.config(state="disabled" if (state["busy"] or ready_all or not installed) else "normal")
        if ready_all and not state["busy"]:
            msg.config(text="Everything is ready. Tejas works with no internet.")
        elif installed and not state["busy"] and not has_model:
            msg.config(text=f"Step 2: download the brain ({model}), ears and voice. Needs internet once (~5 GB).")
        phone_and_repeat()

    def refresh_once():
        state["once"] = True
        refresh()

    def phone_and_repeat():
        if server.urls["lan"]:
            ca = home() / "certs" / "tejas-home-ca.crt"
            code = f"\nPairing code for the phone and TV apps:  {certs.ca_fingerprint(ca)}" if ca.exists() else ""
            lan.config(text="iPhone: point the Camera at this code, then follow the steps on the screen.\n\n"
                            "Or type on any phone, tablet or TV on your Wi-Fi:\n" + "\n".join(server.urls["lan"]) + code)
            url = server.urls["lan"][0]
            if qr_state["url"] != url:
                try:
                    import io
                    import segno
                    buf = io.BytesIO()
                    segno.make(url + "/#iphone", error="m").save(buf, kind="png", scale=5, border=2, dark="#06201a", light="#ffffff")
                    qr_state["img"] = tk.PhotoImage(data=buf.getvalue())
                    qr_label.config(image=qr_state["img"])
                    qr_state["url"] = url
                except Exception as e:
                    log(f"QR code failed: {e}")
        if state.pop("once", False):
            return
        if not state["busy"]:
            root.after(4000, refresh)

    def progress(text, frac):
        def ui():
            msg.config(text=text)
            if frac is None:
                bar.config(mode="indeterminate")
                bar.start(12)
            else:
                bar.stop()
                bar.config(mode="determinate", value=frac)
        root.after(0, ui)

    def start_setup():
        state["busy"] = True
        setup_btn.config(state="disabled")

        def work():
            try:
                setup.full_setup(progress)
                progress("All done! Tejas can now think, listen and talk offline.", 1.0)
            except Exception as e:
                progress(f"Couldn't finish: {e}. Check the internet and try again.", 0)
            finally:
                state["busy"] = False
                root.after(500, refresh)
        threading.Thread(target=work, daemon=True).start()

    def quit_all():
        server.stop()
        root.after(300, root.destroy)

    def on_close():
        # Closing the panel must not switch Tejas off: the family is still using it on the TV and phones.
        log("panel closed: Tejas keeps running")
        root.iconify()

    root.protocol("WM_DELETE_WINDOW", on_close)

    def first_open():
        if server.ready.is_set():
            if not server.error:
                open_app_window(server.urls["local"])
        else:
            root.after(500, first_open)

    root.after(300, refresh)
    root.after(800, first_open)
    root.mainloop()


def main() -> None:
    multiprocessing.freeze_support()
    log(f"Tejas AI desktop {__version__} starting on {sys.platform}")
    try:
        import tkinter as tk
        root = tk.Tk()
    except Exception:  # no tkinter or no screen: run as a plain server and open the browser
        from .__main__ import main as cli
        sys.argv = sys.argv[:1]
        threading.Timer(2.0, lambda: open_app_window("http://localhost:8000")).start()
        cli()
        return
    run_gui(root)


if __name__ == "__main__":
    main()
