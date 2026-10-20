/* Tejas AI — the screen. Works on TV, laptop, tablet and phone. No internet needed. */
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const store = {
  get(k, d) { try { const v = localStorage.getItem("tejas." + k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem("tejas." + k, JSON.stringify(v)); } catch {} },
};
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const S = {
  profiles: [], who: null, status: null,
  state: "idle",            // idle | listening | thinking | checking | speaking
  deep: store.get("deep", false), hands: false,
  parentPin: null, level: 0, timers: [], busy: false, abort: null,
  reminders: [], news: null, facts: [], node: "ask", newsTopic: store.get("topic", "kids"),
};

/* ---------------------------------------------------------------- API */
const OFFLINE_MSG = "Tejas isn’t running on the computer right now. Open the Tejas AI app there, wait for “Home server ✓ running”, then try again.";
async function api(path, opts = {}) {
  const headers = { ...(opts.body && !(opts.body instanceof FormData) ? { "Content-Type": "application/json" } : {}), ...(opts.headers || {}) };
  if (S.parentPin) headers["X-Parent-Pin"] = S.parentPin;
  let r;
  try {
    r = await fetch(path, { ...opts, headers, body: opts.body && !(opts.body instanceof FormData) ? JSON.stringify(opts.body) : opts.body });
  } catch (e) {
    if (e.name === "AbortError") throw e;
    throw Object.assign(new Error(OFFLINE_MSG), { offline: true });
  }
  if (r.status === 204) return null;
  const ct = r.headers.get("content-type") || "";
  const data = ct.includes("json") ? await r.json() : await r.blob();
  if (!r.ok) throw Object.assign(new Error((data && data.error) || r.statusText), { status: r.status });
  return data;
}

/* ---------------------------------------------------------------- Audio graph (drives the core) */
const AC = { ctx: null, an: null, buf: null, playSrc: null, micSrc: null };
function audioCtx() {
  if (!AC.ctx) {
    const C = window.AudioContext || window.webkitAudioContext;
    if (!C) return null;
    AC.ctx = new C();
    AC.an = AC.ctx.createAnalyser(); AC.an.fftSize = 512; AC.an.smoothingTimeConstant = 0.7;
    AC.buf = new Uint8Array(AC.an.frequencyBinCount);
  }
  if (AC.ctx.state === "suspended") AC.ctx.resume();
  return AC.ctx;
}
function levelNow() {
  if (!AC.an || !(S.state === "listening" || S.state === "speaking")) return 0;
  AC.an.getByteTimeDomainData(AC.buf);
  let sum = 0;
  for (let i = 0; i < AC.buf.length; i++) { const v = (AC.buf[i] - 128) / 128; sum += v * v; }
  return Math.min(1, Math.sqrt(sum / AC.buf.length) * 4);
}

/* ---------------------------------------------------------------- The orb */
const core = (() => {
  const cv = $("#core"), g = cv.getContext("2d");
  let W = 0, t0 = performance.now(), spin = 0, lvl = 0, think = 0, cool = 0;
  const N = 200;
  const seed = Array.from({ length: N }, () => Math.random());
  function size() { const d = Math.min(devicePixelRatio || 1, 2); W = Math.max(50, cv.clientWidth * d); cv.width = cv.height = W; }
  addEventListener("resize", size); size();
  // Lub-dub, about once a second: Tejas's little heart.
  function heart(t) { const p = (t % 1.15) / 1.15; const b = (x, c, w) => Math.exp(-((x - c) ** 2) / w); return b(p, .08, .0012) + .6 * b(p, .24, .0016); }
  const fb = new Uint8Array(256);
  function frame(now) {
    const t = (now - t0) / 1000, c = W / 2, R = W / 2;
    lvl += (levelNow() - lvl) * 0.25;
    const st = S.state;
    think += ((st === "thinking" || st === "checking" ? 1 : 0) - think) * 0.05;
    cool += ((st === "listening" ? 1 : 0) - cool) * 0.08;
    spin += 0.002 + think * 0.025 + lvl * 0.01;
    document.documentElement.style.setProperty("--glow", (lvl * 0.9 + think * 0.35).toFixed(3));
    const beat = st === "idle" ? heart(t) : 0;
    if (AC.an && (st === "listening" || st === "speaking")) AC.an.getByteFrequencyData(fb); else fb.fill(0);
    g.clearRect(0, 0, W, W);
    const mix = (a, b, k) => a.map((v, i) => Math.round(v + (b[i] - v) * k));
    const ringA = mix([170, 150, 255], [116, 240, 201], cool), ringB = mix([110, 160, 255], [80, 200, 255], cool);

    // Soft halo
    const pr = R * (0.34 + beat * 0.02 + lvl * 0.05 + think * Math.sin(t * 6) * 0.01);
    const halo = g.createRadialGradient(c, c, pr * 0.8, c, c, R);
    halo.addColorStop(0, `rgba(${ringA},${0.30 + lvl * 0.35 + beat * 0.15})`);
    halo.addColorStop(0.5, `rgba(${ringB},${0.06 + lvl * 0.1})`);
    halo.addColorStop(1, "rgba(0,0,0,0)");
    g.fillStyle = halo; g.beginPath(); g.arc(c, c, R, 0, 7); g.fill();

    // Wave ring: hundreds of fine streaks that move with the voice
    g.lineCap = "round";
    for (let i = 0; i < N; i++) {
      const a = (i / N) * Math.PI * 2 + spin;
      const k = Math.floor((i < N / 2 ? i : N - i) * 0.9) + 2;
      const v = fb[k] / 255;
      const wob = Math.sin(t * 2.2 + i * 0.35) * 0.5 + Math.sin(t * 1.3 + i * 0.11) * 0.5;
      const r1 = pr * 1.14 + seed[i] * R * 0.03;
      const len = R * (0.025 + seed[i] * 0.05 + Math.abs(wob) * 0.03 + v * 0.22 + think * 0.03);
      const col = seed[i] > 0.66 ? "255,255,255" : seed[i] > 0.33 ? ringA : ringB;
      g.strokeStyle = `rgba(${col},${0.25 + seed[i] * 0.5 + v * 0.3})`;
      g.lineWidth = W / (seed[i] > 0.8 ? 260 : 420);
      g.beginPath(); g.moveTo(c + Math.cos(a) * r1, c + Math.sin(a) * r1); g.lineTo(c + Math.cos(a) * (r1 + len), c + Math.sin(a) * (r1 + len)); g.stroke();
    }
    // Orbiting dots while thinking
    if (think > 0.02) for (let j = 0; j < 3; j++) {
      const a = t * 3 + j * 2.1, rr = pr * 1.5;
      g.fillStyle = `rgba(232,200,138,${think * 0.9})`; g.beginPath(); g.arc(c + Math.cos(a) * rr, c + Math.sin(a) * rr, W / 120, 0, 7); g.fill();
    }
    // The sphere
    const sph = g.createRadialGradient(c - pr * 0.35, c - pr * 0.45, pr * 0.05, c, c, pr);
    const top = mix([246, 240, 255], [230, 255, 248], cool), midc = mix([186, 165, 255], [130, 235, 210], cool),
      lowc = mix([108, 84, 230], [40, 150, 140], cool), edge = mix([40, 26, 110], [10, 60, 60], cool);
    sph.addColorStop(0, `rgb(${top})`); sph.addColorStop(0.32, `rgb(${midc})`); sph.addColorStop(0.75, `rgb(${lowc})`); sph.addColorStop(1, `rgb(${edge})`);
    g.shadowColor = `rgba(${ringA},.8)`; g.shadowBlur = W / 12;
    g.fillStyle = sph; g.beginPath(); g.arc(c, c, pr, 0, 7); g.fill(); g.shadowBlur = 0;
    // Glass shine
    const sh = g.createLinearGradient(c, c - pr, c, c);
    sh.addColorStop(0, "rgba(255,255,255,.55)"); sh.addColorStop(1, "rgba(255,255,255,0)");
    g.fillStyle = sh; g.beginPath(); g.ellipse(c - pr * 0.12, c - pr * 0.5, pr * 0.62, pr * 0.36, -0.35, 0, 7); g.fill();
    g.strokeStyle = "rgba(255,255,255,.18)"; g.lineWidth = W / 500; g.beginPath(); g.arc(c, c, pr * 0.985, 0, 7); g.stroke();

    bars(fb, t);
    requestAnimationFrame(frame);
  }
  // Voice card: dotted level columns
  const bc = $("#bars"), bg = bc.getContext("2d");
  const hist = new Array(44).fill(0);
  let lastPush = 0;
  function bars(fb, t) {
    const d = Math.min(devicePixelRatio || 1, 2), w = bc.clientWidth * d, h = bc.clientHeight * d;
    if (!w) return;
    if (bc.width !== w) { bc.width = w; bc.height = h; }
    if (t - lastPush > 0.08) {
      lastPush = t;
      const live = S.state === "listening" || S.state === "speaking";
      hist.shift(); hist.push(live ? Math.min(1, lvl * 1.6 + 0.05) : 0.08 + 0.06 * Math.abs(Math.sin(t * 1.7)) + (S.state === "thinking" || S.state === "checking" ? 0.25 * Math.random() : 0));
    }
    bg.clearRect(0, 0, w, h);
    const step = w / hist.length, dot = Math.max(2, step * 0.42), gap = dot * 1.5;
    hist.forEach((v, i) => {
      const n = Math.max(1, Math.round((v * h) / gap));
      for (let k = 0; k < n; k++) {
        bg.fillStyle = `rgba(255,${210 - k * 3},${170 - k * 4},${0.35 + (i / hist.length) * 0.6})`;
        bg.fillRect(i * step, h - k * gap - dot, dot, dot);
      }
    });
  }
  requestAnimationFrame(frame);
  return { size };
})();

/* ---------------------------------------------------------------- State + caption */
const LABELS = { idle: "Tap the orb to talk", listening: "Listening…", thinking: "Thinking…", checking: "Checking my work…", speaking: "Speaking" };
const VOICE_BIG = { idle: "Ready", listening: "Listening", thinking: "Thinking", checking: "Checking", speaking: "Speaking" };
const VOICE_SMALL = { idle: "Tap the orb or press Space", listening: "I stop by myself when you finish", thinking: "Working it out", checking: "Making sure it's right", speaking: "Tap Stop to interrupt" };
function setState(s) {
  S.state = s;
  $("#stateLabel").textContent = LABELS[s] || s;
  $("#voiceBig").textContent = VOICE_BIG[s] || s;
  $("#voiceSmall").textContent = VOICE_SMALL[s] || "";
  $("#voiceBadge").textContent = s === "idle" ? "Ready" : "Live";
  $("#stop").hidden = !(s === "speaking" || s === "thinking" || s === "checking");
  document.body.dataset.state = s;
}
function md(text) { // tiny, safe formatter: **bold** and line breaks
  return esc(text).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/^#+\s*/gm, "").replace(/^\s*[-*]\s+/gm, "• ");
}
function chip(text, bad) { const el = document.createElement("span"); el.className = "chip" + (bad ? " bad" : ""); el.textContent = text; $("#capChips").append(el); }
const TOOL_NAMES = { math: "Maths engine", convert_units: "Converter", set_timer: "Timer", add_reminder: "Reminder", list_reminders: "Reminders", cancel_reminder: "Reminder", remember: "Remembered", search_library: "Home library", get_news: "News" };
/* ---------------------------------------------------------------- Voice out */
const voiceOut = (() => {
  let queue = [], playing = false, serverVoice = true, onIdle = null;
  const player = $("#player");
  function forSpeech(s) {
    return s.replace(/\*\*|__|`|#+/g, "").replace(/•/g, "")
      .replace(/(\d)\s*\^\s*2\b/g, "$1 squared").replace(/(\w)\s*\^\s*2\b/g, "$1 squared").replace(/(\w)\s*\^\s*3\b/g, "$1 cubed")
      .replace(/\^/g, " to the power ").replace(/√/g, "square root of ").replace(/[×*](?=\s*[\d(a-z])/gi, " times ").replace(/÷/g, " divided by ")
      .replace(/≈/g, " about ").replace(/\s=\s/g, " equals ").replace(/(\d)\s*\/\s*(\d)/g, "$1 over $2").replace(/\s-\s(?=\d)/g, " minus ")
      .replace(/\s+/g, " ").trim();
  }
  function langOf(s) { return /[ऀ-ॿ]/.test(s) ? "hi" : (S.who && S.who.language === "hi" && /[ऀ-ॿ]/.test(s) ? "hi" : "en"); }
  async function next() {
    if (playing) return;
    const s = queue.shift();
    if (!s) { if (S.state === "speaking") setState("idle"); const f = onIdle; onIdle = null; f && f(); return; }
    playing = true; setState("speaking");
    try {
      if (serverVoice) {
        const r = await fetch("/api/speak", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: s, lang: langOf(s) }) });
        if (r.status === 200) { const played = await playBlob(await r.blob()); if (played !== false) { playing = false; return next(); } }
        else serverVoice = false; // no voice on the home computer: use this device's own voice from now on
      }
      await deviceSay(s, langOf(s));
    } catch (e) { console.warn("speak", e); }
    playing = false; next();
  }
  function playBlob(blob) {
    return new Promise((res) => {
      const url = URL.createObjectURL(blob);
      player.src = url;
      const ctx = audioCtx();
      if (ctx && ctx.state === "suspended") ctx.resume().catch(() => {});
      if (ctx && !AC.playSrc) { try { AC.playSrc = ctx.createMediaElementSource(player); AC.playSrc.connect(AC.an); AC.playSrc.connect(ctx.destination); } catch {} }
      if (AC.micSrc) { try { AC.micSrc.disconnect(); } catch {} }
      player.onended = player.onerror = () => { URL.revokeObjectURL(url); res(); };
      player.play().catch(() => { URL.revokeObjectURL(url); res(false); });
    });
  }
  function pickVoice(lang) {
    const vs = speechSynthesis.getVoices();
    const want = lang === "hi" ? ["hi-IN"] : ["en-IN", "en-GB", "en-US"];
    const warm = /ryan|daniel|thomas|arthur|guy|george|male|ravi|google uk english male/i;
    for (const w of want) { const v = vs.find((v) => v.lang.replace("_", "-").startsWith(w) && warm.test(v.name)); if (v) return v; }
    for (const w of want) { const v = vs.find((v) => v.lang.replace("_", "-").startsWith(w)); if (v) return v; }
    return null;
  }
  function deviceSay(text, lang) {
    return new Promise((res) => {
      if (!("speechSynthesis" in window)) return res();
      const u = new SpeechSynthesisUtterance(text);
      const v = pickVoice(lang); if (v) u.voice = v;
      u.lang = lang === "hi" ? "hi-IN" : (v ? v.lang : "en-IN"); u.rate = 0.96; u.pitch = 0.92;
      u.onend = u.onerror = () => res();
      speechSynthesis.speak(u);
      setTimeout(res, 20000 + text.length * 120);
    });
  }
  return {
    say(text) { const s = forSpeech(text); if (s) { queue.push(s); next(); } },
    stop() { queue = []; player.pause(); player.removeAttribute("src"); if ("speechSynthesis" in window) speechSynthesis.cancel(); playing = false; onIdle = null; if (S.state === "speaking") setState("idle"); },
    whenDone(f) { if (!playing && !queue.length) f(); else onIdle = f; },
    busy() { return playing || queue.length > 0; },
  };
})();

/* Split streaming text into sentences so Tejas starts speaking quickly */
function sentencer(onSentence) {
  let buf = "";
  return {
    push(t) {
      buf += t;
      let m;
      while ((m = buf.match(/^([\s\S]*?[.!?।](?:["')\]]*)(?=\s|$)|[\s\S]*?\n)/)) && m[1].trim().length > 1) {
        const s = m[1]; buf = buf.slice(s.length);
        if (/\d\.$/.test(s.trim()) && /^\d/.test(buf)) { buf = s + buf; break; } // "3.14": wait
        onSentence(s.trim());
      }
    },
    flush() { if (buf.trim()) onSentence(buf.trim()); buf = ""; },
  };
}

/* ---------------------------------------------------------------- Ask Tejas */
async function ask(text, opts = {}) {
  text = (text || "").trim();
  if (!text) return;
  if (S.busy && S.abort) S.abort.abort();
  voiceOut.stop();
  S.busy = true;
  $("#capYou").textContent = text; $("#capTejas").innerHTML = ""; $("#capChips").innerHTML = "";
  setState("thinking");
  let shown = "";
  const say = sentencer((s) => voiceOut.say(s));
  const ctrl = new AbortController(); S.abort = ctrl;
  try {
    const r = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, signal: ctrl.signal,
      body: JSON.stringify({ text, profile_id: S.who ? S.who.id : null, deep: S.deep }) });
    const rd = r.body.getReader(), dec = new TextDecoder();
    let pend = "";
    for (;;) {
      const { value, done } = await rd.read();
      if (done) break;
      pend += dec.decode(value, { stream: true });
      let i;
      while ((i = pend.indexOf("\n")) >= 0) {
        const line = pend.slice(0, i); pend = pend.slice(i + 1);
        if (!line.trim()) continue;
        const ev = JSON.parse(line);
        if (ev.type === "token") { shown += ev.text; $("#capTejas").innerHTML = md(shown); $(".answer-card").scrollTop = 1e9; say.push(ev.text); }
        else if (ev.type === "stage") setState(ev.stage);
        else if (ev.type === "tool") chip(`${TOOL_NAMES[ev.name] || ev.name}${ev.result && typeof ev.result === "string" && ev.result.length < 60 ? ": " + ev.result : ""}`, ev.ok === false);
        else if (ev.type === "action") handleAction(ev);
        else if (ev.type === "error") chip(ev.text, true);
        else if (ev.type === "done") {
          if (!shown && ev.text) { $("#capTejas").innerHTML = md(ev.text); say.push(ev.text); }
          if (ev.flagged) chip("A grown-up can see this in the Parent zone", true);
        }
      }
    }
    say.flush();
  } catch (e) {
    if (e.name !== "AbortError") { $("#capTejas").textContent = "I can’t reach the home computer right now."; chip(String(e.message || e), true); }
  } finally {
    S.busy = false;
    if (S.state === "thinking" || S.state === "checking") setState(voiceOut.busy() ? "speaking" : "idle");
    loadFacts();
    if (S.hands && !opts.noHands) voiceOut.whenDone(() => setTimeout(() => S.hands && S.state === "idle" && listen(), 350));
  }
}

function handleAction(ev) {
  if (ev.action === "timer") addTimer(ev.seconds, ev.label);
  if (ev.action === "reminders_changed") loadReminders();
}

/* ---------------------------------------------------------------- Voice in */
let rec = null;
async function listen() {
  if (rec) { rec.stopNow(); return; }
  voiceOut.stop();
  if (window.TEJAS_WEB) { if (DICT.on) return stopDictation(); return listenWeb(); }
  if (!window.isSecureContext || !navigator.mediaDevices) {
    toast("Microphone needs the secure address", "Open Tejas with the https:// address shown in Connect, then allow the microphone.", { label: "Show me", fn: openConnect });
    return;
  }
  if (S.status && !S.status.ears) {
    toast("Ears not installed", "Speech recognition isn’t installed on the home computer yet. You can still type to me.");
    return;
  }
  let stream;
  try { stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } }); }
  catch { toast("Can’t use the microphone", "Please allow the microphone for this page in the browser settings."); setState("idle"); return; }
  const ctx = audioCtx();
  if (AC.micSrc) { try { AC.micSrc.disconnect(); } catch {} }
  AC.micSrc = ctx.createMediaStreamSource(stream); AC.micSrc.connect(AC.an);
  const mime = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg"].find((m) => window.MediaRecorder && MediaRecorder.isTypeSupported(m)) || "";
  const mr = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
  const chunks = []; mr.ondataavailable = (e) => e.data.size && chunks.push(e.data);
  setState("listening");
  // Voice activity: stop by itself after the child stops talking.
  const td = new Uint8Array(AC.an.fftSize), start = performance.now();
  let floor = 0.01, heard = false, lastLoud = 0, cancelled = false, timer;
  function rms() { AC.an.getByteTimeDomainData(td); let s = 0; for (const v of td) { const x = (v - 128) / 128; s += x * x; } return Math.sqrt(s / td.length); }
  function tick() {
    const now = performance.now(), v = rms();
    if (now - start < 350) floor = Math.max(floor, v * 1.2);
    else if (v > Math.max(0.02, floor * 2.6)) { heard = true; lastLoud = now; }
    if (heard && now - lastLoud > 1200) return finish();
    if (!heard && now - start > 7000) { cancelled = true; return finish(); }
    if (now - start > 30000) return finish();
    timer = setTimeout(tick, 60);
  }
  function finish() { clearTimeout(timer); if (mr.state !== "inactive") mr.stop(); }
  rec = { stopNow: () => { heard = true; finish(); } };
  mr.onstop = async () => {
    stream.getTracks().forEach((t) => t.stop());
    try { AC.micSrc.disconnect(); } catch {}
    AC.micSrc = null; rec = null;
    if (cancelled || !chunks.length) { setState("idle"); if (S.hands) { S.hands = false; syncToggles(); toast("Hands-free paused", "I didn’t hear anything, so I stopped listening."); } return; }
    setState("thinking"); $("#capYou").textContent = "…";
    const fd = new FormData();
    fd.append("audio", new Blob(chunks, { type: mr.mimeType || "audio/webm" }), "speech.webm");
    if (S.who && S.who.language && S.who.language !== "hinglish") fd.append("language", S.who.language);
    try {
      const r = await api("/api/listen", { method: "POST", body: fd });
      if (r && r.text) ask(r.text);
      else { setState("idle"); $("#capYou").textContent = ""; $("#capTejas").textContent = "Sorry, I didn’t catch that. Can you say it again?"; voiceOut.say("Sorry, I didn't catch that. Can you say it again?"); }
    } catch (e) { setState("idle"); toast("I couldn’t hear that", e.message); }
  };
  mr.start(250); tick();
}

/* The web app has no home computer: the browser's own speech recognition does the listening. */
function listenWeb() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const dictate = () => {
    window.TEJAS_WEB_NO_SR = true; store.set("noSR", true);
    startDictation();
  };
  if (!SR || window.TEJAS_WEB_NO_SR || store.get("noSR", false)) return dictate();
  const r = new SR();
  const lang = S.who && S.who.language;
  r.lang = lang === "hi" ? "hi-IN" : lang === "pa" ? "pa-IN" : "en-IN";
  r.interimResults = true; r.continuous = false; r.maxAlternatives = 1;
  let finalText = "", failed = null;
  r.onresult = (e) => {
    let interim = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      if (e.results[i].isFinal) finalText += e.results[i][0].transcript; else interim += e.results[i][0].transcript;
    }
    $("#capYou").textContent = (finalText + " " + interim).trim() || "…";
  };
  r.onerror = (e) => { failed = e.error || "error"; };
  r.onend = () => {
    rec = null;
    if (finalText.trim()) return ask(finalText.trim());
    setState("idle");
    if (failed && failed !== "no-speech" && failed !== "aborted") {
      dictate();
    } else if (S.hands) { S.hands = false; syncToggles(); toast("Hands-free paused", "I didn’t hear anything, so I stopped listening."); }
  };
  rec = { stopNow: () => { try { r.stop(); } catch {} } };
  setState("listening"); $("#capYou").textContent = "…";
  try { r.start(); } catch { rec = null; setState("idle"); window.TEJAS_WEB_NO_SR = true; dictate(); }
}

/* Talking through the computer's own voice typing (Windows + H, Mac Fn Fn, phone keyboard mic).
   Tejas sends the question by itself when you stop talking. */
const DICT = { on: false, t: null, last: "" };
const isPhone = /Android|iPhone|iPad/i.test(navigator.userAgent);
const isMac = /Mac/i.test(navigator.platform || navigator.userAgent) && !isPhone;
function dictHint() {
  return isPhone ? "Tap the mic on your keyboard and talk" : isMac ? "Press Fn twice, then talk" : "Press Windows + H, then talk";
}
function startDictation() {
  const box = $("#askInput");
  DICT.on = true; DICT.last = box.value;
  box.value = ""; box.placeholder = dictHint() + "…";
  document.body.classList.add("dictating");
  setState("listening"); $("#capYou").textContent = "…";
  box.focus();
  if (!store.get("dictTipSeen", false)) {
    toast("Talk to Tejas", (isPhone ? "Tap the microphone on your keyboard and speak."
      : isMac ? "Press the Fn key twice (or turn on Dictation in Settings), then speak."
      : "Press the Windows key and H together, then speak. Windows types what you say.")
      + " When you stop talking, I send it by myself and answer out loud.", null, 15000);
    store.set("dictTipSeen", true);
  }
  clearTimeout(DICT.t);
  DICT.t = setTimeout(() => { if (DICT.on && !box.value.trim()) stopDictation(); }, 45000);
}
function stopDictation() {
  DICT.on = false; clearTimeout(DICT.t);
  document.body.classList.remove("dictating");
  $("#askInput").placeholder = "Ask a question…";
  if (S.state === "listening") { setState("idle"); $("#capYou").textContent = ""; }
}
$("#askInput").addEventListener("input", () => {
  if (!DICT.on) return;
  const v = $("#askInput").value;
  $("#capYou").textContent = v || "…";
  clearTimeout(DICT.t);
  // Voice typing pauses when you stop talking: send after a short quiet moment.
  DICT.t = setTimeout(() => {
    const q = $("#askInput").value.trim();
    if (!DICT.on || !q) return;
    $("#askInput").value = ""; stopDictation(); ask(q);
  }, 1800);
});
$("#askInput").addEventListener("keydown", (e) => { if (DICT.on && e.key === "Escape") stopDictation(); });

/* ---------------------------------------------------------------- Timers */
function addTimer(seconds, label) {
  S.timers.push({ id: Math.random().toString(36).slice(2), label: label || "Timer", total: seconds, end: Date.now() + seconds * 1000 });
  counts(); if (S.node === "timers") renderFan(); else selectNode("timers");
}
const mmss = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
function tickTimers() {
  const now = Date.now();
  for (const t of [...S.timers]) {
    const left = Math.max(0, Math.round((t.end - now) / 1000));
    const el = $(`#fan [data-timer="${t.id}"]`);
    if (el) { $(".tag", el).textContent = mmss(left); $(".bars3", el).innerHTML = levelBars(1 - left / t.total, 5); }
    if (left === 0) {
      S.timers = S.timers.filter((x) => x !== t); counts(); if (S.node === "timers") renderFan();
      chime(); toast("Timer done", `${t.label} — time’s up!`); voiceOut.say(`${t.label} timer is done!`);
    }
  }
}
function chime() {
  const ctx = audioCtx(); if (!ctx) return;
  [880, 1175, 1568].forEach((f, i) => {
    const o = ctx.createOscillator(), gg = ctx.createGain(), t = ctx.currentTime + i * 0.18;
    o.type = "sine"; o.frequency.value = f; gg.gain.setValueAtTime(0, t); gg.gain.linearRampToValueAtTime(0.18, t + 0.02); gg.gain.exponentialRampToValueAtTime(0.001, t + 0.9);
    o.connect(gg).connect(ctx.destination); o.start(t); o.stop(t + 1);
  });
}

/* ---------------------------------------------------------------- Data: clock, reminders, news, memories */
function tickClock() {
  const d = new Date();
  $("#clockTime").textContent = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  $("#clockDate").textContent = d.toLocaleDateString([], { weekday: "long", day: "numeric", month: "long" });
  const h = d.getHours(), part = h < 5 ? "Still awake" : h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : h < 21 ? "Good evening" : "Good night";
  $("#greet").textContent = S.who ? `${part}, ${S.who.name}` : part;
}
async function loadReminders() { try { S.reminders = await api("/api/reminders"); counts(); if (S.node === "reminders") renderFan(); } catch {} }
async function loadNews() { try { S.news = await api(`/api/news?topic=${S.newsTopic}`); counts(); if (S.node === "news") renderFan(); } catch {} }
async function loadFacts() { if (!S.who) { S.facts = []; counts(); return; } try { S.facts = await api(`/api/facts/${S.who.id}`); counts(); if (S.node === "mind") renderFan(); } catch {} }
function counts() {
  const n = { rem: S.reminders.length, tim: S.timers.length, news: S.news && S.news.ok ? S.news.items.length : 0, mind: S.facts.length };
  $("#nRem").textContent = $("#tRem").textContent = n.rem;
  $("#nTim").textContent = $("#tTim").textContent = n.tim;
  $("#nNews").textContent = $("#tNews").textContent = n.news;
  $("#nMind").textContent = $("#tMind").textContent = n.mind;
  $("#nAsk").textContent = QUICK.length;
}

/* ---------------------------------------------------------------- Mind map: nodes, fan, gold wires */
const QUICK = [
  ["Homework help", "STEP BY STEP", "Can you help me with my homework?"],
  ["Tell me a story", "STORY", "Tell me a short, cosy story."],
  ["Quiz me", "5 QUESTIONS", "Quiz me with 5 fun questions, one at a time."],
  ["Fun fact", "SOMETHING NEW", "Tell me one amazing fun fact."],
  ["Today’s news", "PLAIN WORDS", "What's in the news today? Keep it short and simple."],
  ["My reminders", "WHAT’S NEXT", "What reminders do I have?"],
  ["Times tables", "PRACTICE", "Let's practise times tables. Ask me one at a time and tell me if I'm right."],
  ["Explain simply", "LIKE I’M 7", "Explain how rainbows are made, like I'm 7."],
  ["Plan my day", "GROWN-UPS", "Help me plan the rest of my day in a few simple steps."],
];
const TOPICS = [["kids", "Kids"], ["india", "India"], ["world", "World"], ["science", "Science"]];
function levelBars(v, n = 3, cls = "") { const on = Math.max(1, Math.round(v * n)); return Array.from({ length: n }, (_, i) => `<i${i < on ? "" : ' class="off"'}></i>`).join(""); }
function shortWhen(due) {
  const d = new Date(due * 1000), now = new Date(), t = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  const days = Math.round((new Date(d.toDateString()) - new Date(now.toDateString())) / 864e5);
  return (days === 0 ? "Today " : days === 1 ? "Tomorrow " : days < 7 ? d.toLocaleDateString([], { weekday: "short" }) + " " : d.toLocaleDateString([], { day: "numeric", month: "short" }) + " ") + t;
}
function urgency(due) { const h = (due * 1000 - Date.now()) / 3.6e6; return h < 1 ? ["bad", 3] : h < 12 ? ["warn", 2] : ["", 1]; }
function selectNode(name) {
  S.node = name; store.set("node", name);
  $$(".node").forEach((n) => n.classList.toggle("on", n.dataset.node === name));
  renderFan();
}
function fanItems() {
  const it = [];
  if (S.node === "ask") {
    QUICK.forEach(([t, tag, say]) => it.push({ title: t, tag, act: () => ask(say) }));
    return { head: ["Ask me to", "Tap one, or just talk"], items: it };
  }
  if (S.node === "reminders") {
    S.reminders.forEach((r) => { const [c, l] = urgency(r.due); it.push({ title: r.text, tag: shortWhen(r.due) + (r.repeat !== "none" ? " · " + r.repeat : ""), bars: [c, l / 3], del: () => api(`/api/reminders/${r.id}`, { method: "DELETE" }).then(loadReminders), act: () => voiceOut.say(`${r.text}, ${r.when_text}`) }); });
    it.push({ title: "+ Add a reminder", tag: "TAP", act: () => $("#btnAddReminder").click() });
    return { head: ["Reminders", "I’ll say them out loud on every screen"], items: it };
  }
  if (S.node === "timers") {
    S.timers.forEach((t) => it.push({ title: t.label, tag: mmss(Math.max(0, Math.round((t.end - Date.now()) / 1000))), bars: ["", 0], timer: t.id, del: () => { S.timers = S.timers.filter((x) => x !== t); counts(); renderFan(); } }));
    [["5 min", 5], ["10 min", 10], ["20 min homework", 20]].forEach(([l, m]) => it.push({ title: `+ ${l} timer`, tag: "START", act: () => addTimer(m * 60, l.includes("homework") ? "Homework" : `${l} timer`) }));
    return { head: ["Timers", "Counting down"], items: it };
  }
  if (S.node === "news") {
    const n = S.news;
    if (n && n.ok) {
      const age = n.age_hours < 1 ? "JUST NOW" : n.age_hours < 24 ? `${Math.round(n.age_hours)}H AGO` : `${Math.round(n.age_hours / 24)}D AGO`;
      const fresh = n.age_hours < 3 ? 1 : n.age_hours < 24 ? 0.66 : 0.33;
      n.items.forEach((x) => it.push({ title: x.title, tag: age, bars: [fresh < 0.5 ? "warn" : "", fresh], act: () => ask(`Tell me simply about this news: ${x.title}`) }));
    } else it.push({ note: (n && n.error) || "No headlines yet." });
    return { head: ["Headlines", null], topics: true, items: it };
  }
  if (S.node === "mind") {
    S.facts.slice(-12).reverse().forEach((f) => it.push({ title: f.text, tag: "REMEMBERED" }));
    if (!S.facts.length) it.push({ note: S.who ? "Tell me about yourself: what you love, what you’re learning. I’ll remember." : "Choose who’s talking first." });
    return { head: ["Memories", S.who ? `What I know about ${S.who.name}` : ""], items: it };
  }
  return { head: ["", ""], items: [] };
}
const mobile = matchMedia("(max-width:980px)");
function renderFan() {
  const { head, items, topics } = fanItems();
  $("#fanHead").innerHTML = `<b>${esc(head[0])}</b>${head[1] ? esc(head[1]) : ""}` +
    (topics ? `<div class="ask-row" style="justify-content:flex-end">${TOPICS.map(([k, l]) => `<button class="chipbtn tog" aria-pressed="${S.newsTopic === k}" data-topic="${k}">${l}</button>`).join("")}</div>` : "");
  $$("#fanHead [data-topic]").forEach((b) => b.onclick = () => { S.newsTopic = b.dataset.topic; store.set("topic", S.newsTopic); loadNews(); });
  const ul = $("#fan");
  ul.innerHTML = items.map((x, i) => x.note ? `<li><p class="empty-note">${esc(x.note)}</p></li>` :
    `<li style="animation-delay:${i * 35}ms"><button class="item" data-i="${i}"${x.timer ? ` data-timer="${x.timer}"` : ""}><b>${esc(x.title)}</b><span class="meta"><span class="tag">${esc(x.tag || "")}</span>${x.bars ? `<span class="bars3 ${x.bars[0]}">${levelBars(x.bars[1])}</span>` : ""}${x.del ? '<span class="x" role="button" aria-label="Remove">✕</span>' : ""}</span></button></li>`).join("");
  $$("#fan .item").forEach((b) => {
    const x = items[b.dataset.i];
    b.onclick = (e) => { if (e.target.classList.contains("x")) { x.del(); return; } x.act && x.act(); };
    if (x.timer) b.dataset.timer = x.timer;
  });
  layout();
}
function layout() {
  const svg = $("#wires");
  if (mobile.matches) { svg.innerHTML = ""; $$("#fan li").forEach((li) => { li.style.left = li.style.top = ""; }); return; }
  const st = $("#stage").getBoundingClientRect(), W = st.width, H = st.height;
  const orb = $("#mic").getBoundingClientRect();
  const cx = orb.left + orb.width / 2 - st.left, cy = orb.top + orb.height / 2 - st.top, ro = orb.width * 0.36;
  const sel = $(".node.on") || $(".node");
  const nr = sel.getBoundingClientRect();
  const nx = nr.right - st.left, ny = nr.top + nr.height / 2 - st.top;
  const lis = $$("#fan li"), n = lis.length;
  const R = Math.max(nx - cx + 90, Math.min(nx - cx + 190, W - cx - 225));
  const maxSpan = 2 * Math.asin(Math.min(0.98, (H / 2 - 50) / R));
  const span = Math.min(maxSpan, Math.max(0.35, (n - 1) * 0.15));
  let paths = "";
  // orb → nodes
  $$(".node").forEach((node) => {
    const r = node.getBoundingClientRect(), x2 = r.left - st.left, y2 = r.top + r.height / 2 - st.top, x1 = cx + ro * 1.25;
    const on = node.classList.contains("on");
    paths += `<path d="M${x1},${cy} C${x1 + (x2 - x1) * 0.55},${cy} ${x2 - (x2 - x1) * 0.45},${y2} ${x2},${y2}" stroke="url(#wg)" stroke-width="${on ? 1.6 : 1}" opacity="${on ? 1 : 0.45}"/>`;
  });
  lis.forEach((li, i) => {
    const th = n === 1 ? 0 : -span / 2 + (span * i) / (n - 1);
    let x = cx + R * Math.cos(th), y = cy + R * Math.sin(th);
    y = Math.max(28, Math.min(H - 22, y));
    li.style.left = `${x}px`; li.style.top = `${y}px`;
    const c1 = nx + Math.max(40, (x - nx) * 0.5);
    paths += `<path class="fw" d="M${nx},${ny} C${c1},${ny} ${x - 70},${y} ${x - 6},${y}" stroke="url(#fg)" stroke-width="1.1" style="animation-delay:${i * 35}ms"/><circle cx="${x - 6}" cy="${y}" r="2.6" fill="#f3dcae"/>`;
  });
  svg.innerHTML = `<defs><linearGradient id="wg" x1="0" x2="1"><stop offset="0" stop-color="#b9a7ff" stop-opacity=".2"/><stop offset="1" stop-color="#e8c88a" stop-opacity=".9"/></linearGradient>
    <linearGradient id="fg" x1="0" x2="1"><stop offset="0" stop-color="#f3dcae" stop-opacity=".95"/><stop offset="1" stop-color="#e8c88a" stop-opacity=".35"/></linearGradient></defs>
    <style>.fw{stroke-dasharray:900;stroke-dashoffset:900;animation:draw .7s cubic-bezier(.2,1,.3,1) forwards}@keyframes draw{to{stroke-dashoffset:0}}</style>
    <g fill="none">${paths}</g>`;
}
addEventListener("resize", () => { clearTimeout(layout.t); layout.t = setTimeout(layout, 60); });

/* ---------------------------------------------------------------- Status */
async function loadStatus() {
  try {
    const s = await api("/api/status"); S.status = s;
    const pill = $("#brainPill");
    pill.className = "status-dot " + (s.llm.ok ? "ok" : "bad");
    $("span", pill).textContent = s.llm.ok ? `Mind: ${s.llm.model}` : "Mind offline";
    pill.title = s.llm.error || "";
    $("#liveBadge").className = "badge" + (s.llm.ok ? "" : " bad"); $("#liveBadge").textContent = s.llm.ok ? "Active" : "Needs setup";
    $("#statusText").textContent = s.llm.ok
      ? (s.llm.online ? `Thinking with a free online brain${s.voice ? ", talking with my own voice" : ""}. Questions go over the internet.`
                      : `Running on this computer${s.voice ? " with my own voice" : ""}. No internet needed, nothing leaves your home.`)
      : `My thinking engine isn’t ready. ${s.llm.error || ""}. On the home computer run: ollama pull ${s.llm.model || "qwen2.5:7b"}`;
    $("#orbName").textContent = s.name || "Tejas";
    S.wasOffline = false;
  } catch {
    const pill = $("#brainPill"); pill.className = "status-dot bad"; $("span", pill).textContent = "Home computer unreachable";
    if (!S.wasOffline) toast("Tejas isn’t running", OFFLINE_MSG, null, 20000);
    S.wasOffline = true;
  }
}
/* ---------------------------------------------------------------- Live events (reminders on every screen) */
function events() {
  const es = new EventSource("/api/events");
  es.onmessage = (m) => {
    const ev = JSON.parse(m.data);
    if (ev.type === "reminder") {
      if (ev.profile_id && S.who && ev.profile_id !== S.who.id && !(S.who.age >= 18)) return;
      chime(); toast("Reminder", ev.text, null, 15000); voiceOut.say(ev.say || ev.text); loadReminders();
    }
    if (ev.type === "reminders_changed") loadReminders();
    if (ev.type === "news_updated") loadNews();
  };
  es.onerror = () => { es.close(); setTimeout(events, 5000); };
}

/* ---------------------------------------------------------------- Toasts */
function toast(title, text, action, ms = 7000) {
  const el = document.createElement("div");
  el.className = "toast";
  el.innerHTML = `<div><b>${esc(title)}</b>${esc(text)}</div>${action ? `<button>${esc(action.label)}</button>` : ""}`;
  if (action) $("button", el).onclick = () => { el.remove(); action.fn(); };
  $("#toasts").append(el);
  setTimeout(() => el.remove(), ms);
}

/* ---------------------------------------------------------------- Overlays */
function openOv(id) { $$(".overlay").forEach((o) => o.hidden = true); const o = $(id); o.hidden = false; setTimeout(() => { const f = $("input,button:not(.close),select,[tabindex]", o); f && f.focus(); }, 30); }
let keyNav = false;
addEventListener("keydown", () => { keyNav = true; }, true);
addEventListener("pointerdown", () => { keyNav = false; }, true);
function closeOv() { $$(".overlay").forEach((o) => o.hidden = true); if (keyNav) $("#mic").focus(); }
$$("[data-close]").forEach((b) => b.onclick = closeOv);
$$(".overlay").forEach((o) => o.addEventListener("click", (e) => { if (e.target === o && o.id !== "ovWelcome") closeOv(); }));

const initials = (n) => (n || "?").trim().split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
function setWho(p) {
  S.who = p; store.set("who", p ? p.id : null);
  $("#whoAvatar").textContent = $("#whoAvatar2").textContent = initials(p && p.name); $("#whoName").textContent = p ? p.name : "Choose";
  $("#greetSub").textContent = p ? (p.age && p.age < 18 ? "What shall we learn or play today?" : "How can I help today?") : "Who is talking to me?";
  $("#kicker").textContent = p ? `${p.name}${p.age ? " · " + p.age + (p.age < 18 ? " yrs" : "") : ""}` : "Home";
  tickClock(); loadFacts();
  $("#capYou").textContent = ""; $("#capTejas").textContent = p ? `Hi ${p.name}! What shall we do today?` : ""; $("#capChips").innerHTML = "";
}
async function loadProfiles() { S.profiles = await api("/api/profiles"); return S.profiles; }
function openWho() {
  $("#people").innerHTML = S.profiles.map((p) => `<button class="person" data-id="${p.id}"><span class="avatar">${esc(initials(p.name))}</span><span>${esc(p.name)}</span></button>`).join("");
  $$(".person").forEach((b) => b.onclick = () => { setWho(S.profiles.find((p) => p.id == b.dataset.id)); closeOv(); voiceOut.say(`Hi ${S.who.name}!`); });
  openOv("#ovWho");
}
function formData(form) {
  const o = {};
  for (const el of form.elements) {
    if (!el.name) continue;
    if (el.type === "checkbox") o[el.name] = el.checked;
    else if (el.type === "number") o[el.name] = el.value === "" ? null : Number(el.value);
    else o[el.name] = el.value.trim() || null;
  }
  return o;
}

/* Welcome (first run) */
function openWelcome() { openOv("#ovWelcome"); renderAdded(); }
function renderAdded() { $("#welcomeAdded").innerHTML = S.profiles.map((p) => `<span>${esc(p.name)}${p.age ? ", " + p.age : ""}</span>`).join(""); $("#welcomeDone").disabled = !S.profiles.length; }
$("#welcomeForm").onsubmit = async (e) => {
  e.preventDefault();
  try { await api("/api/profiles", { method: "POST", body: formData(e.target) }); e.target.reset(); await loadProfiles(); renderAdded(); e.target.elements.name.focus(); }
  catch (err) { toast("Couldn’t add", err.message); }
};
$("#welcomeDone").onclick = () => { closeOv(); S.profiles.length === 1 ? setWho(S.profiles[0]) : openWho(); };

/* Connect */
async function openConnect() {
  openOv("#ovConnect");
  try {
    const c = await api("/api/connect");
    $("#qrs").innerHTML = c.urls.length ? c.urls.map((u) => `<div class="qr"><img alt="QR code for ${esc(u)}" src="/api/qr.svg?url=${encodeURIComponent(u)}"><code>${esc(u)}</code></div>`).join("")
      : "<p class='lead'>This computer isn’t on a network right now.</p>";
    if (c.code) { $("#pairCode").hidden = false; $("#pairCode").innerHTML = `Pairing code for the Tejas phone and TV apps:<b>${esc(c.code)}</b>`; }
  } catch {}
}
$("#btnConnect").onclick = openConnect;
$$("#connectTabs .tab").forEach((t) => t.onclick = () => {
  $$("#connectTabs .tab").forEach((x) => x.classList.toggle("on", x === t));
  $$("#ovConnect .steps").forEach((o) => o.hidden = o.dataset.ct !== t.dataset.ct);
});
if (window.TejasApp) { $("#appSwitch").hidden = false; $("#btnForget").onclick = () => window.TejasApp.forget(); }

/* Parent zone */
$("#btnParent").onclick = () => {
  openOv("#ovParent");
  const set = S.status && S.status.parent_pin_set;
  if (!set || S.parentPin) { showParent(); return; }
  $("#pinForm").hidden = false; $("#parentBody").hidden = true; $("#pinErr").textContent = ""; $("#pinInput").value = ""; $("#pinInput").focus();
};
$("#pinForm").onsubmit = async (e) => {
  e.preventDefault();
  const pin = $("#pinInput").value;
  try { await api("/api/parent/check", { method: "POST", body: { pin } }); S.parentPin = pin; showParent(); }
  catch (err) { $("#pinErr").textContent = err.status === 429 ? err.message : "That PIN isn’t right."; }
};
function showParent() {
  $("#pinForm").hidden = true; $("#parentBody").hidden = false;
  if (!(S.status && S.status.parent_pin_set)) toast("Set a parent PIN", "Go to Settings and set a PIN so only grown-ups can open this zone.");
  const opts = S.profiles.map((p) => `<option value="${p.id}">${esc(p.name)}</option>`).join("");
  $("#histWho").innerHTML = opts; $("#mindWho").innerHTML = opts;
  if (S.who) { $("#histWho").value = S.who.id; $("#mindWho").value = S.who.id; }
  tab("talks");
}
function tab(name) {
  $$(".tab").forEach((t) => t.classList.toggle("on", t.dataset.tab === name));
  $$(".tabpane").forEach((p) => p.hidden = p.id !== "tab-" + name);
  ({ talks: loadHistory, family: loadFamily, mind: loadMind, settings: loadSettings, library: loadLibrary })[name]();
}
$$(".tab").forEach((t) => t.onclick = () => tab(t.dataset.tab));
async function loadHistory() {
  const pid = $("#histWho").value; if (!pid) { $("#history").innerHTML = "<p class='lead'>No family members yet.</p>"; return; }
  const h = await api(`/api/history/${pid}`);
  $("#history").innerHTML = h.length ? h.map((m) => `<div class="msg ${m.role}${m.flagged ? " flag" : ""}"><small>${new Date(m.created * 1000).toLocaleString()}${m.flagged ? `<span class="tag">⚑ ${esc(m.flagged)}</span>` : ""}</small>${esc(m.content)}</div>`).join("") : "<p class='lead'>No conversations yet.</p>";
  $("#history").scrollTop = 1e9;
}
$("#histWho").onchange = loadHistory;
$("#histClear").onclick = async () => { if (confirmBox()) { await api(`/api/history/${$("#histWho").value}`, { method: "DELETE" }); loadHistory(); } };
function confirmBox() {
  if (window.TEJAS_WEB) return true; // pop-up boxes are blocked inside the web app frame
  return window.confirm ? window.confirm("Are you sure?") : true;
}
async function loadFamily() {
  await loadProfiles();
  $("#familyList").innerHTML = S.profiles.map((p) => `<div class="fam"><span class="avatar">${esc(initials(p.name))}</span><div>${esc(p.name)}<small>${p.age ? p.age + " yrs" : ""}${p.grade ? " · " + esc(p.grade) : ""}${p.interests ? " · loves " + esc(p.interests) : ""}</small></div><button data-id="${p.id}">Remove</button></div>`).join("");
  $$(".fam button").forEach((b) => b.onclick = async () => { if (confirmBox()) { await api(`/api/profiles/${b.dataset.id}`, { method: "DELETE" }); if (S.who && S.who.id == b.dataset.id) setWho(null); loadFamily(); } });
}
$("#familyForm").onsubmit = async (e) => { e.preventDefault(); try { await api("/api/profiles", { method: "POST", body: formData(e.target) }); e.target.reset(); loadFamily(); } catch (err) { toast("Couldn’t add", err.message); } };
async function loadMind() {
  const pid = $("#mindWho").value; if (!pid) return;
  const fs = await api(`/api/facts/${pid}`);
  $("#mindFacts").innerHTML = fs.length ? fs.map((f) => `<li>${esc(f.text)}<button data-id="${f.id}" aria-label="Forget">Forget</button></li>`).join("") : '<li class="empty">Nothing remembered yet.</li>';
  $$("#mindFacts button").forEach((b) => b.onclick = async () => { await api(`/api/facts/${pid}/${b.dataset.id}`, { method: "DELETE" }); loadMind(); loadFacts(); });
}
$("#mindWho").onchange = loadMind;
async function loadSettings() {
  const [s, v] = await Promise.all([api("/api/settings"), api("/api/voices")]);
  const f = $("#settingsForm");
  $("#voiceEn").innerHTML = Object.entries(v.catalog).filter(([k]) => k.startsWith("en")).map(([k, d]) => `<option value="${k}">${esc(d)}${v.installed.includes(k) ? "" : " (not downloaded)"}</option>`).join("");
  for (const el of f.elements) {
    if (!el.name) continue;
    const val = el.name.split(".").reduce((o, k) => (o || {})[k], s);
    if (el.type === "checkbox") el.checked = !!val; else if (val !== undefined && val !== null) el.value = val;
  }
}
$("#settingsForm").onsubmit = async (e) => {
  e.preventDefault();
  const patch = {};
  for (const [k, v] of Object.entries(formData(e.target))) {
    if (v === null) continue;
    const ks = k.split("."); let o = patch;
    ks.slice(0, -1).forEach((x) => o = o[x] = o[x] || {});
    o[ks.at(-1)] = v;
  }
  try { await api("/api/settings", { method: "PUT", body: patch }); $("#setOk").textContent = "Saved"; setTimeout(() => $("#setOk").textContent = "", 2500); loadStatus(); }
  catch (err) { toast("Couldn’t save", err.message); }
};
$("#newPinForm").onsubmit = async (e) => {
  e.preventDefault();
  const pin = e.target.elements.pin.value;
  try { await api("/api/parent/pin", { method: "POST", body: { pin, old_pin: S.parentPin } }); S.parentPin = pin; $("#pinOk").textContent = "PIN saved"; e.target.reset(); loadStatus(); }
  catch (err) { toast("Couldn’t set PIN", err.message); }
};
async function loadLibrary() {
  const l = await api("/api/library");
  $("#libPath").textContent = l.folder;
  $("#libFiles").innerHTML = l.files.length ? l.files.map((f) => `<li>${esc(f)}</li>`).join("") : '<li class="empty">No books yet.</li>';
}
$("#libReindex").onclick = async () => { const r = await api("/api/library/reindex", { method: "POST" }); $("#libOk").textContent = `${r.files} files ready`; loadLibrary(); };

/* Small forms: new reminder / timer */
function miniForm(title, html, onSubmit) {
  $("#askTitle").textContent = title; const f = $("#miniForm"); f.innerHTML = html + '<div class="form-actions"><button class="btn primary">Save</button></div>';
  f.onsubmit = async (e) => { e.preventDefault(); try { await onSubmit(formData(f)); closeOv(); } catch (err) { toast("Hmm", err.message); } };
  openOv("#ovAsk");
}
$("#btnAddReminder").onclick = () => miniForm("New reminder",
  '<label>What should I remind?<input name="text" required maxlength="200" placeholder="Pack the school bag"></label><label>When?<input name="when" required maxlength="80" placeholder="7 pm, tomorrow 7:30 am, in 20 minutes"></label><label>Repeat<select name="repeat"><option value="none">Just once</option><option value="daily">Every day</option><option value="weekly">Every week</option></select></label>',
  async (d) => { const r = await api("/api/reminders", { method: "POST", body: { ...d, profile_id: S.who ? S.who.id : null } }); toast("Reminder set", `${r.text} — ${r.when_text}`); loadReminders(); });
$("#btnAddTimer").onclick = () => miniForm("New timer",
  '<label>Minutes<input name="minutes" type="number" min="0.1" max="1440" step="0.5" required value="10"></label><label>Name<input name="label" maxlength="40" placeholder="Homework"></label>',
  async (d) => addTimer(Math.round(d.minutes * 60), d.label || "Timer"));

/* ---------------------------------------------------------------- Controls */
$("#mic").onclick = () => { audioCtx(); if (S.state === "speaking") { voiceOut.stop(); return; } if (S.state === "thinking" || S.state === "checking") return; listen(); };
$("#stop").onclick = () => { voiceOut.stop(); if (S.abort) S.abort.abort(); setState("idle"); };
$("#askForm").onsubmit = (e) => { e.preventDefault(); audioCtx(); if (DICT.on) stopDictation(); const v = $("#askInput").value; $("#askInput").value = ""; ask(v); };
function syncToggles() { $("#togDeep").setAttribute("aria-pressed", S.deep); $("#togHands").setAttribute("aria-pressed", S.hands); }
$("#togDeep").onclick = () => { S.deep = !S.deep; store.set("deep", S.deep); syncToggles(); };
$("#togHands").onclick = () => { S.hands = !S.hands; syncToggles(); if (S.hands && S.state === "idle") { audioCtx(); listen(); } };
$("#btnWho").onclick = $("#btnWho2").onclick = () => S.profiles.length ? openWho() : openWelcome();
$("#btnConnect2").onclick = openConnect;
$("#btnNew").onclick = () => { voiceOut.stop(); if (S.abort) S.abort.abort(); setState("idle"); $("#capYou").textContent = ""; $("#capChips").innerHTML = ""; $("#capTejas").textContent = "Fresh start. What shall we do?"; $("#askInput").focus(); };
$("#viewGraph").onclick = () => selectNode("ask");
$$(".node,.tile").forEach((b) => b.onclick = () => selectNode(b.dataset.node));

/* TV remote / keyboard: arrows move between buttons, OK presses. Space = talk. */
function focusables() { const ov = $$(".overlay").find((o) => !o.hidden); return $$("button,input,select,a[href],li[tabindex]", ov || $("#app")).filter((el) => !el.disabled && el.offsetParent !== null); }
document.addEventListener("keydown", (e) => {
  const typing = /INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName);
  if (e.key === "Escape" || e.key === "BrowserBack" || e.keyCode === 10009) { if ($$(".overlay").some((o) => !o.hidden && o.id !== "ovWelcome")) { e.preventDefault(); closeOv(); } else voiceOut.stop(); return; }
  if (!typing && (e.key === " " || e.key === "MediaPlayPause")) { e.preventDefault(); $("#mic").click(); return; }
  const dirs = { ArrowUp: [0, -1], ArrowDown: [0, 1], ArrowLeft: [-1, 0], ArrowRight: [1, 0] };
  if (!dirs[e.key] || (typing && (e.key === "ArrowLeft" || e.key === "ArrowRight"))) return;
  const [dx, dy] = dirs[e.key], cur = document.activeElement && document.activeElement !== document.body ? document.activeElement : null;
  const list = focusables(); if (!list.length) return;
  if (!cur) { e.preventDefault(); $("#mic").focus(); return; }
  const a = cur.getBoundingClientRect(), ax = a.left + a.width / 2, ay = a.top + a.height / 2;
  let best = null, bd = Infinity;
  for (const el of list) {
    if (el === cur) continue;
    const b = el.getBoundingClientRect(), bx = b.left + b.width / 2, by = b.top + b.height / 2, vx = bx - ax, vy = by - ay;
    const along = vx * dx + vy * dy; if (along <= 4) continue;
    const across = Math.abs(vx * dy) + Math.abs(vy * dx), d = along + across * 2.2;
    if (d < bd) { bd = d; best = el; }
  }
  if (best) { e.preventDefault(); best.focus(); best.scrollIntoView({ block: "nearest" }); }
});

/* ---------------------------------------------------------------- Start */
(async function start() {
  syncToggles(); setState("idle"); tickClock();
  setInterval(tickClock, 15000); setInterval(tickTimers, 500); setInterval(loadStatus, 30000);
  selectNode(store.get("node", "ask"));
  await loadStatus();
  try { await loadProfiles(); } catch {}
  if (!S.profiles.length) openWelcome();
  else {
    const saved = S.profiles.find((p) => p.id === store.get("who"));
    if (saved) setWho(saved); else if (S.profiles.length === 1) setWho(S.profiles[0]); else openWho();
  }
  loadReminders(); loadNews(); events();
  if (document.fonts) document.fonts.ready.then(layout);
  // Scanned the QR code in the desktop app: show the iPhone setup steps first.
  if (location.hash === "#iphone" && !matchMedia("(display-mode: standalone)").matches && !navigator.standalone) {
    openConnect(); const t = $('#connectTabs .tab[data-ct="iphone"]'); if (t) t.click();
    history.replaceState(null, "", location.pathname);
  }
  if (!window.TEJAS_WEB && "serviceWorker" in navigator && window.isSecureContext) navigator.serviceWorker.register("sw.js").catch(() => {});
})();

/* Browsers only allow sound after the first tap or key press: unlock it then. */
(() => {
  const unlock = () => {
    try { const c = audioCtx(); if (c && c.state === "suspended") c.resume(); } catch {}
    try { if ("speechSynthesis" in window) { const u = new SpeechSynthesisUtterance(" "); u.volume = 0; speechSynthesis.speak(u); } } catch {}
    removeEventListener("pointerdown", unlock, true); removeEventListener("keydown", unlock, true);
  };
  addEventListener("pointerdown", unlock, true); addEventListener("keydown", unlock, true);
})();
