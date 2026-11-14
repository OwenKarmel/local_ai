"""NL command -> model intent ops -> coordinates -> auto-fix -> validated level. No global state (eval uses it too)."""
import time

from .intents import compile_intent, intent_schema, parse_intent
from .llm import LLMError, chat, short_name
from .patcher import PatchError, extract_json
from .prompts import intent_messages, retry_message
from .schema import Level

MAX_MODEL_RETRIES = 1  # deterministic fixes run first; the model gets at most one more try


def run_command(level: Level, text: str, model: str) -> dict:
    """Returns {"ok", "level" (Level|None), "patch" (dict|None), "log": [...], "message", "total_ms"}.

    log entries follow the /api/command contract: {model, latency_ms, errors, repairs} (+ "raw", "intent").
    """
    ld = level.model_dump()
    messages = intent_messages(ld, text)
    schema = intent_schema(ld)
    log: list[dict] = []
    t0 = time.perf_counter()

    def done(ok, message, new_level=None, patch=None):
        return {"ok": ok, "level": new_level, "patch": patch, "log": log, "message": message,
                "total_ms": int((time.perf_counter() - t0) * 1000)}

    for attempt in range(1 + MAX_MODEL_RETRIES):
        last = attempt == MAX_MODEL_RETRIES
        try:
            res = chat(model, messages, schema=schema)
        except LLMError as e:
            log.append({"model": short_name(model), "latency_ms": 0, "errors": [str(e)], "repairs": []})
            return done(False, str(e))
        entry = {"model": res["model"], "latency_ms": res["latency_ms"], "errors": [], "repairs": [], "raw": res["text"]}
        log.append(entry)
        try:
            intent = parse_intent(extract_json(res["text"]))
            entry["intent"] = [o.model_dump() for o in intent.ops]
            if not intent.ops:
                raise PatchError("The reply has no ops. Return at least one operation that does what the command asks.")
            ed = compile_intent(level, intent)
            entry["repairs"] = list(ed.repairs)
            new_level = ed.result()
            errors = list(ed.errors)
        except PatchError as e:
            errors, new_level, ed = [str(e)], None, None
        entry["errors"] = errors

        applied = ed is not None and new_level is not None and bool(ed.ops)
        if applied and not errors:
            return done(True, intent.explanation or "Level updated.", new_level, {"explanation": intent.explanation, "ops": ed.ops})
        if not last:
            entry["repairs"].append("asked the model to fix the errors (1 retry)")
            messages = messages + [{"role": "assistant", "content": res["text"]}, retry_message(errors)]
            continue
        if applied:  # last try: keep the ops that worked, report the ones that didn't
            return done(True, (intent.explanation or "Level updated") + f" (skipped {len(errors)} op(s) that could not be applied)",
                        new_level, {"explanation": intent.explanation, "ops": ed.ops})
        return done(False, "Could not apply the command: " + "; ".join(errors))
    return done(False, "unreachable")
