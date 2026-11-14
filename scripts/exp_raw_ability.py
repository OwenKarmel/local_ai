"""Experiment: can Bonsai write a working ability against the RAW Phaser scene (no helper layer)?

    python scripts/exp_raw_ability.py gen    --models 4B,9B --runs 5 --text "give me fireball powers"
    python scripts/exp_raw_ability.py repair --results frontend/exp/results.json

`gen` writes attempt-1 code to frontend/exp/<model>_r<run>_a1.json (+ frontend/exp/index.json).
A browser harness (see plan.md / PR) installs each one in the game and tests it, writing results.json.
`repair` asks the model once more for runs that failed with a syntax or runtime error (like production:
only errors are fed back, not "it didn't do what you asked"), writing <model>_r<run>_a2.json.
"""
import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend import config  # noqa: E402
from backend.llm import chat  # noqa: E402

OUT = ROOT / "frontend" / "exp"
# Bonsai model card's non-thinking sampler. A first try with temperature 0.3 and no presence penalty made the 4B
# loop on one line ("this.projectile.setCollideWorldBounds(true);") until max_tokens, identically on every run.
CODE_SAMPLER = {"temperature": 0.7, "top_p": 0.8, "top_k": 20, "presence_penalty": 1.5}

SYSTEM = """You write JavaScript that adds a new ability or behavior to a running Phaser 3.80 platformer (Arcade Physics).
There is no helper library: use the Phaser scene directly.

Reply with ONLY JSON: {"explanation": "<one sentence>", "keys": ["F"], "code": "<JavaScript>"}
- keys: the keyboard keys the player presses to use it (single letters A-Z or "SPACE"); [] if none.
- code registers exactly one ability:
    ABILITIES["name"] = {
      setup(scene) { ... },       // runs when the level starts and again after every restart
      update(scene, dt) { ... }   // runs every frame; dt in seconds
    };
  Keep your state on the ability object (this.something = ...). Create keys, groups and colliders in setup.

THE SCENE (scene = the running Phaser.Scene)
- scene.player: Arcade sprite with a 24x30 px body. scene.player.flipX is true when facing left, false when facing right.
- scene.enemies: Arcade physics group of enemy sprites. An enemy is defeated with enemy.disableBody(true, true).
- scene.platforms: static physics group (ground and platforms). scene.hazards: static group (spikes, lava).
- scene.physics (Arcade physics: scene.physics.add.sprite/group/collider/overlap), scene.add (game objects),
  scene.time (timers: scene.time.delayedCall / addEvent), scene.input.keyboard (keys), scene.tweens.
- scene.TILE = 32 px per tile. World gravity: scene.physics.world.gravity.y (pixels/s^2).
- Textures: "fx_ball" (14 px white circle), "fx_dot" (8 px white dot), "player", "enemy". Color with sprite.setTint(0xff8800).
- Phaser is a global (e.g. Phaser.Input.Keyboard.JustDown(key)).
RULES: no network, no DOM, don't replace scene.player or the scene's groups, don't edit other code."""

EXAMPLE_CMD = "let me dash forward when I press Q"
EXAMPLE = {
    "explanation": "Q gives a short burst of speed in the facing direction, with a cooldown.",
    "keys": ["Q"],
    "code": """ABILITIES["dash"] = {
  setup(scene) {
    this.key = scene.input.keyboard.addKey("Q");
    this.until = 0;
    this.ready = 0;
  },
  update(scene, dt) {
    const now = scene.time.now, p = scene.player;
    if (Phaser.Input.Keyboard.JustDown(this.key) && now >= this.ready) {
      this.dir = p.flipX ? -1 : 1;
      this.until = now + 180;
      this.ready = now + 800;
      p.setTint(0x88ccff);
    }
    if (now < this.until) p.setVelocityX(this.dir * 600);
    else if (this.until) { p.clearTint(); this.until = 0; }
  }
};""",
}


SYSTEM_API = """You write JavaScript that adds a new ability or behavior to a running 2D platformer.

Reply with ONLY JSON: {"explanation": "<one sentence>", "keys": ["F"], "code": "<JavaScript>"}
- keys: the keyboard keys the player presses to use it (single letters A-Z or "SPACE"); [] if none.
- code registers exactly one ability:
    ABILITIES["name"] = {
      setup(scene, api) { ... },       // runs when the level starts and again after every restart
      update(scene, dt, api) { ... }   // runs every frame; dt in seconds
    };
  Keep your state on the ability object (this.something = ...).

API (use ONLY these, plus sprite.x, sprite.y, sprite.setVelocity(vx, vy), sprite.setTint(0xRRGGBB), sprite.clearTint(), sprite.destroy()):
- api.key(name) -> k; k.pressed() is true only on the frame the key goes down; k.down() while held. name: "A".."Z", "SPACE", "SHIFT"
- api.spawn(texture, x, y, {vx, vy, gravity, tint, scale, bounce, lifeMs, solid}) -> sprite. gravity defaults to true; solid (stops on platforms) defaults to true; lifeMs removes it after that time
- api.onHit(a, b, fn) calls fn(a, b) every time a overlaps b. a, b: a sprite, or "player" | "enemies" | "platforms" | "hazards"
- api.defeat(enemy) defeats an enemy
- api.enemies() -> list of active enemy sprites
- api.player is the player sprite (24x30 px); api.facing() -> 1 facing right, -1 facing left
- api.after(ms, fn); api.every(ms, fn); api.now() -> milliseconds
- api.TILE = 32 (pixels per tile)
- Textures: "fx_ball" (14 px circle), "fx_dot" (8 px dot), "player", "enemy"
Nothing affects enemies, platforms or the player unless your code makes it happen (e.g. with api.onHit).
RULES: no network, no DOM, don't edit other code."""

