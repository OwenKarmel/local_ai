"""Eval: run a fixed set of commands against the sample level on each model; report success + latency + speed.

    python -m backend.eval_commands                 # 9B and 4B
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
# (command, check(before, after) -> bool). Checks test intent, not exact numbers.
CASES = [
    ("make the gaps bigger", lambda b, a: len(_gapw(a)) == len(_gapw(b)) and all(x > y for x, y in zip(_gapw(a), _gapw(b)))),
    ("add three enemies near the end", lambda b, a: len(_new(b, a, "enemy")) == 3 and all(e.x >= R["end"][0] for e in _new(b, a, "enemy"))),
    ("make the first gap smaller", lambda b, a: sum(_gapw(a)) < sum(_gapw(b))),
    ("put spikes on the floating platforms", lambda b, a: len(_new(b, a, "spikes")) >= 2),
    ("make the enemies faster", lambda b, a: all(e.props.get("speed", 60) > {x.id: x for x in _of(b, "enemy")}[e.id].props.get("speed", 60) for e in _of(a, "enemy"))),
    ("add some coins in the middle", lambda b, a: len(_new(b, a, "coin")) >= 1 and all(R["middle"][0] <= e.x < R["middle"][1] for e in _new(b, a, "coin"))),
    ("make jumping higher", lambda b, a: a.physics.jump_velocity > b.physics.jump_velocity),
    ("remove the lava", lambda b, a: not _of(a, "lava")),
    ("make the level harder", None),  # judged by hand; reported as ops
    ("make the level a bit easier", None),
]


def speed(model: str) -> dict:
    """Decode tok/s (long output, tiny prompt) and prefill tok/s (real prompt, 1 output token)."""
    chat(model, [{"role": "user", "content": "Say hi."}], max_tokens=4)  # warm-up / load
    r = chat(model, [{"role": "user", "content": "Write the numbers from 1 to 150 separated by spaces."}], max_tokens=300)
    dec = r["usage"].get("completion_tokens", 0) / (r["latency_ms"] / 1000)
    p = chat(model, intent_messages(SAMPLE.model_dump(), "make the gaps bigger"), max_tokens=1)
    pre = p["usage"].get("prompt_tokens", 0) / (p["latency_ms"] / 1000)
    return {"decode_tok_s": round(dec, 1), "prefill_tok_s": round(pre), "prompt_tokens": p["usage"].get("prompt_tokens")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="9B,4B")
    args = ap.parse_args()
    base = Path(config.CODE_MODEL).parent
    out = {}
    for size in args.models.split(","):
        model = str(base / f"Ternary-Bonsai-2-{size}-mlx-2bit")
        sp = speed(model)
        print(f"\n## {size}: decode {sp['decode_tok_s']} tok/s, prefill {sp['prefill_tok_s']} tok/s ({sp['prompt_tokens']} prompt tokens)")
        print("| command | ok | intent check | model calls | latency s | ops (model intent) |\n|---|---|---|---|---|---|")
        rows = []
        for cmd, check in CASES:
            r = run_command(SAMPLE, cmd, model)
            calls = len(r["log"])
            intents = [o for e in r["log"] for o in (e.get("intent") or [])][-6:]
            passed = None if (check is None or not r["ok"]) else bool(check(SAMPLE, r["level"]))
            row = {"command": cmd, "ok": r["ok"], "check": passed, "calls": calls, "latency_s": round(r["total_ms"] / 1000, 1),
                   "message": r["message"], "intent": intents, "errors": [e["errors"] for e in r["log"]], "repairs": [e["repairs"] for e in r["log"]]}
            rows.append(row)
            short = "; ".join(f"{o['op']}({','.join(str(v) for k, v in o.items() if k != 'op')})" for o in intents)
            print(f"| {cmd} | {'✅' if r['ok'] else '❌'} | {'—' if passed is None else ('✅' if passed else '❌')} | {calls} | {row["latency_s"]} | {short[:110]} |")
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
