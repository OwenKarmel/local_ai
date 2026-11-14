"""Eval: run a fixed set of commands against the sample level on each model; report success + latency + speed.

    python -m backend.eval_commands                 # 4B (the default model)
    python -m backend.eval_commands --models 2B,4B,9B

Needs mlx_vlm.server on BONSAI_BASE_URL. Results also saved to backend/data/eval-<timestamp>.json (gitignored).
"""
import argparse
import json
import time
from pathlib import Path

from . import config
from .llm import chat
from .pipeline import run_command
from .prompts import intent_messages
from .schema import Level
from .summary import analyze, regions

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = Level.model_validate_json((ROOT / "backend/levels/sample.json").read_text())


def _of(lv, t):
    return [e for e in lv.entities if e.type == t]


def _gapw(lv):
    return [g["w"] for g in analyze(lv.model_dump())["gaps"]]


def _new(b, a, t):
    old = {e.id for e in _of(b, t)}
    return [e for e in _of(a, t) if e.id not in old]


R = regions(SAMPLE.width)
P5 = {"x": 5, "y": 12, "has_double_jump": False}
P18 = {"x": 18, "y": 12, "has_double_jump": True}


def _ahead(px):
    """Every new or changed entity is at or ahead of the player."""
    def check(b, a):
        old = {e.id: e.model_dump() for e in b.entities}
        touched = [e for e in a.entities if old.get(e.id) != e.model_dump()]
        return bool(touched) and all(e.x + e.w - 1 >= px - 1 for e in touched)
    return check


# (command, player, check(before, after) -> bool). Checks test intent, not exact numbers.
CASES = [
    ("make the gaps bigger", None, lambda b, a: len(_gapw(a)) == len(_gapw(b)) and all(x > y for x, y in zip(_gapw(a), _gapw(b)))),
    ("add three enemies near the end", None, lambda b, a: len(_new(b, a, "enemy")) == 3 and all(e.x >= R["end"][0] for e in _new(b, a, "enemy"))),
    ("make the first gap smaller", None, lambda b, a: sum(_gapw(a)) < sum(_gapw(b))),
    ("put spikes on the floating platforms", None, lambda b, a: len(_new(b, a, "spikes")) >= 2),
    ("make the enemies faster", None, lambda b, a: all(e.props.get("speed", 60) > {x.id: x for x in _of(b, "enemy")}[e.id].props.get("speed", 60) for e in _of(a, "enemy"))),
    ("add some coins in the middle", None, lambda b, a: len(_new(b, a, "coin")) >= 1 and all(R["middle"][0] <= e.x < R["middle"][1] for e in _new(b, a, "coin"))),
    ("make jumping higher", None, lambda b, a: a.physics.jump_velocity > b.physics.jump_velocity),
    ("remove the lava", None, lambda b, a: not _of(a, "lava")),
    ("make the level harder", None, None),  # judged by hand; reported as ops
    ("make the level a bit easier", None, None),
    ("lower the gravity", None, lambda b, a: a.physics.gravity < b.physics.gravity),
    ("add an enemy right in front of me", P5, lambda b, a: len(_new(b, a, "enemy")) == 1 and all(P5["x"] + 1 <= e.x <= P5["x"] + 6 for e in _new(b, a, "enemy"))),
    ("make this harder", P18, _ahead(P18["x"])),
]


def speed(model: str) -> dict:
    """Decode tok/s (long output, tiny prompt) and prefill tok/s (real prompt, 1 output token)."""
    chat(model, [{"role": "user", "content": "Say hi."}], max_tokens=4)  # warm-up / load
    r = chat(model, [{"role": "user", "content": "Write the numbers from 1 to 150 separated by spaces."}], max_tokens=300)
    dec = r["usage"].get("completion_tokens", 0) / (r["latency_ms"] / 1000)
    p = chat(model, intent_messages(SAMPLE.model_dump(), "make the gaps bigger", P18), max_tokens=1)
    pre = p["usage"].get("prompt_tokens", 0) / (p["latency_ms"] / 1000)
    return {"decode_tok_s": round(dec, 1), "prefill_tok_s": round(pre), "prompt_tokens": p["usage"].get("prompt_tokens")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="4B")
    args = ap.parse_args()
    base = Path(config.CODE_MODEL).parent
    out = {}
    for size in args.models.split(","):
        model = str(base / f"Ternary-Bonsai-2-{size}-mlx-2bit")
        sp = speed(model)
        print(f"\n## {size}: decode {sp['decode_tok_s']} tok/s, prefill {sp['prefill_tok_s']} tok/s ({sp['prompt_tokens']} prompt tokens)")
        print("| command | player x | status | intent check | model calls | latency s | spoken |\n|---|---|---|---|---|---|---|")
        rows = []
        for cmd, player, check in CASES:
            r = run_command(SAMPLE, cmd, model, player)
            calls = sum(1 for s in r["log"] if s["step"] == "model")
            after = Level.model_validate(r["level"])
            passed = None if (check is None or not r["ok"]) else bool(check(SAMPLE, after))
            row = {"command": cmd, "player": player, "status": r["status"], "ok": r["ok"], "check": passed, "calls": calls,
                   "latency_s": round(r["latency_ms"] / 1000, 1), "spoken": r["spoken"], "reason": r["reason"],
                   "patch": r["patch"], "log": r["log"]}
            rows.append(row)
            print(f"| {cmd} | {player['x'] if player else '—'} | {r['status']} | {'—' if passed is None else ('✅' if passed else '❌')} | {calls} | {row['latency_s']} | {r['spoken'][:90]} |")
        ok = sum(r["ok"] for r in rows)
        chk = [r["check"] for r in rows if r["check"] is not None]
        print(f"**{size}: {ok}/{len(rows)} applied, {sum(chk)}/{len(chk)} intent checks passed, "
              f"median latency {sorted(r['latency_s'] for r in rows)[len(rows) // 2]} s**")
        out[size] = {"speed": sp, "rows": rows}
    d = ROOT / "backend" / "data"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"eval-{time.strftime('%H%M%S')}.json"
    f.write_text(json.dumps(out, indent=1))
    print(f"\nsaved {f}")


if __name__ == "__main__":
    main()
