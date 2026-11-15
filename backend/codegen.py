"""Code escalation: write a new ability/behavior with the code model (Bonsai 9B by default).

The level model (4B) decides a command needs new code by emitting a `write_code` op; the pipeline calls
generate(). The reply is schema-enforced JSON {explanation, keys, code}. (A plain-text fenced-code format was tried:
the 9B's code then defeated enemies 0/5 twice, vs 5/5 with JSON; plan.md decisions 11-14.) The code is syntax-checked with node and repaired once on error.
Runtime errors are caught in the browser sandbox (frontend/game.js) and disable the ability.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import time

from . import config
from .llm import SAMPLER, LLMError, chat, short_name

SYSTEM = """You write JavaScript that adds a new ability or behavior to a running 2D platformer.

Reply with ONLY JSON: {"explanation": "<one sentence>", "keys": ["F"], "code": "<JavaScript>"}
- keys: the keyboard keys the player presses to use it (single letters A-Z or "SPACE"); [] if none.
- code registers exactly one ability:
    ABILITIES["name"] = {
      setup(scene, api) { ... },       // runs when the level starts and again after every restart
      update(scene, dt, api) { ... }   // runs every frame; dt in seconds
    };
  Keep your state on the ability object (this.something = ...).

API (use ONLY these, plus sprite.x, sprite.y, sprite.setVelocity(vx, vy), sprite.setTint(0xRRGGBB), sprite.clearTint(), sprite.destroy()):
- api.key(name) -> k; k.pressed() is true once per key press; k.down() while held. name: "A".."Z", "SPACE", "SHIFT"
- api.spawn(texture, x, y, {vx, vy, gravity, tint, scale, bounce, lifeMs, solid}) -> sprite. gravity defaults to true; solid (stops on platforms) defaults to true; lifeMs removes it after that time
- api.projectile(x, y, dir, {speed, fire, tint, life_ms}) -> projectile. fire:true uses a Kenney fireball with glow, flicker, Phaser particle trail and impact burst; it vanishes on impact when registered with api.onHit
- api.onHit(a, b, fn): every time a overlaps b, calls fn(objA, objB) with the two OBJECTS that touched (never strings); with "enemies", objB is the enemy that was hit. a, b: a sprite, or "player" | "enemies" | "platforms" | "hazards". Call it inside setup or update (api only exists there), once per sprite, e.g. right after spawning it. Spawned sprites also have sprite.onHit(b, fn)
- api.hurt(enemy, amount) damages an enemy (amount defaults to 1): normal enemies die from one hit, bosses have more hp. Use it for attacks.
- api.defeat(enemy) removes an enemy instantly, whatever its hp
- api.enemies() -> list of active enemy sprites
- api.player is the player sprite (24x30 px); api.facing() -> 1 facing right, -1 facing left
- api.after(ms, fn); api.every(ms, fn); api.now() -> milliseconds
- api.TILE = 32 (pixels per tile)
- Any platform can move with props.motion_dx, props.motion_dy (signed tile offsets) and props.motion_period (seconds), set through the normal set_property building block; the engine carries riders.
- Textures: "fx_ball" (14 px circle), "fx_dot" (8 px dot), "player", "enemy"
Nothing affects enemies, platforms or the player unless your code makes it happen (e.g. with api.onHit).
RULES: no network, no DOM, don't edit other code."""

EXAMPLE_CMD = "let me dash forward when I press Q"
EXAMPLE_REPLY = json.dumps({"explanation": "Q gives a short burst of speed in the facing direction, with a cooldown.", "keys": ["Q"], "code": """ABILITIES["dash"] = {
  setup(scene, api) {
    this.key = api.key("Q");
    this.until = 0;
    this.ready = 0;
  },
  update(scene, dt, api) {
    const now = api.now(), p = api.player;
    if (this.key.pressed() && now >= this.ready) {
      this.dir = api.facing();
      this.until = now + 180;
      this.ready = now + 800;
      p.setTint(0x88ccff);
    }
    if (now < this.until) p.setVelocity(this.dir * 600, 0);
    else if (this.until) { p.clearTint(); this.until = 0; }
  }
};"""})

_FENCE = re.compile(r"```(?:js|javascript)?\s*\n(.*?)```", re.S)
_NAME = re.compile(r"""ABILITIES\[\s*["']([A-Za-z0-9_\- ]+)["']\s*\]""")


def messages(command: str, what: str) -> list[dict]:
    return [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": EXAMPLE_CMD}, {"role": "assistant", "content": EXAMPLE_REPLY},
            {"role": "user", "content": f"{command}\n(What to build: {what})" if what and what != command else command}]


SCHEMA = {"type": "object", "properties": {"explanation": {"type": "string"},
                                           "keys": {"type": "array", "items": {"type": "string"}},
                                           "code": {"type": "string"}},
          "required": ["explanation", "keys", "code"], "additionalProperties": False}


