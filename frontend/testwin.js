// Text command window: optional typed input for /api/command (voice is the main input; see voice.js).
(function () {
  const form = document.getElementById("cmd-form");
  const input = document.getElementById("cmd-input");
  const out = document.getElementById("cmd-out");
  // Keep typing from reaching the game's key handlers (WASD, space, R).
  ["keydown", "keyup", "keypress"].forEach((t) => input.addEventListener(t, (e) => e.stopPropagation()));

  function add(cls, text) {
    const d = document.createElement("div");
    d.className = "entry " + cls;
    d.textContent = text;
    out.appendChild(d);
    out.scrollTop = out.scrollHeight;
  }

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    add("info", "> " + text);
    try {
      const t0 = performance.now();
      const res = await fetch("/api/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, source: "typed", speaker: null, player: window.Sketch2Game_playerState ? window.Sketch2Game_playerState() : null }),
      });
      if (!res.ok) throw new Error("HTTP " + res.status);
      const r = await res.json();
      const ms = Math.round(performance.now() - t0);
      add(r.status === "applied" ? "ok" : "error", `[${r.status}] ${r.spoken || ""}`);
      if (r.reason) add("info", "reason: " + r.reason);
      add("info", `route=${r.route} model=${String(r.model).split("/").pop()} v${r.version} server=${r.latency_ms}ms total=${ms}ms ops=${r.patch.length}`);
      if (r.status === "applied") {
        const S = window.Sketch2Game;
        if (typeof S.applyPatch === "function") S.applyPatch(r.patch, r.level, r.spoken); // live apply (task 7), when it exists
        else S.loadLevel(r.level);                                                       // until then: reload the level
      }
    } catch (e) {
      add("error", "request failed: " + e.message);
    }
  });
})();