EXAMPLE_API = {
    "explanation": "Q gives a short burst of speed in the facing direction, with a cooldown.",
    "keys": ["Q"],
    "code": """ABILITIES["dash"] = {
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
};""",
}
MODE = {"api": False}


def messages(text: str) -> list[dict]:
    system, ex = (SYSTEM_API, EXAMPLE_API) if MODE["api"] else (SYSTEM, EXAMPLE)
    return [{"role": "system", "content": system},
            {"role": "user", "content": EXAMPLE_CMD}, {"role": "assistant", "content": json.dumps(ex)},
            {"role": "user", "content": text}]


SCHEMA = {"type": "object", "properties": {"explanation": {"type": "string"},
                                           "keys": {"type": "array", "items": {"type": "string"}},
                                           "code": {"type": "string"}},
          "required": ["explanation", "keys", "code"], "additionalProperties": False}


def syntax_check(code: str) -> str | None:
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write("(function (ABILITIES, Phaser) {\n" + code + "\n});\n")
    p = subprocess.run(["node", "--check", f.name], capture_output=True, text=True)
    return None if p.returncode == 0 else p.stderr.strip().splitlines()[-1][:300] if p.stderr.strip() else "syntax error"


def model_path(size: str) -> str:
    return str(Path(config.CODE_MODEL).parent / f"Ternary-Bonsai-2-{size}-mlx-2bit")


def ask(model: str, msgs: list[dict]) -> dict:
    r = chat(model, msgs, schema=SCHEMA, max_tokens=1000, timeout=300, sampler=CODE_SAMPLER)
    try:
        d = json.loads(r["text"])
    except json.JSONDecodeError as e:
        d = {"explanation": "", "keys": [], "code": "", "parse_error": str(e)}
    d.update(latency_ms=r["latency_ms"], tokens_in=r["usage"].get("prompt_tokens"), tokens_out=r["usage"].get("completion_tokens"),
             raw=r["text"])
    d["code_lines"] = sum(1 for ln in d.get("code", "").splitlines() if ln.strip())
    d["syntax_error"] = syntax_check(d["code"]) if d.get("code") else "no code"
    return d


def write(rec: dict):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{rec['id']}.json").write_text(json.dumps(rec, indent=1))
    idx_p = OUT / "index.json"
    idx = json.loads(idx_p.read_text()) if idx_p.exists() else []
    idx = [i for i in idx if i != rec["id"]] + [rec["id"]]
    idx_p.write_text(json.dumps(idx))


def gen(args):
    if (OUT / "index.json").exists():
        (OUT / "index.json").unlink()
    for size in args.models.split(","):
        m = model_path(size)
        chat(m, [{"role": "user", "content": "hi"}], max_tokens=2)  # load / warm up
        for run in range(1, args.runs + 1):
            d = ask(m, messages(args.text))
            rec = {"id": f"{size}_r{run}_a1", "model": size, "run": run, "attempt": 1, "text": args.text, **d}
            if d["syntax_error"] and args.repair_syntax:  # syntax errors are caught before the game: repair right away
                write(rec)
                d2 = ask(m, messages(args.text) + [{"role": "assistant", "content": d["raw"]}, repair_msg("Syntax error: " + d["syntax_error"])])
                rec = {"id": f"{size}_r{run}_a2", "model": size, "run": run, "attempt": 2, "text": args.text, **d2,
                       "attempt1_latency_ms": d["latency_ms"]}
            write(rec)
            print(f"{rec['id']}: {rec['latency_ms']/1000:.1f}s lines={rec['code_lines']} keys={rec.get('keys')} syntax={rec['syntax_error'] or 'ok'}", flush=True)


def repair_msg(err: str) -> dict:
    return {"role": "user", "content": f"That code failed in the game:\n{err}\n\nFix it. Reply with the whole corrected JSON object only."}


def repair(args):
    results = json.loads(Path(args.results).read_text())
    for r in results:
        if r.get("attempt") != 1 or r.get("ok") or not r.get("error"):
            continue  # only runtime/syntax errors get a repair (production can't detect "runs but does nothing")
        prev = json.loads((OUT / f"{r['id']}.json").read_text())
        m = model_path(prev["model"])
        d = ask(m, messages(prev["text"]) + [{"role": "assistant", "content": prev["raw"]}, repair_msg(r["error"])])
        rec = {"id": f"{prev['model']}_r{prev['run']}_a2", "model": prev["model"], "run": prev["run"], "attempt": 2,
               "text": prev["text"], **d, "attempt1_latency_ms": prev["latency_ms"]}
        write(rec)
        print(f"{rec['id']}: {rec['latency_ms']/1000:.1f}s lines={rec['code_lines']} syntax={rec['syntax_error'] or 'ok'}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gen")
    g.add_argument("--models", default="4B,9B")
    g.add_argument("--runs", type=int, default=5)
    g.add_argument("--text", default="give me fireball powers")
    g.add_argument("--repair-syntax", action="store_true", default=True)
    g.add_argument("--api", action="store_true", help="use the mechanics API prompt instead of raw Phaser")
    rp = sub.add_parser("repair")
    rp.add_argument("--results", default=str(OUT / "results.json"))
    rp.add_argument("--api", action="store_true")
    a = ap.parse_args()
    MODE["api"] = a.api
    gen(a) if a.cmd == "gen" else repair(a)
