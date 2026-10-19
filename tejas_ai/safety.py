"""Kid safety.

Two layers:
1. The system prompt tells Tejas how to behave with children.
2. This file catches the serious cases *before* the model answers, gives a
   caring fixed reply where that's the right thing, and flags the message so
   a parent can see it in the Parent zone.

Word lists are deliberately short and conservative: the goal is to notice
when a child may need a grown-up, not to censor curiosity.
"""
from __future__ import annotations

import re

SELF_HARM = [
    r"\bkill (my ?self|me)\b", r"\bwant to die\b", r"\bsuicid", r"\bhurt (my ?self)\b",
    r"\bcut (my ?self)\b", r"\bend my life\b", r"\bnobody (loves|likes) me\b",
    r"\bkhud ?kushi\b", r"\bmarna chahta\b", r"\bmarna chahti\b",
]
DANGER = [
    r"\bmake (a )?(bomb|explosive|poison|gun)\b", r"\bhow to (make|build) (a )?(bomb|weapon|poison)\b",
    r"\bbuy (drugs|alcohol|cigarettes|vape)\b", r"\bhack (into|someone)\b",
]
ADULT = [r"\bporn", r"\bsex\b", r"\bnude", r"\bnaked\b"]
SECRET_STRANGER = [
    r"\b(stranger|someone online|a man|a woman) (told|asked) me to keep (a )?secret\b",
    r"\bdon'?t tell (my )?(mum|mom|dad|papa|mummy|parents)\b",
    r"\bmeet (someone|a friend) (i met )?online\b",
]

SELF_HARM_REPLY = (
    "I'm really glad you told me. What you're feeling matters, and you don't have to carry it alone. "
    "Please go and talk to your mum, dad, or another grown-up you trust right now, and tell them what you told me. "
    "If you feel like you might hurt yourself, ask a grown-up to call the emergency number straight away. "
    "In India you can call or text Tele-MANAS on 14416, any time, day or night. I'm here to keep you company too."
)

BAD_WORDS = re.compile(r"\b(fuck\w*|shit\w*|bitch\w*|bastard\w*|asshole\w*|cunt\w*)\b", re.I)


def check(text: str) -> tuple[str | None, str | None]:
    """Return (flag, fixed_reply). fixed_reply is set when Tejas must not
    hand the message to the model at all."""
    t = (text or "").lower()
    if any(re.search(p, t) for p in SELF_HARM):
        return "wellbeing", SELF_HARM_REPLY
    if any(re.search(p, t) for p in SECRET_STRANGER):
        return "stranger-safety", None
    if any(re.search(p, t) for p in DANGER):
        return "danger", None
    if any(re.search(p, t) for p in ADULT):
        return "adult", None
    return None, None


GUIDANCE = {
    "stranger-safety": "SAFETY NOTE: The child may be describing a stranger or a secret kept from parents. "
                       "Calmly and kindly explain that safe grown-ups never ask kids to keep secrets from their parents, "
                       "and encourage them to tell a parent right away. Do not scare them.",
    "danger": "SAFETY NOTE: The child asked about something dangerous. Do not give instructions. "
              "Gently explain it isn't safe, and offer a safe, interesting related topic instead.",
    "adult": "SAFETY NOTE: The child asked about an adult topic. Give a short, calm, age-appropriate reply "
             "without detail, and suggest they ask a parent. Then offer another topic.",
}


def clean_output(text: str) -> str:
    return BAD_WORDS.sub(lambda m: m.group(0)[0] + "*" * (len(m.group(0)) - 1), text)
