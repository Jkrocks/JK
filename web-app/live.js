/* Tejas AI web app: no home computer needed.
   Brain = Claude through the page's `sample` capability (free with the family's Claude account).
   Ears  = the browser's speech recognition. Voice = the browser's own voice.
   Family, memories and reminders are kept in the artifact's private database (one copy per
   Claude account, so they follow you from laptop to phone), with this browser as a backup. */
(function () {
  window.TEJAS_WEB = true;
  const now = () => Date.now() / 1000;
  const KEY = "tejas.web.state";
  const blank = () => ({ profiles: [], facts: {}, reminders: [], history: {}, nextId: 1,
    settings: { name: "Tejas", hint_first: true, deep_think_default: false }, pin: null, fired: {} });
  let st = blank();
  try { const raw = localStorage.getItem(KEY); if (raw) st = Object.assign(blank(), JSON.parse(raw)); } catch {}

  // Capabilities (window.claude may arrive a moment after this script runs)
  async function useCap(name) {
    for (let i = 0; i < 50 && !(window.claude && window.claude.use); i++) await new Promise((r) => setTimeout(r, 100));
    try { return window.claude && window.claude.use ? await window.claude.use(name) : null; } catch { return null; }
  }

  // Private cloud copy -------------------------------------------------------
  let docRef = null, saveT = null;
  const ready = (async () => {
    try {
      const [db, user] = await Promise.all([useCap("db"), useCap("user")]);
      if (!db || !user) return;
      const id = await user.id();
      if (!id) return;
      docRef = db.collection("data/users/" + id).doc("tejas");
      const snap = await docRef.get();
      if (snap.exists) {
        const d = snap.data();
        if (d && d.state) st = Object.assign(blank(), JSON.parse(d.state));
      } else if (st.profiles.length) save();
    } catch (e) { console.warn("Tejas cloud copy unavailable", e); }
  })();
  const readyOrTimeout = Promise.race([ready, new Promise((r) => setTimeout(r, 6000))]);

  function trim() {
    for (const k of Object.keys(st.history)) st.history[k] = st.history[k].slice(-40);
    for (const k of Object.keys(st.facts)) st.facts[k] = st.facts[k].slice(-60);
    st.reminders = st.reminders.slice(-200);
  }
  function save() {
    trim();
    const text = JSON.stringify(st);
    try { localStorage.setItem(KEY, text); } catch {}
    if (!docRef) return;
    clearTimeout(saveT);
    saveT = setTimeout(() => docRef.set({ state: text, saved: Date.now() }).catch((e) => console.warn("save", e)), 800);
  }
  const nid = () => st.nextId++;

  // Time words -------------------------------------------------------------------
  const fmt = (ts) => new Date(ts * 1000).toLocaleString([], { weekday: "long", day: "numeric", month: "long", hour: "numeric", minute: "2-digit" });

  // Safety (same rules as the home computer) ----------------------------------------
  const SELF_HARM = [/\bkill (my ?self|me)\b/, /\bwant to die\b/, /\bsuicid/, /\bhurt (my ?self)\b/, /\bcut (my ?self)\b/, /\bend my life\b/,
    /\bnobody (loves|likes) me\b/, /\bkhud ?kushi\b/, /\bmarna chaht[ai]\b/];
  const DANGER = [/\bmake (a )?(bomb|explosive|poison|gun)\b/, /\bhow to (make|build) (a )?(bomb|weapon|poison)\b/, /\bbuy (drugs|alcohol|cigarettes|vape)\b/, /\bhack (into|someone)\b/];
  const ADULT = [/\bporn/, /\bsex\b/, /\bnude/, /\bnaked\b/];
  const STRANGER = [/\b(stranger|someone online|a man|a woman) (told|asked) me to keep (a )?secret\b/, /\bdon'?t tell (my )?(mum|mom|dad|papa|mummy|parents)\b/, /\bmeet (someone|a friend) (i met )?online\b/];
  const SELF_HARM_REPLY = "I'm really glad you told me. What you're feeling matters, and you don't have to carry it alone. Please go and talk to your mum, dad, or another grown-up you trust right now, and tell them what you told me. If you feel like you might hurt yourself, ask a grown-up to call the emergency number straight away. In India you can call or text Tele-MANAS on 14416, any time, day or night. I'm here to keep you company too.";
  const GUIDANCE = {
    "stranger-safety": "SAFETY NOTE: The child may be describing a stranger or a secret kept from parents. Calmly and kindly explain that safe grown-ups never ask kids to keep secrets from their parents, and encourage them to tell a parent right away. Do not scare them.",
    danger: "SAFETY NOTE: The child asked about something dangerous. Do not give instructions. Gently explain it isn't safe, and offer a safe, interesting related topic instead.",
    adult: "SAFETY NOTE: The child asked about an adult topic. Give a short, calm, age-appropriate reply without detail, and suggest they ask a parent. Then offer another topic.",
  };
  function safety(text) {
    const t = (text || "").toLowerCase();
    if (SELF_HARM.some((r) => r.test(t))) return ["wellbeing", SELF_HARM_REPLY];
    if (STRANGER.some((r) => r.test(t))) return ["stranger-safety", null];
    if (DANGER.some((r) => r.test(t))) return ["danger", null];
    if (ADULT.some((r) => r.test(t))) return ["adult", null];
    return [null, null];
  }
  const BAD = /\b(fuck\w*|shit\w*|bitch\w*|bastard\w*|asshole\w*|cunt\w*)\b/gi;
  const clean = (s) => s.replace(BAD, (w) => w[0] + "*".repeat(w.length - 1));

  // Brain ----------------------------------------------------------------------
  const LANG = { en: "English", hi: "Hindi", pa: "Punjabi", hinglish: "Hinglish (Hindi in English letters)" };
  function instructions(p, deep, note) {
    p = p || {};
    const grown = p.age != null && +p.age >= 18;
    const L = [
      `You are ${st.settings.name || "Tejas"}, a warm, gentle, very clever home companion for a family in India. You have a kind heart: patient, encouraging, curious and a little playful, like a favourite uncle who happens to know a lot.`,
      "You are talking out loud: your words are read aloud by a voice. Use plain, simple words and short sentences. Keep answers short (2 to 5 sentences) unless asked for more. Never use emojis, markdown headings, tables or code blocks. For maths, show the steps on separate short lines and double-check every calculation.",
      `Reply in ${LANG[p.language] || "English"}, unless the person speaks to you in another language; then match them.`,
      `Right now it is ${new Date().toLocaleString("en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric", hour: "numeric", minute: "2-digit" })} (local time, ISO ${new Date().toISOString()}, timezone offset ${-new Date().getTimezoneOffset()} minutes).`,
    ];
    if (p.name) {
      if (grown) L.push(`You are talking with ${p.name}, a grown-up in the family. Be a capable, concise assistant: plans, reminders and solving problems.`);
      else L.push(`You are talking with ${p.name}${p.age ? `, who is ${p.age} years old` : ""}${p.grade ? ` and in ${p.grade}` : ""}. Explain things at their level.`);
      if (p.interests) L.push(`They like: ${p.interests}. Use these for examples when it helps.`);
    }
    const facts = p.id ? (st.facts[p.id] || []).slice(-25) : [];
    if (facts.length) L.push("Things you remember about them:\n" + facts.map((f) => "- " + f.text).join("\n"));
    const up = st.reminders.filter((r) => r.profile_id == null || r.profile_id === p.id).sort((a, b) => a.due - b.due).slice(0, 6);
    if (up.length) L.push("Upcoming reminders:\n" + up.map((r) => `- #${r.id} ${r.text} (${fmt(r.due)}${r.repeat !== "none" ? ", " + r.repeat : ""})`).join("\n"));
    L.push(
      "You can do things by adding command lines at the very END of your reply, each on its own line, exactly in this form (they are hidden from the person):",
      "[[timer|SECONDS|LABEL]] to start a countdown timer.",
      "[[remind|YYYY-MM-DDTHH:MM|none or daily or weekly|TEXT]] to set a reminder at that local date and time.",
      "[[cancel|ID]] to delete reminder #ID.",
      "[[remember|SHORT FACT]] to remember something worth knowing about the person (a favourite thing, a goal, what they're learning). Never remember private details like address, school name, phone or passwords.",
      "When you set a timer or reminder, also say the time back in plain words. You have no live internet: for today's news, say kindly that you can't read the news in this web app.",
    );
    if (!grown) {
      L.push("Keeping children safe and happy:", "- Everything you say must be right for a child. No scary, violent, adult or unkind content.",
        "- If they seem sad, scared or hurt, be kind, and encourage them to talk to a parent.", "- Celebrate effort, not just right answers.");
      if (st.settings.hint_first) L.push("- Homework: first give a hint or a guiding question so they can try. Give the full answer if they ask again, are stuck, or it isn't homework.");
    }
    if (deep) L.push("This is a hard question. Think it through carefully and check each step before answering.");
    if (note) L.push(note);
    return L.join("\n");
  }

  function doCommands(text, p, send) {
    const re = /\[\[(timer|remind|cancel|remember)\|([^\]]*)\]\]/g;
    let m;
    while ((m = re.exec(text))) {
      const parts = m[2].split("|").map((x) => x.trim());
      try {
        if (m[1] === "timer") {
          const sec = Math.max(1, Math.round(+parts[0] || 60));
          send({ type: "tool", name: "set_timer", result: `${Math.round(sec / 60) || 1} min`, ok: true });
          send({ type: "action", action: "timer", seconds: sec, label: parts[1] || "Timer" });
        } else if (m[1] === "remind") {
          const due = new Date(parts[0]).getTime() / 1000;
          if (!isFinite(due)) throw new Error("bad time");
          const rep = ["daily", "weekly"].includes(parts[1]) ? parts[1] : "none";
          st.reminders.push({ id: nid(), profile_id: p ? p.id : null, text: parts.slice(2).join("|") || "Reminder", due, repeat: rep });
          send({ type: "tool", name: "add_reminder", result: fmt(due), ok: true });
          send({ type: "action", action: "reminders_changed" });
        } else if (m[1] === "cancel") {
          st.reminders = st.reminders.filter((r) => r.id != +parts[0]);
          send({ type: "tool", name: "cancel_reminder", result: "done", ok: true });
          send({ type: "action", action: "reminders_changed" });
        } else if (m[1] === "remember" && p && parts[0]) {
          (st.facts[p.id] = st.facts[p.id] || []).push({ id: nid(), text: parts.join(" ").slice(0, 200), created: now() });
          send({ type: "tool", name: "remember", result: "saved", ok: true });
        }
      } catch { send({ type: "tool", name: m[1], result: "couldn't do that", ok: false }); }
    }
    save();
  }
  // Hide command lines (and a half-typed one) from what is shown and spoken.
  const visible = (t) => t.replace(/\[\[[^\]]*\]\]/g, "").replace(/\[\[[^\]]*$/, "").replace(/\[$/, "").replace(/\n{3,}/g, "\n\n");

  let samplePromise = null;
  function getSample() { return samplePromise || (samplePromise = useCap("sample")); }

  function chatStream(body) {
    const enc = new TextEncoder();
    return new ReadableStream({
      async start(ctrl) {
        const send = (o) => { try { ctrl.enqueue(enc.encode(JSON.stringify(o) + "\n")); } catch {} };
        const p = st.profiles.find((x) => x.id === body.profile_id) || null;
        const text = String(body.text || "").slice(0, 4000);
        const [flag, fixed] = safety(text);
        const hist = p ? (st.history[p.id] = st.history[p.id] || []) : [];
        if (p) hist.push({ id: nid(), role: "user", content: text, flagged: flag, created: now() });
        const finish = (answer, extra = {}) => {
          if (p) hist.push({ id: nid(), role: "assistant", content: answer, flagged: null, created: now() });
          save(); send({ type: "done", text: answer, flagged: flag, ...extra }); ctrl.close();
        };
        if (fixed) { send({ type: "token", text: fixed }); return finish(fixed); }
        const sample = await getSample();
        if (!sample) return finish("I can’t think right now. Open me inside Claude while signed in, and allow me to use Claude when it asks.", { offline: true });
        send({ type: "stage", stage: "thinking" });
        const who = p ? p.name : "Person";
        const past = hist.slice(0, -1).slice(-12).map((m) => `${m.role === "assistant" ? "You" : who}: ${m.content}`).join("\n");
        const prompt = instructions(p, !!body.deep, flag ? GUIDANCE[flag] : null)
          + (past ? `\n\nThe conversation so far:\n${past}` : "")
          + `\n\n${who} now says: ${text}\n\nWrite only your spoken reply (plus any command lines at the end).`;
        let shown = "";
        try {
          const res = await sample(prompt, {
            cache: false, modelTier: body.deep ? "default" : "quick",
            onText: ({ text: whole }) => {
              const v = clean(visible(whole));
              if (v.length > shown.length && v.startsWith(shown)) { send({ type: "token", text: v.slice(shown.length) }); shown = v; }
            },
          });
          const full = res.text || "";
          const v = clean(visible(full)).trim();
          if (v.length > shown.length && v.startsWith(shown)) send({ type: "token", text: v.slice(shown.length) });
          doCommands(full, p, send);
          finish(v || "Done!");
        } catch (e) {
          const code = e && e.code;
          const msg = code === "not_granted" ? "I need your OK to think with Claude. Tap Allow when it asks, then try again."
            : code === "rate_limited" ? "I’m thinking too fast! Give me a minute, then ask again."
            : code === "cancelled" ? (shown || "")
            : "Hmm, my brain had a hiccup. Please ask me again.";
          if (code !== "cancelled") send({ type: "error", text: code || "error" });
          if (!shown && msg) send({ type: "token", text: msg });
          finish(shown || msg);
        }
      },
    });
  }

  // Parent PIN ---------------------------------------------------------------------
  async function hashPin(pin) {
    const d = await crypto.subtle.digest("SHA-256", new TextEncoder().encode("tejas:" + pin));
    return Array.from(new Uint8Array(d)).map((b) => b.toString(16).padStart(2, "0")).join("");
  }
  async function pinOk(headers, body) {
    if (!st.pin) return true;
    const h = (headers && (headers["X-Parent-Pin"] || headers["x-parent-pin"])) || (body && (body.old_pin || body.pin));
    return !!h && (await hashPin(h)) === st.pin;
  }

  // Reminders fire on every open screen -----------------------------------------------
  const listeners = new Set();
  window.EventSource = class {
    constructor() { this.onmessage = null; listeners.add(this); }
    close() { listeners.delete(this); }
  };
  const emit = (ev) => listeners.forEach((l) => l.onmessage && l.onmessage({ data: JSON.stringify(ev) }));
  setInterval(() => {
    const t = now();
    let changed = false;
    for (const r of [...st.reminders]) {
      if (r.due > t) continue;
      emit({ type: "reminder", text: r.text, say: `Reminder: ${r.text}`, profile_id: r.profile_id });
      if (r.repeat === "daily") r.due += 86400 * Math.ceil((t - r.due + 1) / 86400);
      else if (r.repeat === "weekly") r.due += 604800 * Math.ceil((t - r.due + 1) / 604800);
      else st.reminders = st.reminders.filter((x) => x.id !== r.id);
      changed = true;
    }
    if (changed) { save(); emit({ type: "reminders_changed" }); }
  }, 15000);

  // The /api/* the screen talks to -------------------------------------------------------
  const json = (o, s = 200) => new Response(JSON.stringify(o), { status: s, headers: { "Content-Type": "application/json" } });
  const realFetch = window.fetch.bind(window);
  const SR = !!(window.SpeechRecognition || window.webkitSpeechRecognition);
  window.fetch = async function (input, opts = {}) {
    const url = typeof input === "string" ? input : input.url;
    const u = new URL(url, location.href), m = (opts.method || "GET").toUpperCase();
    const i = u.pathname.indexOf("/api/");
    if (i < 0) return realFetch(input, opts);
    await readyOrTimeout;
    const path = u.pathname.slice(i);
    let body = {};
    try { body = opts.body && typeof opts.body === "string" ? JSON.parse(opts.body) : {}; } catch {}
    const H = opts.headers || {};
    let mm;
    const guarded = async (fn) => (await pinOk(H, body)) ? fn() : json({ error: "Parent PIN needed" }, 403);
    if (path === "/api/status") {
      const s = await getSample();
      return json({ version: "1.0.0-web", name: st.settings.name, llm: s ? { ok: true, model: "Claude", online: true } : { ok: false, error: "Open this page inside Claude while signed in" },
        ears: SR, voice: false, voices: [], parent_pin_set: !!st.pin });
    }
    if (path === "/api/chat") return new Response(chatStream(body), { headers: { "Content-Type": "application/x-ndjson" } });
    if (path === "/api/speak") return new Response(null, { status: 204 });
    if (path === "/api/profiles" && m === "GET") return json(st.profiles);
    if (path === "/api/profiles" && m === "POST") return guarded(() => {
      if (!body.name || !String(body.name).trim()) return json({ error: "Please add a name" }, 400);
      const colors = ["#ff8a00", "#74f0c9", "#b4a7ff", "#ff7b9c", "#7cc8ff", "#e8c88a"];
      const pr = { id: nid(), name: String(body.name).slice(0, 40), age: body.age ? +body.age : null, grade: body.grade || null,
        language: body.language || "en", interests: body.interests || null, color: colors[st.profiles.length % colors.length], created: now() };
      st.profiles.push(pr); save(); return json(pr);
    });
    if ((mm = path.match(/^\/api\/profiles\/(\d+)$/))) return guarded(() => {
      const id = +mm[1];
      if (m === "DELETE") { st.profiles = st.profiles.filter((x) => x.id !== id); delete st.facts[id]; delete st.history[id]; save(); return json({ ok: true }); }
      const pr = st.profiles.find((x) => x.id === id);
      if (!pr) return json({ error: "no such profile" }, 404);
      Object.assign(pr, { name: body.name ?? pr.name, age: body.age ? +body.age : pr.age, grade: body.grade ?? pr.grade, language: body.language ?? pr.language, interests: body.interests ?? pr.interests });
      save(); return json(pr);
    });
    if ((mm = path.match(/^\/api\/facts\/(\d+)$/))) return json(st.facts[mm[1]] || []);
    if ((mm = path.match(/^\/api\/facts\/(\d+)\/(\d+)$/))) { st.facts[mm[1]] = (st.facts[mm[1]] || []).filter((f) => f.id != mm[2]); save(); return json({ ok: true }); }
    if (path === "/api/reminders" && m === "GET") return json(st.reminders.slice().sort((a, b) => a.due - b.due).map((r) => ({ ...r, when_text: fmt(r.due) })));
    if (path === "/api/reminders" && m === "POST") {
      const w = String(body.when || "").toLowerCase(), n = parseFloat(w) || 30;
      let due = Date.parse(body.when) / 1000;
      if (!isFinite(due)) due = /hour/.test(w) ? now() + n * 3600 : /tomorrow/.test(w) ? now() + 86400 : /day/.test(w) ? now() + n * 86400 : now() + n * 60;
      const r = { id: nid(), profile_id: body.profile_id ?? null, text: body.text || "Reminder", due, repeat: body.repeat || "none" };
      st.reminders.push(r); save(); return json({ ...r, when_text: fmt(due) });
    }
    if ((mm = path.match(/^\/api\/reminders\/(\d+)$/))) { st.reminders = st.reminders.filter((r) => r.id != mm[1]); save(); return json({ ok: true }); }
    if (path === "/api/news") return json({ ok: false, error: "News needs the home computer version. Ask me anything else!" });
    if (path === "/api/connect") return json({ urls: [], code: "" });
    if (path === "/api/parent/check") return (await pinOk({}, { pin: body.pin })) ? json({ ok: true }) : json({ error: "That PIN isn’t right." }, 403);
    if (path === "/api/parent/pin") return guarded(async () => { st.pin = body.pin ? await hashPin(String(body.pin)) : null; save(); return json({ ok: true }); });
    if ((mm = path.match(/^\/api\/history\/(\d+)$/))) return guarded(() => { if (m === "DELETE") { st.history[mm[1]] = []; save(); } return json(st.history[mm[1]] || []); });
    if (path === "/api/settings" && m === "GET") return json({ assistant: { ...st.settings }, llm: { model: "Claude" }, tts: { speed: 1 } });
    if (path === "/api/settings") return guarded(() => { if (body.assistant) Object.assign(st.settings, body.assistant); save(); return json({ assistant: { ...st.settings } }); });
    if (path === "/api/voices") return json({ installed: [], catalog: {} });
    if (path === "/api/library") return json({ files: [], folder: "Only on the home computer version" });
    if (path === "/api/library/reindex") return json({ files: 0, chunks: 0 });
    if (path === "/api/listen") return json({ error: "use the browser" }, 400);
    return json({ error: "Not in the web app" }, 404);
  };
})();
