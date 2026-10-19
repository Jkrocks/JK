"""The home library: drop school books, notes or stories (txt, md, pdf) into
~/.tejas-ai/library and Tejas can look things up in them, fully offline.

Search uses BM25, a classic keyword ranking that needs no extra AI model.
"""
from __future__ import annotations

import math
import re
import threading
from collections import Counter
from pathlib import Path

WORD = re.compile(r"[a-zA-Zऀ-ॿ਀-੿0-9]+")  # Latin, Devanagari, Gurmukhi
STOP = set("a an the and or of to in on for is are was were be by with as at it this that from what which who how why when".split())
EXTS = {".txt", ".md", ".pdf"}
CHUNK = 900


def words(text: str) -> list[str]:
    return [w for w in (m.lower() for m in WORD.findall(text)) if w not in STOP and len(w) > 1]


def read_file(p: Path) -> str:
    if p.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            return ""
        try:
            return "\n".join((page.extract_text() or "") for page in PdfReader(str(p)).pages)
        except Exception:
            return ""
    try:
        return p.read_text("utf-8", errors="ignore")
    except OSError:
        return ""


def chunks(text: str) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    out, cur = [], ""
    for para in paras:
        if len(cur) + len(para) > CHUNK and cur:
            out.append(cur)
            cur = ""
        while len(para) > CHUNK * 1.5:
            out.append(para[:CHUNK])
            para = para[CHUNK:]
        cur = (cur + "\n\n" + para).strip()
    if cur:
        out.append(cur)
    return out


class Library:
    def __init__(self, folder: Path):
        self.folder = folder
        self._lock = threading.Lock()
        self.docs: list[dict] = []
        self.df: Counter = Counter()
        self.avg = 1.0
        self.index()

    def index(self) -> dict:
        docs, df = [], Counter()
        files = sorted(p for p in self.folder.rglob("*") if p.is_file() and p.suffix.lower() in EXTS)
        for f in files:
            for i, c in enumerate(chunks(read_file(f))):
                tf = Counter(words(c))
                if not tf:
                    continue
                docs.append({"file": str(f.relative_to(self.folder)), "part": i + 1, "text": c, "tf": tf,
                             "len": sum(tf.values())})
                df.update(tf.keys())
        with self._lock:
            self.docs, self.df = docs, df
            self.avg = (sum(d["len"] for d in docs) / len(docs)) if docs else 1.0
        return {"files": len(files), "chunks": len(docs)}

    def files(self) -> list[str]:
        return sorted({d["file"] for d in self.docs})

    def search(self, query: str, k: int = 3) -> list[dict]:
        q = words(query)
        if not q or not self.docs:
            return []
        n = len(self.docs)
        k1, b = 1.5, 0.75
        scored = []
        with self._lock:
            for d in self.docs:
                s = 0.0
                for w in q:
                    f = d["tf"].get(w)
                    if not f:
                        continue
                    idf = math.log(1 + (n - self.df[w] + 0.5) / (self.df[w] + 0.5))
                    s += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * d["len"] / self.avg))
                if s > 0:
                    scored.append((s, d))
        scored.sort(key=lambda t: -t[0])
        return [{"file": d["file"], "part": d["part"], "text": d["text"], "score": round(s, 2)} for s, d in scored[:k]]
