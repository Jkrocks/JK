"""Everything Tejas can *do*, beyond talking.

Each tool has a JSON schema the local model sees (Ollama/OpenAI tool format)
and a Python function that runs it. Results go back to the model, and some
also send an "action" to the screens (timers, reminders).
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field

UNITS = {
    # length (metre)
    "mm": ("len", 0.001), "cm": ("len", 0.01), "m": ("len", 1.0), "km": ("len", 1000.0),
    "in": ("len", 0.0254), "inch": ("len", 0.0254), "ft": ("len", 0.3048), "foot": ("len", 0.3048),
    "feet": ("len", 0.3048), "yd": ("len", 0.9144), "mile": ("len", 1609.344), "mi": ("len", 1609.344),
    # mass (kilogram)
    "mg": ("mass", 1e-6), "g": ("mass", 0.001), "kg": ("mass", 1.0), "tonne": ("mass", 1000.0),
    "lb": ("mass", 0.45359237), "pound": ("mass", 0.45359237), "oz": ("mass", 0.028349523125),
    # volume (litre)
    "ml": ("vol", 0.001), "l": ("vol", 1.0), "litre": ("vol", 1.0), "liter": ("vol", 1.0),
    "cup": ("vol", 0.24), "tsp": ("vol", 0.005), "tbsp": ("vol", 0.015), "gallon": ("vol", 3.785411784),
    # time (second)
    "s": ("time", 1.0), "sec": ("time", 1.0), "second": ("time", 1.0), "min": ("time", 60.0),
    "minute": ("time", 60.0), "h": ("time", 3600.0), "hr": ("time", 3600.0), "hour": ("time", 3600.0),
    "day": ("time", 86400.0), "week": ("time", 604800.0), "year": ("time", 31557600.0),
    # speed (m/s)
    "m/s": ("speed", 1.0), "km/h": ("speed", 1 / 3.6), "kmph": ("speed", 1 / 3.6), "mph": ("speed", 0.44704),
    # area (m²)
    "m2": ("area", 1.0), "cm2": ("area", 1e-4), "km2": ("area", 1e6), "acre": ("area", 4046.8564224),
    "hectare": ("area", 10000.0), "sqft": ("area", 0.09290304),
}
TEMPS = {"c", "celsius", "f", "fahrenheit", "k", "kelvin"}


def _unit(u: str) -> str:
    u = (u or "").strip().lower().replace("²", "2").replace(" ", "")
    u = {"metre": "m", "meter": "m", "metres": "m", "meters": "m", "kilometre": "km", "kilometer": "km",
         "kilometres": "km", "kilometers": "km", "centimetre": "cm", "centimeter": "cm", "centimetres": "cm",
         "centimeters": "cm", "millimetre": "mm", "millimeter": "mm", "grams": "g", "gram": "g",
         "kilogram": "kg", "kilograms": "kg", "kilo": "kg", "kilos": "kg", "pounds": "lb", "lbs": "lb",
         "litres": "l", "liters": "l", "millilitre": "ml", "milliliter": "ml", "inches": "inch",
         "miles": "mile", "seconds": "second", "minutes": "minute", "mins": "min", "hours": "hour",
         "hrs": "hr", "days": "day", "weeks": "week", "years": "year", "cups": "cup", "gallons": "gallon",
         "°c": "c", "°f": "f", "degc": "c", "degf": "f", "acres": "acre", "hectares": "hectare"}.get(u, u)
    return u


def convert_units(value: float, from_unit: str, to_unit: str) -> dict:
    a, b = _unit(from_unit), _unit(to_unit)
    try:
        v = float(value)
    except (TypeError, ValueError):
        return {"ok": False, "error": "value must be a number"}
    if a in TEMPS and b in TEMPS:
        c = {"c": v, "celsius": v, "f": (v - 32) * 5 / 9, "fahrenheit": (v - 32) * 5 / 9,
             "k": v - 273.15, "kelvin": v - 273.15}[a]
        out = {"c": c, "celsius": c, "f": c * 9 / 5 + 32, "fahrenheit": c * 9 / 5 + 32,
               "k": c + 273.15, "kelvin": c + 273.15}[b]
    elif a in UNITS and b in UNITS and UNITS[a][0] == UNITS[b][0]:
        out = v * UNITS[a][1] / UNITS[b][1]
    else:
        return {"ok": False, "error": f"I can't convert {from_unit} to {to_unit}."}
    nice = f"{out:.6g}"
    return {"ok": True, "result": f"{v:g} {from_unit} = {nice} {to_unit}"}


WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def parse_when(text: str, now: dt.datetime | None = None) -> dt.datetime | None:
    """Understand plain times: 'in 10 minutes', '7 pm', 'tomorrow at 7:30',
    'friday 6pm', '2026-10-21 08:00'."""
    now = now or dt.datetime.now()
    t = (text or "").strip().lower()
    if not t:
        return None
    try:
        return dt.datetime.fromisoformat(t.replace("t", " ", 1) if re.match(r"\d{4}-", t) else "x")
    except ValueError:
        pass
    m = re.search(r"(?:in|after)\s+(\d+(?:\.\d+)?)\s*(second|sec|minute|min|hour|hr|day|week)s?", t)
    if m:
        n, u = float(m.group(1)), m.group(2)
        secs = {"second": 1, "sec": 1, "minute": 60, "min": 60, "hour": 3600, "hr": 3600,
                "day": 86400, "week": 604800}[u]
        return now + dt.timedelta(seconds=n * secs)
    if re.search(r"\bhalf an hour\b", t):
        return now + dt.timedelta(minutes=30)
    day = now.date()
    if "tomorrow" in t:
        day = day + dt.timedelta(days=1)
    else:
        for i, wd in enumerate(WEEKDAYS):
            if wd in t:
                ahead = (i - now.weekday()) % 7 or 7
                day = day + dt.timedelta(days=ahead)
                break
    hour = minute = None
    ampm = r"(?P<ap>am|pm|a\.m\.|p\.m\.|o'?clock)"
    m = re.search(r"\b(?P<h>\d{1,2})(?::|\.)(?P<m>\d{2})\s*" + ampm + "?", t) or \
        re.search(r"\b(?P<h>\d{1,2})\s*" + ampm, t) or \
        re.fullmatch(r"(?:at\s+)?(?P<h>\d{1,2})", t) or re.search(r"\bat\s+(?P<h>\d{1,2})\b", t)
    if m:
        g = m.groupdict()
        hour = int(g["h"])
        minute = int(g["m"]) if g.get("m") else 0
        ap = g.get("ap")
        if ap and ap.startswith("p") and hour < 12:
            hour += 12
        if ap and ap.startswith("a") and hour == 12:
            hour = 0
    elif "morning" in t:
        hour, minute = 8, 0
    elif "afternoon" in t:
        hour, minute = 15, 0
    elif "evening" in t:
        hour, minute = 18, 0
    elif "night" in t:
        hour, minute = 20, 0
    elif "noon" in t:
        hour, minute = 12, 0
    if hour is None:
        if day != now.date():
            hour, minute = 9, 0
        else:
            return None
    if not (0 <= hour < 24 and 0 <= minute < 60):
        return None
    when = dt.datetime.combine(day, dt.time(hour, minute))
    if when <= now and day == now.date():
        # "7 pm" said at 8 pm means tomorrow; "7" with no am/pm may mean evening.
        if hour < 12 and when + dt.timedelta(hours=12) > now and not re.search(r"am|a\.m\.", t):
            when += dt.timedelta(hours=12)
        else:
            when += dt.timedelta(days=1)
    return when


def say_time(d: dt.datetime) -> str:
    return d.strftime("%A %d %B at %I:%M %p").replace(" 0", " ")


def fn(name, desc, props, required=()):
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props, "required": list(required)}}}


SPECS = [
    fn("math", "Exact maths engine. ALWAYS use it for any calculation, equation, fraction, percentage, "
       "algebra, or calculus. Never do arithmetic in your head.",
       {"expression": {"type": "string", "description": "e.g. '2x+3=11', '15% of 80', 'x^2-5x+6=0', '1/3+1/6', 'x+y=10, x-y=2'"},
        "operation": {"type": "string", "enum": ["auto", "evaluate", "solve", "simplify", "factor", "expand",
                                                  "derivative", "integral", "limit", "primes"]},
        "variable": {"type": "string"}, "lower": {"type": "string"}, "upper": {"type": "string"},
        "point": {"type": "string"}}, ["expression"]),
    fn("convert_units", "Convert between units (length, weight, volume, time, speed, area, temperature).",
       {"value": {"type": "number"}, "from_unit": {"type": "string"}, "to_unit": {"type": "string"}},
       ["value", "from_unit", "to_unit"]),
    fn("set_timer", "Start a countdown timer on the screens, e.g. for homework or brushing teeth.",
       {"minutes": {"type": "number"}, "label": {"type": "string"}}, ["minutes"]),
    fn("add_reminder", "Save a reminder that Tejas will say out loud at the right time.",
       {"text": {"type": "string", "description": "what to remind, in plain words"},
        "when": {"type": "string", "description": "plain time like 'in 20 minutes', '7 pm', 'tomorrow 7:30 am', 'friday 6pm'"},
        "repeat": {"type": "string", "enum": ["none", "daily", "weekly"]}}, ["text", "when"]),
    fn("list_reminders", "List upcoming reminders.", {}),
    fn("cancel_reminder", "Cancel a reminder by its number or words.", {"which": {"type": "string"}}, ["which"]),
    fn("remember", "Save one short, useful fact about this child for the future, like a favourite thing, "
       "a goal, or what they're learning. Don't save private details like addresses or passwords.",
       {"fact": {"type": "string"}}, ["fact"]),
    fn("search_library", "Look up the family's own books and school notes saved on this computer.",
       {"query": {"type": "string"}}, ["query"]),
    fn("get_news", "Get the latest saved news headlines.",
       {"topic": {"type": "string", "enum": ["kids", "india", "world", "science"]},
        "count": {"type": "integer"}}),
]


@dataclass
class ToolContext:
    profile_id: int | None
    actions: list = field(default_factory=list)


class ToolBox:
    def __init__(self, math, memory, library, news):
        self.math, self.memory, self.library, self.news = math, memory, library, news

    @property
    def specs(self) -> list[dict]:
        return SPECS

    def run(self, name: str, args: dict, ctx: ToolContext) -> dict:
        args = args or {}
        try:
            f = getattr(self, f"t_{name}")
        except AttributeError:
            return {"ok": False, "error": f"no tool called {name}"}
        try:
            return f(ctx, **{k: v for k, v in args.items() if v not in (None, "")})
        except TypeError as e:
            return {"ok": False, "error": f"bad arguments for {name}: {e}"}
        except Exception as e:
            return {"ok": False, "error": f"{name} failed: {type(e).__name__}"}

    def t_math(self, ctx, expression, operation="auto", variable=None, lower=None, upper=None, point=None):
        return self.math.run(expression, operation, variable, lower, upper, point)

    def t_convert_units(self, ctx, value, from_unit, to_unit):
        return convert_units(value, from_unit, to_unit)

    def t_set_timer(self, ctx, minutes, label="Timer"):
        secs = int(round(float(minutes) * 60))
        if not 1 <= secs <= 24 * 3600:
            return {"ok": False, "error": "timers can be 1 second to 24 hours"}
        ctx.actions.append({"action": "timer", "seconds": secs, "label": str(label)[:40]})
        return {"ok": True, "result": f"timer started for {secs // 60} min {secs % 60} s"}

    def t_add_reminder(self, ctx, text, when, repeat="none"):
        d = parse_when(when)
        if not d:
            return {"ok": False, "error": f"I couldn't understand the time '{when}'. Ask for a clearer time."}
        r = self.memory.add_reminder(ctx.profile_id, text, d.timestamp(), repeat)
        ctx.actions.append({"action": "reminders_changed"})
        return {"ok": True, "result": f"reminder #{r['id']} set for {say_time(d)}" + (f", {repeat}" if repeat != "none" else "")}

    def t_list_reminders(self, ctx):
        rs = self.memory.reminders()
        if not rs:
            return {"ok": True, "result": "no reminders"}
        return {"ok": True, "result": [f"#{r['id']}: {r['text']} — {say_time(dt.datetime.fromtimestamp(r['due']))}"
                                       + (f" ({r['repeat']})" if r["repeat"] != "none" else "") for r in rs[:15]]}

    def t_cancel_reminder(self, ctx, which):
        rs = self.memory.reminders()
        m = re.search(r"\d+", str(which))
        hit = [r for r in rs if m and r["id"] == int(m.group())] or \
              [r for r in rs if str(which).lower() in r["text"].lower()]
        if not hit:
            return {"ok": False, "error": "no matching reminder"}
        self.memory.delete_reminder(hit[0]["id"])
        ctx.actions.append({"action": "reminders_changed"})
        return {"ok": True, "result": f"cancelled: {hit[0]['text']}"}

    def t_remember(self, ctx, fact):
        if ctx.profile_id is None:
            return {"ok": False, "error": "no child selected"}
        if re.search(r"\b(password|pin|address|phone|aadhaar|otp)\b", fact, re.I):
            return {"ok": False, "error": "That's private, so I won't save it."}
        return {"ok": True, "result": "saved" if self.memory.remember(ctx.profile_id, fact) else "already known"}

    def t_search_library(self, ctx, query):
        hits = self.library.search(query, k=3)
        if not hits:
            return {"ok": True, "result": "nothing found in the home library"}
        return {"ok": True, "result": [{"from": f"{h['file']} (part {h['part']})", "text": h["text"][:1200]} for h in hits]}

    def t_get_news(self, ctx, topic="kids", count=5):
        return self.news.headlines(topic, int(count))
