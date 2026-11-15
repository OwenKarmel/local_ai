// demo.js — clean "demo video" mode: the game fills the screen, a small mic button sits in the corner,
// and a short caption shows what was heard and what the copilot did. Developer mode is unchanged.
// Turn on: open /?demo, press Shift+D, or click "🎬 Demo mode" in the panel. Esc (or Shift+D) turns it off.
(function () {
  const $ = (id) => document.getElementById(id);
  const body = document.body;
  const typing = () => ["INPUT", "TEXTAREA"].includes(document.activeElement && document.activeElement.tagName);

  function refreshScale() {
    const sc = window.Callout && window.Callout.scene;
    if (sc && sc.scale) sc.scale.refresh(); // keep mouse/pointer coordinates right after the canvas is resized
  }

  function setDemo(on) {
    body.classList.toggle("demo", on);
    history.replaceState(null, "", on ? "?demo" : location.pathname);
    setTimeout(refreshScale, 50);
  }

  if (new URLSearchParams(location.search).has("demo")) setDemo(true);
  window.addEventListener("resize", () => setTimeout(refreshScale, 50));
  window.addEventListener("keydown", (e) => {
    if (typing()) return;
    if (e.shiftKey && (e.key === "D" || e.key === "d")) { e.preventDefault(); setDemo(!body.classList.contains("demo")); }
    else if (e.key === "Escape" && body.classList.contains("demo")) setDemo(false);
  });
  $("demo-btn").addEventListener("click", () => setDemo(true));

  // Small mic button: same as holding the big button or V.
  const mic = $("mini-mic"), big = $("talk-btn");
  const press = (type) => big.dispatchEvent(new PointerEvent(type, { bubbles: true }));
  mic.addEventListener("pointerdown", (e) => { e.preventDefault(); press("pointerdown"); });
  ["pointerup", "pointerleave", "pointercancel"].forEach((t) => mic.addEventListener(t, () => press("pointerup")));
  new MutationObserver(() => mic.classList.toggle("recording", big.classList.contains("recording")))
    .observe(big, { attributes: true, attributeFilter: ["class"] });

  // Caption: mirrors what voice.js shows in the panel, then fades.
  const cap = $("caption");
  let timer = 0;
  function show() {
    const heard = $("voice-heard").textContent.trim(), reply = $("voice-reply").textContent.trim();
    if (!heard && !reply) return;
    cap.innerHTML = "";
    if (heard) { const d = document.createElement("div"); d.className = "heard"; d.textContent = heard; cap.appendChild(d); }
    if (reply) {
      const d = document.createElement("div");
      d.className = "reply " + ($("voice-reply").className || "");
      d.textContent = reply;
      cap.appendChild(d);
    }
    cap.classList.add("show");
    clearTimeout(timer);
    timer = setTimeout(() => cap.classList.remove("show"), reply ? 6000 : 15000);
  }
  ["voice-heard", "voice-reply"].forEach((id) => new MutationObserver(show).observe($(id), { childList: true, characterData: true, subtree: true }));
})();
