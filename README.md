# Tejas AI · V1 2026

**An offline, private AI companion for the whole family.** Tejas listens, talks back in a warm voice, helps with homework, solves hard maths exactly, tells stories, quizzes the kids, sets reminders and timers, reads the news, and remembers what matters to each person.

It runs on **one computer at home with no internet connection**. Every other screen in the house — TV, laptop, tablet, phone — opens Tejas in its web browser over home Wi‑Fi.

```
   TV ─┐
 Phone ─┼── home Wi‑Fi ──▶  Home computer: Tejas server
Laptop ─┘                    ├─ Mind:  a local AI model (Ollama, e.g. Qwen 2.5)
                             ├─ Ears:  Whisper speech recognition (offline)
                             ├─ Voice: Piper neural voice (offline)
                             ├─ Tools: exact maths, reminders, timers, units,
                             │         home library, news, memory
                             └─ Memory: profiles, memories, conversations (SQLite)
```

Nothing is sent to the cloud. No accounts, no ads, no tracking.

---

## What it can do

| | |
|---|---|
| **Talk naturally** | Tap the orb (or press Space / OK on a TV remote) and speak. Tejas stops listening on its own when you finish, and answers out loud, sentence by sentence. **Hands‑free** keeps the conversation going. |
| **Help with homework** | Gives a hint first so the child can try (parents can switch this off), then explains step by step in plain words. |
| **Never gets maths wrong** | Every calculation goes through a real maths engine (SymPy): arithmetic, fractions, percentages, equations, systems, inequalities, factorising, calculus. The AI explains; the engine computes. |
| **Think hard mode** | For tough questions Tejas drafts an answer, then checks its own work with its tools before speaking. |
| **Reminders & timers** | “Remind me at 7 pm to pack my bag”, “every day at 8”, “start a 10‑minute timer”. Reminders are spoken on every screen at home. |
| **News** | When the computer is online it saves headlines every hour (Kids, India, World, Science); offline, Tejas reads the saved ones and says how old they are. |
| **Its own mind** | Remembers each person’s favourite things, goals and what they’re learning, and uses it next time. Parents can see and delete every memory. |
| **Home library** | Drop school books and notes (PDF, TXT, MD) into the library folder and Tejas can look things up in them. |
| **Languages** | English, Hindi, Hinglish and Punjabi conversations (Whisper understands many more). |
| **Kid‑safe** | Child‑friendly persona, gentle refusals, private details never saved, a caring fixed reply (with India’s Tele‑MANAS 14416 helpline) if a child talks about hurting themselves, and flagged chats shown to parents. |
| **Parent zone** | PIN‑protected: read conversations, manage family profiles and memories, choose the model and voice, set homework hints. |

## The screen

A mind‑map interface: the living orb on the left (it breathes like a heartbeat when idle, and ripples with your voice and Tejas’s), gold wires out to **Ask me to · Reminders · Timers · Headlines · Memories**, each fanning out to things you can tap. On the right: the answer, live voice meter, status and quick tiles, and the **Ask a question** bar.

- **TV:** arrow keys / remote D‑pad move between buttons, OK presses, Back closes. Big text on large screens.
- **Phone:** one scrolling column with the ask bar pinned at the bottom. Add it to your home screen for a full‑screen app.

## What you need

- A home computer that stays on: Windows 10/11, macOS, or Linux (incl. **TEJAS OS**).
- **8 GB RAM** works (Tejas picks a small brain); **16 GB+** recommended; a GPU makes it faster but isn’t required.
- About **8 GB of disk** for the models.
- Internet **once**, for installing. After that, unplug it if you like.

| Memory | Brain the installer picks | Ears |
|---|---|---|
| under 12 GB | `qwen2.5:3b` | Whisper base |
| 12–23 GB | `qwen2.5:7b` | Whisper small |
| 24 GB+ | `qwen2.5:14b` | Whisper small |

Override with `TEJAS_MODEL=llama3.1:8b ./scripts/install.sh` (any Ollama model that supports tools).

## Install

**Linux / macOS / TEJAS OS**
```bash
git clone <this repo> tejas-ai && cd tejas-ai
./scripts/install.sh            # add --service to start Tejas automatically at login (Linux)
./start.sh
```

**Windows** (PowerShell)
```powershell
git clone <this repo> tejas-ai; cd tejas-ai
powershell -ExecutionPolicy Bypass -File scripts\install.ps1
.\start.bat
```

Then open **http://localhost:8000** on the home computer. The first time, Tejas asks who’s in the family.

## Use it on the TV and phones

Tejas prints an address like `https://192.168.1.20:8443`. Open it on any device on the same Wi‑Fi (or tap **Connect a screen** and scan the QR code).

The browser will warn that the page “isn’t private” the first time. That’s expected: browsers only allow the microphone on secure pages, so Tejas makes its own home security certificate, offline. Tap **Advanced → Proceed**. To remove the warning for good, install `tejas-home-ca.crt` (download link in the Connect screen) on that device.

## Where things live

Everything is in one folder: `~/.tejas-ai` (Windows: `C:\Users\<you>\.tejas-ai`). Back it up to keep your family’s memories.

```
config.json   settings          tejas.db   profiles, memories, chats, reminders
library/      your books/notes  models/    ears and voices
certs/        home certificate  news.json  saved headlines
```

## For developers

```bash
pip install -e ".[test]" && pytest
python -m tejas_ai --help
```

- `tejas_ai/brain.py` – persona, maths pre‑check, tool loop, think‑hard self‑review
- `tejas_ai/tools.py` – maths, units, timers, reminders (plain‑English times), memory, library, news
- `tejas_ai/mathengine.py` – sandboxed SymPy worker with a kill‑on‑timeout
- `tejas_ai/llm.py` – Ollama and OpenAI‑compatible (llama.cpp, LM Studio) streaming with tools
- `tejas_ai/speech.py` – Whisper ears, Piper voice
- `tejas_ai/web/` – the app (no build step, no CDN)

## Roadmap

- Wake word (“Hey Tejas”) that runs on the home computer
- Daily screen‑time limits per child
- Calendar sync, photo questions (“what’s this leaf?”), and ready‑made TEJAS OS package

---
MIT licence. Fonts: Geist and Michroma (SIL Open Font License).
