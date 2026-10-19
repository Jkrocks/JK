"""Long-term memory: who each child is, what Tejas has learned about them,
and every conversation (so parents can read them in the Parent zone)."""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  age INTEGER,
  grade TEXT,
  language TEXT DEFAULT 'en',
  interests TEXT DEFAULT '',
  color TEXT DEFAULT '#ff8a00',
  created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS facts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  text TEXT NOT NULL,
  created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  flagged TEXT,
  created REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_profile ON messages(profile_id, id);
CREATE INDEX IF NOT EXISTS idx_facts_profile ON facts(profile_id, id);
CREATE TABLE IF NOT EXISTS reminders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  profile_id INTEGER,
  text TEXT NOT NULL,
  due REAL NOT NULL,
  repeat TEXT DEFAULT 'none',
  done INTEGER DEFAULT 0,
  created REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(done, due);
"""

REPEATS = {"none": 0, "daily": 86400, "weekly": 7 * 86400}

PROFILE_FIELDS = ("name", "age", "grade", "language", "interests", "color")
MAX_FACTS = 200


class Memory:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.execute("PRAGMA journal_mode = WAL")
        self.db.executescript(SCHEMA)
        self.db.commit()

    def _q(self, sql: str, args=()):
        with self._lock:
            cur = self.db.execute(sql, args)
            self.db.commit()
            return cur

    # Profiles -----------------------------------------------------------
    def profiles(self) -> list[dict]:
        return [dict(r) for r in self._q("SELECT * FROM profiles ORDER BY id")]

    def profile(self, pid: int) -> dict | None:
        r = self._q("SELECT * FROM profiles WHERE id = ?", (pid,)).fetchone()
        return dict(r) if r else None

    def add_profile(self, **kw) -> dict:
        data = {k: kw.get(k) for k in PROFILE_FIELDS}
        if not (data["name"] or "").strip():
            raise ValueError("name is required")
        data["name"] = data["name"].strip()[:40]
        data["language"] = data["language"] or "en"
        data["interests"] = (data["interests"] or "")[:300]
        data["color"] = data["color"] or "#ff8a00"
        cur = self._q(
            "INSERT INTO profiles (name, age, grade, language, interests, color, created) VALUES (?,?,?,?,?,?,?)",
            (*[data[k] for k in PROFILE_FIELDS], time.time()),
        )
        return self.profile(cur.lastrowid)

    def update_profile(self, pid: int, **kw) -> dict | None:
        sets = {k: v for k, v in kw.items() if k in PROFILE_FIELDS and v is not None}
        if sets:
            cols = ", ".join(f"{k} = ?" for k in sets)
            self._q(f"UPDATE profiles SET {cols} WHERE id = ?", (*sets.values(), pid))
        return self.profile(pid)

    def delete_profile(self, pid: int) -> None:
        self._q("DELETE FROM profiles WHERE id = ?", (pid,))

    # Facts ("its own mind") ---------------------------------------------
    def facts(self, pid: int) -> list[dict]:
        return [dict(r) for r in self._q("SELECT id, text, created FROM facts WHERE profile_id = ? ORDER BY id", (pid,))]

    def remember(self, pid: int, text: str) -> bool:
        text = " ".join((text or "").split())[:240]
        if len(text) < 3:
            return False
        existing = {f["text"].lower() for f in self.facts(pid)}
        if text.lower() in existing:
            return False
        self._q("INSERT INTO facts (profile_id, text, created) VALUES (?,?,?)", (pid, text, time.time()))
        # Keep memory bounded: forget the oldest facts first.
        self._q(
            "DELETE FROM facts WHERE profile_id = ? AND id NOT IN (SELECT id FROM facts WHERE profile_id = ? ORDER BY id DESC LIMIT ?)",
            (pid, pid, MAX_FACTS),
        )
        return True

    def forget(self, pid: int, fact_id: int) -> None:
        self._q("DELETE FROM facts WHERE id = ? AND profile_id = ?", (fact_id, pid))

    # Conversations ------------------------------------------------------
    def add_message(self, pid: int, role: str, content: str, flagged: str | None = None) -> None:
        self._q(
            "INSERT INTO messages (profile_id, role, content, flagged, created) VALUES (?,?,?,?,?)",
            (pid, role, content, flagged, time.time()),
        )

    def recent(self, pid: int, limit: int = 16) -> list[dict]:
        rows = self._q(
            "SELECT role, content FROM messages WHERE profile_id = ? ORDER BY id DESC LIMIT ?", (pid, limit)
        ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def history(self, pid: int, limit: int = 200) -> list[dict]:
        rows = self._q(
            "SELECT id, role, content, flagged, created FROM messages WHERE profile_id = ? ORDER BY id DESC LIMIT ?",
            (pid, limit),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def clear_history(self, pid: int) -> None:
        self._q("DELETE FROM messages WHERE profile_id = ?", (pid,))

    # Reminders ----------------------------------------------------------
    def add_reminder(self, pid: int | None, text: str, due: float, repeat: str = "none") -> dict:
        text = " ".join((text or "").split())[:200]
        if not text:
            raise ValueError("reminder needs some words")
        repeat = repeat if repeat in REPEATS else "none"
        cur = self._q(
            "INSERT INTO reminders (profile_id, text, due, repeat, created) VALUES (?,?,?,?,?)",
            (pid, text, float(due), repeat, time.time()),
        )
        return dict(self._q("SELECT * FROM reminders WHERE id = ?", (cur.lastrowid,)).fetchone())

    def reminders(self, include_done: bool = False) -> list[dict]:
        sql = "SELECT * FROM reminders" + ("" if include_done else " WHERE done = 0") + " ORDER BY due"
        return [dict(r) for r in self._q(sql)]

    def delete_reminder(self, rid: int) -> None:
        self._q("DELETE FROM reminders WHERE id = ?", (rid,))

    def pop_due(self, now: float | None = None) -> list[dict]:
        """Return reminders that are due; repeat ones move to their next time."""
        now = now or time.time()
        due = [dict(r) for r in self._q("SELECT * FROM reminders WHERE done = 0 AND due <= ?", (now,))]
        for r in due:
            step = REPEATS.get(r["repeat"], 0)
            if step:
                nxt = r["due"]
                while nxt <= now:
                    nxt += step
                self._q("UPDATE reminders SET due = ? WHERE id = ?", (nxt, r["id"]))
            else:
                self._q("UPDATE reminders SET done = 1 WHERE id = ?", (r["id"],))
        return due
