"""News headlines that keep working offline.

When the home computer has internet, Tejas refreshes headlines from RSS
feeds (every hour by default) and saves them. When the internet is off, it
reads the saved headlines and says how old they are. No accounts, no
tracking: just plain RSS.
"""
from __future__ import annotations

import html
import json
import re
import time
from pathlib import Path

import httpx

try:  # Safe XML parsing (guards against malicious feeds).
    from defusedxml import ElementTree as ET
except ImportError:  # pragma: no cover
    import xml.etree.ElementTree as ET  # type: ignore

DEFAULT_FEEDS = {
    "kids": "https://feeds.bbci.co.uk/newsround/rss.xml",
    "india": "https://www.thehindu.com/news/national/feeder/default.rss",
    "world": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "science": "https://www.nasa.gov/feed/",
}
MAX_BYTES = 3_000_000


def _text(el, *names) -> str:
    for n in names:
        found = el.find(n)
        if found is not None and (found.text or "").strip():
            return found.text.strip()
    return ""


def _clean(s: str) -> str:
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return " ".join(s.split())


def parse_feed(xml_bytes: bytes, limit: int = 10) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    items = []
    atom = "{http://www.w3.org/2005/Atom}"
    nodes = root.findall(".//item") or root.findall(f".//{atom}entry")
    for it in nodes[:limit]:
        title = _clean(_text(it, "title", f"{atom}title"))
        summary = _clean(_text(it, "description", f"{atom}summary", f"{atom}content"))[:280]
        if title:
            items.append({"title": title, "summary": summary})
    return items


class News:
    def __init__(self, cache_path: Path, feeds: dict | None = None, max_age_s: int = 3600):
        self.cache_path = cache_path
        self.feeds = feeds or DEFAULT_FEEDS
        self.max_age_s = max_age_s
        self.cache = self._load()

    def _load(self) -> dict:
        try:
            return json.loads(self.cache_path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self) -> None:
        self.cache_path.write_text(json.dumps(self.cache), "utf-8")

    async def refresh(self, force: bool = False) -> dict:
        """Try to update every feed. Failures are fine: we keep old headlines."""
        updated = 0
        async with httpx.AsyncClient(timeout=8, follow_redirects=True,
                                     headers={"User-Agent": "TejasAI/1.0 (home assistant)"}) as client:
            for topic, url in self.feeds.items():
                old = self.cache.get(topic)
                if old and not force and time.time() - old.get("at", 0) < self.max_age_s:
                    continue
                try:
                    r = await client.get(url)
                    r.raise_for_status()
                    items = parse_feed(r.content[:MAX_BYTES])
                    if items:
                        self.cache[topic] = {"at": time.time(), "items": items}
                        updated += 1
                except Exception:
                    continue  # offline or feed down
        if updated:
            self._save()
        return {"updated": updated}

    def headlines(self, topic: str = "kids", count: int = 5) -> dict:
        topic = topic if topic in self.feeds else next(iter(self.feeds))
        entry = self.cache.get(topic)
        if not entry:
            return {"ok": False, "topic": topic,
                    "error": "I have no saved news yet. Connect this computer to the internet once and I'll fetch some."}
        age_h = (time.time() - entry["at"]) / 3600
        return {"ok": True, "topic": topic, "age_hours": round(age_h, 1),
                "items": entry["items"][:max(1, min(count, 10))]}
