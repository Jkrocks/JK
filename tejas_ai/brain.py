"""Tejas's mind.

One turn of conversation:
  1. Safety check on what the child said.
  2. Build a picture of who is talking: their age, language, what Tejas
     remembers about them, the time, upcoming reminders.
  3. If it's a maths question, solve it exactly first (so even a tiny model
     gets the numbers right).
  4. Let the local model think and use tools (maths, reminders, timers,
     library, news, memory) for up to a few rounds.
  5. Deep mode: a second pass where Tejas checks its own work before answering.
  6. Save the conversation so parents can read it.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from typing import AsyncIterator

from . import safety
from .llm import LLMOffline, ToolsUnsupported
from .tools import ToolContext, say_time

MAX_ROUNDS = 6
MATH_LEAD = re.compile(
    r"^\s*(?:hey\s+tejas[,!]?\s*)?(?:please\s+)?(?:what(?:'s| is)|whats|calculate|compute|solve|work out|find|"
    r"how much is|tell me)\s+(?:the\s+(?:answer|value)\s+(?:of|to)\s+)?", re.I)
MATHY = re.compile(r"^[\d\s.,+\-*/^()=x×÷%a-zA-Z²³√π<>!]+$")


def looks_like_math(text: str) -> str | None:
    t = MATH_LEAD.sub("", text or "").strip().rstrip("?.! ")
    t = re.sub(r"\b(plus)\b", "+", t, flags=re.I)
    t = re.sub(r"\b(minus)\b", "-", t, flags=re.I)
    t = re.sub(r"\b(times|multiplied by|into)\b", "*", t, flags=re.I)
    t = re.sub(r"\b(divided by|by)\b", "/", t, flags=re.I)
    t = re.sub(r"\b(squared)\b", "^2", t, flags=re.I)
    t = re.sub(r"\b(cubed)\b", "^3", t, flags=re.I)
    t = re.sub(r"\bfor\s+[a-z]\b", "", t, flags=re.I).strip()
    if len(t) < 3 or len(t) > 200 or not MATHY.match(t):
        return None
    if not re.search(r"\d", t) or not re.search(r"[+\-*/^=×÷%!]|sqrt|√", t):
        return None
    letters = re.findall(r"[a-zA-Z]+", t)
    if any(len(w) > 4 and w.lower() not in {"sqrt"} for w in letters):
        return None  # it's a sentence, not an expression
    return t


class ThinkFilter:
    """Hides <think>…</think> blocks some models emit, while streaming."""

    def __init__(self):
        self.buf = ""
        self.inside = False

    def feed(self, chunk: str) -> str:
        self.buf += chunk
        out = ""
        while True:
            if self.inside:
                i = self.buf.find("</think>")
                if i < 0:
                    self.buf = self.buf[-8:]
                    return out
                self.buf = self.buf[i + 8:]
                self.inside = False
            else:
                i = self.buf.find("<think>")
                if i < 0:
                    keep = 7 if "<" in self.buf[-7:] else 0
                    if keep:
                        j = self.buf.rfind("<")
                        out += self.buf[:j]
                        self.buf = self.buf[j:]
                    else:
                        out += self.buf
                        self.buf = ""
                    return out
                out += self.buf[:i]
                self.buf = self.buf[i + 7:]
                self.inside = True

    def flush(self) -> str:
        out = "" if self.inside else self.buf
        self.buf = ""
        return out


LANG_NAMES = {"en": "English", "hi": "Hindi", "pa": "Punjabi", "hinglish": "Hinglish (Hindi in English letters)"}


class Brain:
    def __init__(self, cfg, memory, llm, toolbox):
        self.cfg, self.memory, self.llm, self.toolbox = cfg, memory, llm, toolbox
        self.tools_ok: dict[str, bool] = {}

    # Prompt ---------------------------------------------------------------
    def system_prompt(self, profile: dict | None, deep: bool) -> str:
        name = self.cfg.get("assistant.name", "Tejas")
        now = dt.datetime.now()
        p = profile or {}
        age = p.get("age")
        grown_up = age is not None and int(age) >= 18
        lang = LANG_NAMES.get(p.get("language") or "en", "English")
        lines = [
            f"You are {name}, a warm, gentle, very clever home companion. You live on this family's own computer "
            "and work without the internet. You have a kind heart: you're patient, encouraging, curious, and a "
            "little playful, like a favourite uncle or aunt who happens to know a lot.",
            "You are talking out loud. Use plain, simple words and short sentences. No long lists unless asked. "
            "Never use emojis, tables or code blocks. For maths, show the steps on separate short lines.",
            f"Reply in {lang}, unless the person speaks to you in another language; then match them.",
            f"Right now it is {now.strftime('%A %d %B %Y, %I:%M %p')}.",
        ]
        if p.get("name"):
            if grown_up:
                lines.append(f"You are talking with {p['name']}, a grown-up in the family. Be a capable, concise "
                             "assistant: help with plans, reminders, news, and solving problems.")
            else:
                desc = f"{p['name']}, who is {age} years old" if age else p["name"]
                if p.get("grade"):
                    desc += f" and in {p['grade']}"
                lines.append(f"You are talking with {desc}. Explain things at their level.")
            if p.get("interests"):
                lines.append(f"They like: {p['interests']}. Use these for examples when it helps.")
        facts = self.memory.facts(p["id"])[-25:] if p.get("id") else []
        if facts:
            lines.append("Things you remember about them:\n" + "\n".join(f"- {f['text']}" for f in facts))
        upcoming = [r for r in self.memory.reminders() if r["profile_id"] in (None, p.get("id"))][:5]
        if upcoming:
            lines.append("Upcoming reminders:\n" + "\n".join(
                f"- #{r['id']} {r['text']} ({say_time(dt.datetime.fromtimestamp(r['due']))})" for r in upcoming))
        lines += [
            "How you work:",
            "- For ANY number work, use the math tool. Never guess a calculation.",
            "- For hard problems: think it through step by step, use tools to check, then explain simply.",
            "- If you don't know something, say so honestly. Don't make things up. Your knowledge has no live "
            "internet; for today's events use get_news and say how old the headlines are.",
            "- When the person tells you something worth remembering (a favourite thing, a goal, a worry, what "
            "they're learning), save it with the remember tool.",
            "- For reminders and timers, use the tools, then confirm the time back in plain words.",
            "- Use search_library when they ask about their school books or notes.",
        ]
        if not grown_up:
            lines += [
                "Keeping children safe and happy:",
                "- Everything you say must be right for a child. No scary, violent, adult or unkind content.",
                "- Never ask for or store private details like address, school name, phone or passwords.",
                "- If they seem sad, scared or hurt, be kind, and encourage them to talk to a parent.",
                "- Celebrate effort, not just right answers.",
            ]
            if self.cfg.get("assistant.hint_first", True):
                lines.append("- Homework: first give a hint or ask a guiding question so they can try. Give the "
                             "full answer if they ask again, are stuck, or it isn't homework.")
        if deep:
            lines.append("This is a hard question. Plan your answer, check each step with tools, and be extra careful.")
        return "\n".join(lines)

    def _messages(self, profile, text, deep, notes):
        msgs = [{"role": "system", "content": self.system_prompt(profile, deep)}]
        if profile:
            msgs += [{"role": m["role"], "content": m["content"]} for m in self.memory.recent(profile["id"], 16)]
        for n in notes:
            msgs.append({"role": "system", "content": n})
        msgs.append({"role": "user", "content": text})
        return msgs

    # One turn -------------------------------------------------------------
    async def chat(self, profile_id: int | None, text: str, deep: bool | None = None) -> AsyncIterator[dict]:
        text = (text or "").strip()[:4000]
        if not text:
            yield {"type": "done", "text": ""}
            return
        if deep is None:
            deep = bool(self.cfg.get("assistant.deep_think_default", False))
        profile = self.memory.profile(profile_id) if profile_id else None
        pid = profile["id"] if profile else None

        flag, fixed = safety.check(text)
        if pid:
            self.memory.add_message(pid, "user", text, flag)
        if fixed:
            yield {"type": "token", "text": fixed}
            if pid:
                self.memory.add_message(pid, "assistant", fixed, flag)
            yield {"type": "done", "text": fixed, "flagged": flag}
            return

        notes = []
        if flag in safety.GUIDANCE:
            notes.append(safety.GUIDANCE[flag])
        expr = looks_like_math(text)
        if expr:
            res = self.toolbox.math.run(expr)
            if res.get("ok"):
                yield {"type": "tool", "name": "math", "input": expr, "result": res.get("result")}
                notes.append(f"MATHS ENGINE (exact, trust this): {expr} → {res['result']}"
                             + (f" (≈ {res['decimal']})" if res.get("decimal") else "")
                             + ". Explain how to get there in simple steps.")

        ctx = ToolContext(profile_id=pid)
        msgs = self._messages(profile, text, deep, notes)
        try:
            if deep:
                yield {"type": "stage", "stage": "thinking"}
                draft = ""
                async for ev in self._run(msgs, ctx, stream=False):
                    if ev["type"] == "final":
                        draft = ev["text"]
                    elif ev["type"] != "token":
                        yield ev
                yield {"type": "stage", "stage": "checking"}
                review = msgs + [
                    {"role": "assistant", "content": draft},
                    {"role": "user", "content": "Before you tell me: check your answer above carefully. Re-check every "
                     "number with the math tool and every fact. Fix anything wrong. Then give me the final answer only, "
                     "in plain, kind, simple words, as if speaking to me for the first time. Don't mention checking."},
                ]
                final = ""
                async for ev in self._run(review, ctx, stream=True):
                    if ev["type"] == "final":
                        final = ev["text"]
                    else:
                        yield ev
            else:
                final = ""
                async for ev in self._run(msgs, ctx, stream=True):
                    if ev["type"] == "final":
                        final = ev["text"]
                    else:
                        yield ev
        except LLMOffline as e:
            msg = str(e)
            yield {"type": "error", "text": msg}
            yield {"type": "done", "text": msg, "offline": True}
            return
        except Exception as e:
            msg = "Sorry, my thinking got tangled. Can you ask me again?"
            yield {"type": "error", "text": f"{msg} ({type(e).__name__}: {str(e)[:160]})"}
            yield {"type": "done", "text": msg}
            return

        final = safety.clean_output(final.strip()) or "Hmm, I'm not sure what to say. Can you ask another way?"
        for a in ctx.actions:
            yield {"type": "action", **a}
        if pid:
            self.memory.add_message(pid, "assistant", final, flag)
        yield {"type": "done", "text": final, "flagged": flag}

    async def _run(self, msgs: list[dict], ctx: ToolContext, stream: bool) -> AsyncIterator[dict]:
        """Model ↔ tools loop. Emits tokens (if stream), tool events, and one 'final'."""
        model = self.llm.model
        use_tools = self.tools_ok.get(model, True)
        msgs = list(msgs)
        seen = set()
        text = ""
        for round_ in range(MAX_ROUNDS):
            text, calls, tf = "", [], ThinkFilter()
            try:
                async for kind, val in self.llm.stream(msgs, self.toolbox.specs if use_tools else None):
                    if kind == "text":
                        vis = tf.feed(val)
                        text += vis
                        if stream and vis:
                            yield {"type": "token", "text": vis}
                    elif kind == "tool_calls":
                        calls = val
            except ToolsUnsupported:
                self.tools_ok[model] = use_tools = False
                continue
            tail = tf.flush()
            text += tail
            if stream and tail:
                yield {"type": "token", "text": tail}
            if not calls:
                break
            msgs.append(self.llm.assistant_msg(text, calls))
            for c in calls:
                key = (c["name"], json.dumps(c["arguments"], sort_keys=True))
                if key in seen:
                    result = {"ok": False, "error": "You already did exactly this. Use the earlier result."}
                else:
                    seen.add(key)
                    result = self.toolbox.run(c["name"], c["arguments"], ctx)
                yield {"type": "tool", "name": c["name"], "input": c["arguments"],
                       "result": result.get("result") if isinstance(result, dict) else result,
                       "ok": result.get("ok", True) if isinstance(result, dict) else True}
                msgs.append(self.llm.tool_msg(c, result))
            if stream and text:
                yield {"type": "token", "text": "\n"}
            if round_ == MAX_ROUNDS - 2:
                use_tools = False  # last round: make it answer
        yield {"type": "final", "text": text}