def parse(text: str) -> dict:
    """JSON reply (the default; schema-enforced). Falls back to a KEYS line + ```js block."""
    try:
        d = json.loads(text)
        code = (d.get("code") or "").strip()
        nm = _NAME.search(code)
        return {"code": code, "keys": [str(k).strip().upper() for k in d.get("keys") or [] if str(k).strip()],
                "name": nm.group(1).strip().replace(" ", "_") if nm else None, "explanation": d.get("explanation", "")}
    except (ValueError, AttributeError):
        pass
    m = _FENCE.search(text)
    code = (m.group(1) if m else "").strip()
    km = re.search(r"KEYS:\s*(.+)", text)
    keys = [] if not km else [k.strip().upper() for k in re.split(r"[ ,/]+", km.group(1)) if k.strip() and k.strip().lower() != "none"]
    nm = _NAME.search(code)
    return {"code": code, "keys": keys, "name": nm.group(1).strip().replace(" ", "_") if nm else None}


def syntax_error(code: str) -> str | None:
    """node --check on the code wrapped like the browser runs it. None if fine (or node missing)."""
    node = shutil.which("node")
    if not node:
        return None
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write("(function (ABILITIES, Phaser) {\n" + code + "\n});\n")
    p = subprocess.run([node, "--check", f.name], capture_output=True, text=True, timeout=20)
    if p.returncode == 0:
        return None
    lines = p.stderr.strip().splitlines()
    err = next((ln for ln in lines if "Error" in ln), "syntax error")
    m = next((re.search(r"\.js:(\d+)$", ln) for ln in lines if re.search(r"\.js:(\d+)$", ln)), None)
    n = int(m.group(1)) - 1 if m else None
    src = code.splitlines()[n - 1].strip()[:120] if n and 0 < n <= len(code.splitlines()) else ""
    return f"{err} at line {n if n else '?'}: {src}"


_LOAD_CHECK = r"""
const vm = require("vm"), fs = require("fs");
const code = fs.readFileSync(process.argv[2], "utf8");
const ctx = { ABILITIES: {}, Phaser: {}, Math, JSON, console: { log() {} } };
try {
  vm.runInNewContext(code, ctx, { timeout: 1000 });
  const names = Object.keys(ctx.ABILITIES);
  if (names.length !== 1) throw new Error(`the code must register exactly one ability (got ${names.length})`);
  const ab = ctx.ABILITIES[names[0]];
  if (!ab || typeof ab !== "object" || typeof ab.update !== "function" && typeof ab.setup !== "function")
    throw new Error("the ability needs setup(scene, api) and/or update(scene, dt, api) methods");
} catch (e) { console.error(String(e && e.message || e)); process.exit(1); }
"""


def load_error(code: str) -> str | None:
    """Run the code's top level in an isolated Node vm context (no require/process; fs denied by --permission).
    Catches what a syntax check can't: code outside the ability object (e.g. 'api is not defined')."""
    node = shutil.which("node")
    if not node:
        return None
    with tempfile.TemporaryDirectory() as d:
        d = os.path.realpath(d)  # macOS: /var -> /private/var; --allow-fs-read needs the real path
        runner, src = f"{d}/check.js", f"{d}/ability.js"
        open(runner, "w").write(_LOAD_CHECK)
        open(src, "w").write(code)
        p = subprocess.run([node, "--permission", f"--allow-fs-read={d}", runner, src], capture_output=True, text=True, timeout=20)
    if p.returncode == 0:
        return None
    msg = (p.stderr.strip().splitlines() or ["load error"])[-1][:200]
    return f"Running the code's top level failed: {msg}. Everything must be inside the ABILITIES[...] object's setup/update."


def generate(command: str, what: str, model: str | None = None, base_url: str | None = None) -> dict:
    """Returns {ok, name, code, keys, lines, attempts, latency_ms, model, error}."""
    model = model or config.CODE_GEN_MODEL
    base_url = base_url or config.CODE_GEN_BASE_URL
    msgs = messages(command, what)
    t0 = time.perf_counter()
    out = {"ok": False, "name": None, "code": "", "keys": [], "lines": 0, "attempts": 0, "model": short_name(model), "error": None}
    for attempt in (1, 2):  # one repair
        out["attempts"] = attempt
        try:
            r = chat(model, msgs, schema=SCHEMA, max_tokens=900, timeout=180, sampler=SAMPLER, base_url=base_url)
        except LLMError as e:
            out["error"] = str(e)
            break
        p = parse(r["text"])
        out.update(code=p["code"], keys=p["keys"], name=p["name"], lines=sum(1 for ln in p["code"].splitlines() if ln.strip()))
        err = ("No ```js code block in the reply." if not p["code"] else
               "The code must register exactly one ability: ABILITIES[\"name\"] = { setup(scene, api) {...}, update(scene, dt, api) {...} };"
               if not p["name"] else syntax_error(p["code"]) or load_error(p["code"]))
        if not err:
            out["ok"] = True
            out["error"] = None
            break
        out["error"] = err
        msgs = msgs + [{"role": "assistant", "content": r["text"]},
                       {"role": "user", "content": f"That code has a problem: {err}\nFix it. Reply with the whole corrected JSON object only."}]
    out["latency_ms"] = int((time.perf_counter() - t0) * 1000)
    return out
