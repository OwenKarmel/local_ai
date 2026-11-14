// voice.js — hold-to-talk (button or V key) + typed commands.
// Mic -> POST /api/transcribe (Argmax) -> POST /api/command -> apply level -> POST /api/speak.
// Shows clearly when it's listening (red badge on the game + live mic level), transcribing, and thinking.
(function () {
  const $ = (id) => document.getElementById(id);
  const S = () => window.Sketch2Game;
  const ui = {
    btn: $("talk-btn"), meter: $("mic-level"), status: $("voice-status"), heard: $("voice-heard"),
    reply: $("voice-reply"), badge: $("listen-badge"), flag: $("flag-btn"),
  };

  // Every command is saved as a trace on the backend. The flag button marks the last one as wrong
  // (e.g. it applied but did the wrong thing), so it shows up in `python -m backend.traces --failures`.
  let lastTrace = null;
  window.Sketch2Game_setLastTrace = (id, text) => {
    lastTrace = id ? { id, text } : null;
    ui.flag.hidden = !lastTrace;
    ui.flag.disabled = false;
    ui.flag.textContent = "👎 Wrong result";
  };
  ui.flag.addEventListener("click", async () => {
    ui.flag.blur();  // otherwise Space (jump) re-clicks it
    if (!lastTrace) return;
    const note = window.prompt(`What went wrong with "${lastTrace.text}"? (optional)`, "");
    if (note === null) return;
    try {
      const r = await fetch(`/api/traces/${encodeURIComponent(lastTrace.id)}/flag`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ note }),
      });
      if (!r.ok) throw new Error(`flag failed (${r.status})`);
      ui.flag.textContent = "Flagged ✓";
      ui.flag.disabled = true;
      log(`flagged trace ${lastTrace.id}${note ? ": " + note : ""}`, "info");
    } catch (e) { log(e.message, "error"); }
  });

  let stream = null, recorder = null, chunks = [], startedAt = 0, analyser = null, raf = 0, busy = false;

  function setStatus(text, kind = "") {
    ui.status.textContent = text;
    ui.status.className = kind;
    ui.badge.textContent = kind === "listening" ? "● LISTENING" : kind === "working" ? text : "";
    ui.badge.className = kind ? "show " + kind : "";
  }

  function log(msg, kind) { if (S() && S().log) S().log(msg, kind); }

  async function ensureMic() {
    if (stream) return true;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    } catch (e) {
      setStatus("Microphone blocked: allow it in the browser's address bar (🔒 icon), then try again.", "error");
      return false;
    }
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    analyser = ctx.createAnalyser();
    analyser.fftSize = 512;
    ctx.createMediaStreamSource(stream).connect(analyser);
    return true;
  }

  function meterLoop() {
    const buf = new Uint8Array(analyser.fftSize);
    const tick = () => {
      analyser.getByteTimeDomainData(buf);
      let sum = 0;
      for (const v of buf) sum += ((v - 128) / 128) ** 2;
      const rms = Math.sqrt(sum / buf.length);
      ui.meter.style.width = Math.min(100, rms * 400) + "%";
      raf = requestAnimationFrame(tick);
    };
    tick();
  }

  async function startListening() {
    if (busy || (recorder && recorder.state === "recording")) return;
    if (!(await ensureMic())) return;
    if (analyser.context.state === "suspended") analyser.context.resume();
    chunks = [];
    const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "";
    recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
    recorder.onstop = onRecorded;
    recorder.start();
    startedAt = performance.now();
    ui.btn.classList.add("recording");
    setStatus("● Listening… release to send", "listening");
    meterLoop();
  }

  function stopListening() {
    if (!recorder || recorder.state !== "recording") return;
    recorder.stop();
    ui.btn.classList.remove("recording");
    cancelAnimationFrame(raf);
    ui.meter.style.width = "0%";
  }

  async function onRecorded() {
    const held = performance.now() - startedAt;
    if (held < 350) { setStatus("Too short: hold the button (or V) while you speak.", "error"); return; }
    const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
    busy = true;
    setStatus("Transcribing (Argmax)…", "working");
    try {
      const fd = new FormData();
      fd.append("audio", blob, "speech.webm");
      const r = await fetch("/api/transcribe", { method: "POST", body: fd });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || `transcribe failed (${r.status})`);
      if (!d.text) { setStatus("Didn't catch that. Try again, a bit louder.", "error"); return; }
      ui.heard.textContent = `“${d.text}”  · ${d.latency_ms} ms`;
      await sendCommand(d.text, "voice");
    } catch (e) {
      setStatus(e.message, "error");
      log(e.message, "error");
    } finally {
      busy = false;
    }
  }

  // Shared with testwin.js (typed commands).
  window.Sketch2Game_playerState = () => playerState();
  function playerState() {
    const sc = S() && S().scene;
    if (!sc || !sc.player || !sc.sys.isActive()) return null;
    return { x: Math.floor(sc.player.x / 32), y: Math.floor(sc.player.y / 32), has_double_jump: !!sc.hasDoubleJump, is_big: !!sc.isBig };
  }

  async function sendCommand(text, source) {
    busy = true;
    setStatus("Thinking (Bonsai)…", "working");
    ui.reply.textContent = "";
    try {
      const r = await fetch("/api/command", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, source, speaker: null, player: playerState() }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail ? JSON.stringify(d.detail) : `command failed (${r.status})`);
      window.Sketch2Game_setLastTrace(d.trace_id, text);
      const secs = (d.latency_ms / 1000).toFixed(1);
      ui.reply.textContent = `${d.spoken}  · ${d.status} · ${d.model || "?"} · ${secs} s`;
      ui.reply.className = d.status;
      if (d.reason) log(`${d.status}: ${d.reason}`, "error");
      log(`[${source}] "${text}" → ${d.status} (${secs} s): ${d.spoken}`, d.status === "applied" ? "ok" : "error");
      // Live apply (task 7): no restart; falls back to a reload inside applyPatch if it fails.
      if (d.status === "applied" && d.level) S().applyPatch(d.patch, d.level, d.spoken, d.stage);
      setStatus(d.status === "applied" ? "Done. Hold to talk again." : d.status === "refused" ? "Refused." : "Error.",
                d.status === "applied" ? "" : "error");
      speak(d.spoken, d.status === "refused" ? "refusal" : "normal");
    } catch (e) {
      setStatus(e.message, "error");
      log(e.message, "error");
    } finally {
      busy = false;
    }
  }

  async function speak(text, style) {
    if (!text) return;
    try {
      const r = await fetch("/api/speak", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, style }) });
      if (!r.ok) return;
      const url = URL.createObjectURL(await r.blob());
      const a = new Audio(url);
      a.onended = () => URL.revokeObjectURL(url);
      a.play().catch(() => {});
    } catch (_) { /* speech is optional */ }
  }

  // ----- wiring -----
  ui.btn.addEventListener("pointerdown", (e) => { e.preventDefault(); startListening(); });
  ["pointerup", "pointerleave", "pointercancel"].forEach((ev) => ui.btn.addEventListener(ev, stopListening));

  const typing = () => ["INPUT", "TEXTAREA"].includes(document.activeElement && document.activeElement.tagName);
  window.addEventListener("keydown", (e) => {
    if ((e.key === "v" || e.key === "V") && !e.repeat && !typing()) { e.preventDefault(); startListening(); }
  });
  window.addEventListener("keyup", (e) => { if ((e.key === "v" || e.key === "V") && !typing()) stopListening(); });

  setStatus("Hold the button or V to talk.");
})();
