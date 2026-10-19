"""The Tejas home server. Runs on one computer; every screen in the house
(TV, laptop, phone, tablet) opens it in a browser over home Wi-Fi.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import hmac
import json
import os
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, certs
from .brain import Brain
from .config import Config, home
from .library import Library
from .llm import LLM
from .mathengine import MathEngine
from .memory import Memory
from .news import News
from .speech import VOICES, Ears, Voice
from .tools import ToolBox, parse_when, say_time

WEB = Path(__file__).parent / "web"


class Hub:
    """Pushes live events (reminders, news) to every open screen."""

    def __init__(self):
        self.queues: set[asyncio.Queue] = set()

    def publish(self, event: dict) -> None:
        for q in list(self.queues):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    async def subscribe(self):
        q: asyncio.Queue = asyncio.Queue(maxsize=50)
        self.queues.add(q)
        try:
            yield {"type": "hello", "time": time.time()}
            while True:
                try:
                    yield await asyncio.wait_for(q.get(), timeout=20)
                except asyncio.TimeoutError:
                    yield {"type": "ping"}
        finally:
            self.queues.discard(q)


class PinGuard:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.fails = 0
        self.locked_until = 0.0

    @staticmethod
    def _hash(pin: str, salt: str) -> str:
        return hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), 200_000).hex()

    def is_set(self) -> bool:
        return bool(self.cfg.get("parent.pin_hash"))

    def set(self, pin: str) -> None:
        if not (pin.isdigit() and 4 <= len(pin) <= 8):
            raise HTTPException(400, "PIN must be 4 to 8 digits")
        salt = secrets.token_hex(16)
        self.cfg.update({"parent": {"pin_hash": self._hash(pin, salt), "pin_salt": salt}})

    def check(self, pin: str | None) -> None:
        if not self.is_set():
            return  # first run: no PIN yet
        if time.time() < self.locked_until:
            raise HTTPException(429, "Too many wrong PINs. Wait a minute.")
        ok = pin and hmac.compare_digest(self._hash(pin, self.cfg.get("parent.pin_salt")), self.cfg.get("parent.pin_hash"))
        if not ok:
            self.fails += 1
            if self.fails >= 5:
                self.fails, self.locked_until = 0, time.time() + 60
            raise HTTPException(401, "Parent PIN needed")
        self.fails = 0


class ChatIn(BaseModel):
    text: str = Field(max_length=4000)
    profile_id: int | None = None
    deep: bool | None = None


class ProfileIn(BaseModel):
    name: str | None = Field(default=None, max_length=40)
    age: int | None = Field(default=None, ge=1, le=120)
    grade: str | None = Field(default=None, max_length=30)
    language: str | None = Field(default=None, max_length=12)
    interests: str | None = Field(default=None, max_length=300)
    color: str | None = Field(default=None, max_length=9)


class SpeakIn(BaseModel):
    text: str = Field(max_length=1500)
    lang: str = "en"


class ReminderIn(BaseModel):
    text: str = Field(max_length=200)
    when: str = Field(max_length=80)
    repeat: str = "none"
    profile_id: int | None = None


class PinIn(BaseModel):
    pin: str
    old_pin: str | None = None


def create_app(data_dir: Path | None = None, llm=None) -> FastAPI:
    root = data_dir or home()
    if data_dir:
        for sub in ("models", "library", "certs"):
            (root / sub).mkdir(parents=True, exist_ok=True)
    cfg = Config(root / "config.json")
    memory = Memory(root / "tejas.db")
    library = Library(root / "library")
    news = News(root / "news.json")
    math = MathEngine()
    llm = llm or LLM(cfg)
    toolbox = ToolBox(math, memory, library, news)
    brain = Brain(cfg, memory, llm, toolbox)
    ears, voice = Ears(cfg, root / "models"), Voice(cfg, root / "models")
    hub, pins = Hub(), PinGuard(cfg)
    offline = os.environ.get("TEJAS_OFFLINE") == "1"

    async def reminder_loop():
        while True:
            try:
                for r in memory.pop_due():
                    p = memory.profile(r["profile_id"]) if r["profile_id"] else None
                    who = f"{p['name']}, " if p else ""
                    hub.publish({"type": "reminder", "id": r["id"], "text": r["text"],
                                 "say": f"{who}a gentle reminder: {r['text']}.",
                                 "profile_id": r["profile_id"]})
            except Exception:
                pass
            await asyncio.sleep(5)

    async def news_loop():
        while not offline:
            res = await news.refresh()
            if res["updated"]:
                hub.publish({"type": "news_updated"})
            await asyncio.sleep(3600)

    @asynccontextmanager
    async def lifespan(app):
        tasks = [asyncio.create_task(reminder_loop()), asyncio.create_task(news_loop()),
                 asyncio.create_task(asyncio.to_thread(math.warm_up))]
        yield
        for t in tasks:
            t.cancel()
        math.close()

    app = FastAPI(title="Tejas AI", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.cfg, app.state.memory, app.state.brain = cfg, memory, brain

    @app.middleware("http")
    async def headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Permissions-Policy"] = "microphone=(self), camera=()"
        if request.url.path in ("/", "/index.html", "/sw.js"):
            resp.headers["Cache-Control"] = "no-cache"
        return resp

    # Status --------------------------------------------------------------
    @app.get("/api/status")
    async def status():
        llm_s = await llm.status()
        return {"version": __version__, "name": cfg.get("assistant.name"), "llm": llm_s,
                "ears": ears.available(), "voice": voice.available(), "voices": voice.installed(),
                "library": {"files": len(library.files())}, "parent_pin_set": pins.is_set(),
                "time": time.time()}

    # Conversation ----------------------------------------------------------
    @app.post("/api/chat")
    async def chat(body: ChatIn):
        async def gen():
            async for ev in brain.chat(body.profile_id, body.text, body.deep):
                yield json.dumps(ev, ensure_ascii=False) + "\n"
                if ev.get("type") == "action" and ev.get("action") == "reminders_changed":
                    hub.publish({"type": "reminders_changed"})
        return StreamingResponse(gen(), media_type="application/x-ndjson",
                                 headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})

    @app.post("/api/listen")
    async def listen(audio: UploadFile = File(...), language: str | None = Form(None)):
        data = await audio.read()
        if len(data) > 12_000_000:
            raise HTTPException(413, "recording too long")
        if not ears.available():
            raise HTTPException(503, "Speech recognition isn't installed on the home computer.")
        try:
            return await asyncio.to_thread(ears.transcribe, data, language)
        except Exception as e:
            raise HTTPException(500, f"Couldn't hear that ({type(e).__name__}).")

    @app.post("/api/speak")
    async def speak(body: SpeakIn):
        wav = await asyncio.to_thread(voice.speak, body.text, body.lang)
        if not wav:
            return Response(status_code=204)
        return Response(wav, media_type="audio/wav")

    @app.get("/api/voices")
    async def voices():
        return {"installed": voice.installed(), "catalog": VOICES, "selected": cfg.get("tts.voices")}

    @app.get("/api/events")
    async def events():
        async def gen():
            async for ev in hub.subscribe():
                yield f"data: {json.dumps(ev)}\n\n"
        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # Profiles ------------------------------------------------------------
    @app.get("/api/profiles")
    async def profiles():
        return memory.profiles()

    @app.post("/api/profiles")
    async def add_profile(body: ProfileIn, x_parent_pin: str | None = Header(None)):
        pins.check(x_parent_pin)
        try:
            return memory.add_profile(**body.model_dump())
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.put("/api/profiles/{pid}")
    async def edit_profile(pid: int, body: ProfileIn, x_parent_pin: str | None = Header(None)):
        pins.check(x_parent_pin)
        p = memory.update_profile(pid, **body.model_dump())
        if not p:
            raise HTTPException(404, "no such profile")
        return p

    @app.delete("/api/profiles/{pid}")
    async def del_profile(pid: int, x_parent_pin: str | None = Header(None)):
        pins.check(x_parent_pin)
        memory.delete_profile(pid)
        return {"ok": True}

    # Parent zone ---------------------------------------------------------
    @app.post("/api/parent/pin")
    async def set_pin(body: PinIn):
        if pins.is_set():
            pins.check(body.old_pin)
        pins.set(body.pin)
        return {"ok": True}

    @app.post("/api/parent/check")
    async def check_pin(body: PinIn):
        pins.check(body.pin)
        return {"ok": True}

    @app.get("/api/history/{pid}")
    async def history(pid: int, x_parent_pin: str | None = Header(None)):
        pins.check(x_parent_pin)
        return memory.history(pid)

    @app.delete("/api/history/{pid}")
    async def clear_history(pid: int, x_parent_pin: str | None = Header(None)):
        pins.check(x_parent_pin)
        memory.clear_history(pid)
        return {"ok": True}

    @app.get("/api/facts/{pid}")
    async def facts(pid: int):
        return memory.facts(pid)

    @app.delete("/api/facts/{pid}/{fid}")
    async def forget(pid: int, fid: int, x_parent_pin: str | None = Header(None)):
        pins.check(x_parent_pin)
        memory.forget(pid, fid)
        return {"ok": True}

    @app.get("/api/settings")
    async def get_settings():
        return cfg.public()

    @app.put("/api/settings")
    async def put_settings(patch: dict, x_parent_pin: str | None = Header(None)):
        pins.check(x_parent_pin)
        allowed = {"assistant", "llm", "stt", "tts"}
        clean = {k: v for k, v in patch.items() if k in allowed and isinstance(v, dict)}
        cfg.update(clean)
        return cfg.public()

    # Reminders -------------------------------------------------------------
    @app.get("/api/reminders")
    async def reminders():
        out = []
        for r in memory.reminders():
            r["when_text"] = say_time(dt.datetime.fromtimestamp(r["due"]))
            out.append(r)
        return out

    @app.post("/api/reminders")
    async def add_reminder(body: ReminderIn):
        d = parse_when(body.when)
        if not d:
            raise HTTPException(400, "I couldn't understand that time. Try '7 pm' or 'in 20 minutes'.")
        r = memory.add_reminder(body.profile_id, body.text, d.timestamp(), body.repeat)
        hub.publish({"type": "reminders_changed"})
        return {**r, "when_text": say_time(d)}

    @app.delete("/api/reminders/{rid}")
    async def del_reminder(rid: int):
        memory.delete_reminder(rid)
        hub.publish({"type": "reminders_changed"})
        return {"ok": True}

    # News & library --------------------------------------------------------
    @app.get("/api/news")
    async def get_news(topic: str = "kids"):
        return news.headlines(topic, 8)

    @app.post("/api/news/refresh")
    async def refresh_news():
        if offline:
            return {"updated": 0, "offline": True}
        return await news.refresh(force=True)

    @app.get("/api/library")
    async def lib():
        return {"files": library.files(), "folder": str(root / "library")}

    @app.post("/api/library/reindex")
    async def reindex():
        return await asyncio.to_thread(library.index)

    # Connect other screens -------------------------------------------------
    @app.get("/api/connect")
    async def connect():
        port = cfg.get("server.https_port", 8443)
        ips = certs.lan_ips()
        ca_path = root / "certs" / "tejas-home-ca.crt"
        code = certs.ca_fingerprint(ca_path) if ca_path.exists() else None
        return {"urls": [f"https://{ip}:{port}" for ip in ips], "ca": "/tejas-home-ca.crt", "code": code}

    @app.get("/api/qr.svg")
    async def qr(url: str):
        if not url.startswith("https://") or len(url) > 100:
            raise HTTPException(400, "bad url")
        import segno
        import io
        buf = io.BytesIO()
        segno.make(url, error="m").save(buf, kind="svg", scale=6, dark="#0b0b0c", light="#ffffff", border=2)
        return Response(buf.getvalue(), media_type="image/svg+xml")

    @app.get("/tejas-home-ca.crt")
    async def ca():
        p = root / "certs" / "tejas-home-ca.crt"
        if not p.exists():
            raise HTTPException(404, "no certificate yet")
        return FileResponse(p, media_type="application/x-x509-ca-cert", filename="tejas-home-ca.crt")

    @app.exception_handler(HTTPException)
    async def http_err(request, exc: HTTPException):
        return JSONResponse({"error": exc.detail}, status_code=exc.status_code)

    app.mount("/", StaticFiles(directory=str(WEB), html=True), name="web")
    return app
