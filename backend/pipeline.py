"""Command -> model intent ops -> concrete LowLevelOps -> auto-fix -> validated level.

No global state (the eval script calls it too). Returns the /api/command contract fields except
`version`, which main.py assigns.
"""
import logging
import time

from .intents import compile_intent, intent_schema, parse_intent
from .llm import LLMError, chat, short_name
from .patcher import PatchError, extract_json
from .prompts import intent_messages, retry_message
from .schema import Level

log = logging.getLogger("pipeline")
MAX_MODEL_RETRIES = 1  # deterministic fixes run first; the model gets at most one more try
ROUTE = "level"        # A4 adds the "fast" route; until then every command uses the level prompt


def spoken_from(done: list[str], skipped: int = 0) -> str:
    done = list(dict.fromkeys(done))  # "made enemys faster" x6 -> once
    done = [d.replace("enemys", "enemies") for d in done]
    if not done:
        return "Done."
    parts = done if len(done) <= 3 else done[:2] + [f"{len(done) - 2} more changes"]
    s = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
    s = s[0].upper() + s[1:] + "."
    if skipped:
        s += " I couldn't do the rest."
    return s


def run_command(level: Level, text: str, model: str, player: dict | None = None) -> dict:
    ld = level.model_dump()
    messages = intent_messages(ld, text, player)
    schema = intent_schema(ld, player)
    steps: list[dict] = []
    t0 = time.perf_counter()
    name = short_name(model)

    def out(status, new_level=None, patch=None, spoken="", reason=None):
        return {"ok": status == "applied", "status": status, "route": ROUTE, "model": name,
                "latency_ms": int((time.perf_counter() - t0) * 1000), "patch": patch or [],
                "level": (new_level or level).model_dump(), "spoken": spoken, "reason": reason, "log": steps}

    for attempt in range(1 + MAX_MODEL_RETRIES):
        last = attempt == MAX_MODEL_RETRIES
        try:
            res = chat(model, messages, schema=schema)
        except LLMError as e:
            steps.append({"step": "model", "model": name, "latency_ms": 0, "errors": [str(e)], "repairs": []})
            return out("error", spoken="I can't reach the model right now.", reason=str(e))
        mstep = {"step": "model", "model": res["model"], "latency_ms": res["latency_ms"], "errors": [], "repairs": []}
        steps.append(mstep)
        log.info("attempt %d raw=%s", attempt + 1, res["text"][:600])

        tc = time.perf_counter()
        cstep = {"step": "convert", "model": None, "latency_ms": 0, "errors": [], "repairs": []}
        ed = new_level = None
        try:
            intent = parse_intent(extract_json(res["text"]))
            if not intent.ops:
                raise PatchError("The reply has no ops. Return at least one operation, or one 'unsupported' op explaining what can't be done.")
            ed = compile_intent(level, intent, player)
            cstep["repairs"] = list(ed.repairs)
            new_level = ed.result()
            errors = list(ed.errors)
        except PatchError as e:
            errors = [str(e)]
            intent = None
        cstep["latency_ms"] = int((time.perf_counter() - tc) * 1000)
        cstep["errors"] = errors
        steps.append(cstep)

        unsupported = [o.reason for o in intent.ops if o.op == "unsupported"] if intent else []
        patch = ed.diff() if (ed is not None and new_level is not None) else []

        if patch and not errors:
            spoken = spoken_from(ed.done)
            if unsupported:
                spoken = spoken.rstrip(".") + f", but I can't {unsupported[0].rstrip('.').lower()}."
            steps.append({"step": "check", "model": None, "latency_ms": 0, "errors": [], "repairs": []})
            return out("applied", new_level, patch, spoken)
        if unsupported and not patch and not errors:
            reason = (f"This request can't be expressed with the current edit operations: {unsupported[0]} "
                      "(Refusals for unbeatable levels arrive with the playability checker.)")
            return out("refused", spoken=f"I can't do that yet: {unsupported[0].rstrip('.')}.", reason=reason)
        if not errors and not patch:
            errors = ["The ops changed nothing in the level. Return ops that actually make the requested change."]
            cstep["errors"] = errors
        if not last:
            cstep["repairs"].append("asked the model to fix the errors (1 retry)")
            messages = messages + [{"role": "assistant", "content": res["text"]}, retry_message(errors)]
            continue
        if patch:  # last try: keep the ops that worked, report the rest in the log
            steps.append({"step": "check", "model": None, "latency_ms": 0, "errors": [], "repairs": []})
            return out("applied", new_level, patch, spoken_from(ed.done, skipped=len(errors)))
        return out("error", spoken="Sorry, I couldn't make that change.", reason="; ".join(errors))
    raise AssertionError("unreachable")
