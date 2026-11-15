"""Command traces: one JSON snapshot per /api/command, for finding and fixing failure points in the harness.

Each trace holds everything needed to reproduce a command offline: the text, the player state, the level before,
the exact prompt and schema sent to the model, every attempt's raw reply, parsed intents, compile errors and
repairs, the resulting patch and the final outcome. Players can flag a trace from the game ("that was wrong").

Files live in backend/data/traces/ (gitignored). CLI:
    python -m backend.traces                     # recent traces (F = flagged)
    python -m backend.traces --failures          # only error/refused/flagged
    python -m backend.traces show <id> [--prompt]
    python -m backend.traces replay <id> [--model PATH]   # rerun the same command against the model now
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

TRACE_DIR = Path(__file__).resolve().parent / "data" / "traces"
_ID_RE = re.compile(r"^[0-9]{8}-[0-9]{6}-[0-9]{3}-[a-z0-9-]{0,40}$")


def new_trace(text: str, source: str, player: dict | None, stage: str, version: int, level: dict) -> dict:
    t = time.time()
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40].strip("-")
    tid = time.strftime("%Y%m%d-%H%M%S", time.localtime(t)) + f"-{int(t * 1000) % 1000:03d}-{slug}"
    return {"id": tid, "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t)),
            "input": {"text": text, "source": source, "player": player},
            "stage": stage, "version_before": version, "level_before": level,
            "prompt": None, "schema": None, "attempts": [], "outcome": None, "flag": None}


def save(trace: dict) -> None:
    """Never raises: tracing must not break a command."""
    try:
        TRACE_DIR.mkdir(parents=True, exist_ok=True)
        (TRACE_DIR / f"{trace['id']}.json").write_text(json.dumps(trace, indent=1, default=str))
        _prune()
    except OSError:
        pass


# Keep only the newest traces so they can't fill the disk (each holds the full prompt, about 10-20 KB).
MAX_TRACES = int(os.environ.get("TRACE_KEEP", "300"))


def _prune() -> None:
    files = sorted(TRACE_DIR.glob("*.json"))  # ids start with a timestamp, so name order = time order
    for p in files[:-MAX_TRACES] if len(files) > MAX_TRACES else []:
        p.unlink(missing_ok=True)


def path_for(tid: str) -> Path | None:
    if not _ID_RE.match(tid):
        return None
    p = TRACE_DIR / f"{tid}.json"
    return p if p.exists() else None


def load(tid: str) -> dict | None:
    p = path_for(tid)
    return json.loads(p.read_text()) if p else None


def flag(tid: str, note: str) -> dict | None:
    t = load(tid)
    if t is None:
        return None
    t["flag"] = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "note": note}
    save(t)
    return t


def summary(t: dict) -> dict:
    o = t.get("outcome") or {}
    return {"id": t["id"], "time": t["time"], "text": t["input"]["text"], "source": t["input"]["source"],
            "stage": t.get("stage"), "status": o.get("status"), "spoken": o.get("spoken"), "reason": o.get("reason"),
            "attempts": len(t.get("attempts", [])), "latency_ms": o.get("latency_ms"), "flag": t.get("flag")}


def recent(limit: int = 50, failures_only: bool = False) -> list[dict]:
    if not TRACE_DIR.exists():
        return []
    out = []
    for p in sorted(TRACE_DIR.glob("*.json"), reverse=True):
        try:
            s = summary(json.loads(p.read_text()))
        except (OSError, ValueError, KeyError):
            continue
        if failures_only and s["status"] == "applied" and not s["flag"]:
            continue
        out.append(s)
        if len(out) >= limit:
            break
    return out


# ---------- CLI ----------
def _print_list(rows: list[dict]) -> None:
    for s in reversed(rows):
        f = "F" if s["flag"] else " "
        print(f"{f} {s['id']:<62} {s['status'] or '?':<8} {s['attempts']}x {(s['latency_ms'] or 0) / 1000:5.1f}s  "
              f"{s['text']!r}")
        if s["flag"] and s["flag"].get("note"):
            print(f"    flagged: {s['flag']['note']}")
        if s["status"] != "applied" and s["reason"]:
            print(f"    reason: {s['reason'][:200]}")


def _show(t: dict, prompt: bool) -> None:
    print(json.dumps(summary(t), indent=1))
    print("player:", t["input"]["player"])
    if prompt:
        for m in t.get("prompt") or []:
            print(f"\n----- {m['role']} -----\n{m['content']}")
    for i, a in enumerate(t.get("attempts", []), 1):
        print(f"\n===== attempt {i} ({a.get('model')}, {a.get('latency_ms')} ms, usage {a.get('usage')}) =====")
        if a.get("retry_prompt"):
            print("retry prompt:", a["retry_prompt"])
        print("raw:", a.get("raw"))
        for k in ("llm_error", "errors", "repairs", "done", "unsupported", "patch"):
            if a.get(k):
                print(f"{k}:", json.dumps(a[k], indent=1) if k == "patch" else a[k])
    o = t.get("outcome") or {}
    print(f"\n===== outcome: {o.get('status')} =====\nspoken: {o.get('spoken')}\nreason: {o.get('reason')}")


def _replay(t: dict, model: str | None) -> None:
    from . import config
    from .pipeline import run_command
    from .schema import Level
    r = run_command(Level.model_validate(t["level_before"]), t["input"]["text"], model or config.CODE_MODEL,
                    t["input"]["player"])
    was = (t.get("outcome") or {}).get("status")
    print(f"was: {was}  now: {r['status']}  ({r['latency_ms']} ms)\nspoken: {r['spoken']}\nreason: {r['reason']}")
    print("patch:", json.dumps(r["patch"], indent=1))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m backend.traces")
    ap.add_argument("cmd", nargs="?", default="list", choices=["list", "show", "replay"])
    ap.add_argument("id", nargs="?")
    ap.add_argument("--failures", action="store_true", help="only error/refused/flagged")
    ap.add_argument("-n", type=int, default=30)
    ap.add_argument("--prompt", action="store_true", help="show: print the full prompt")
    ap.add_argument("--model", help="replay: model id (default CODE_MODEL)")
    a = ap.parse_args(argv)
    if a.cmd == "list":
        _print_list(recent(a.n, a.failures))
        return
    if not a.id:
        sys.exit("give a trace id (or a unique prefix/substring of one)")
    tid = a.id
    if not path_for(tid):
        hits = [p.stem for p in TRACE_DIR.glob("*.json") if tid in p.stem] if TRACE_DIR.exists() else []
        if len(hits) != 1:
            sys.exit(f"{len(hits)} traces match {tid!r}" + (": " + ", ".join(hits[:10]) if hits else ""))
        tid = hits[0]
    t = load(tid)
    _show(t, a.prompt) if a.cmd == "show" else _replay(t, a.model)


if __name__ == "__main__":
    main()
