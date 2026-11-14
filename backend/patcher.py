"""Parse, validate, and apply level patches."""
import copy
import json
import re

from pydantic import ValidationError

from .schema import Level, Patch

SETTABLE = {"x", "y", "w", "h", "type", "behaviors"}


class PatchError(Exception):
    """Human/model-readable reason a patch was rejected."""


def extract_json(text: str) -> dict:
    """Pull the first JSON object out of model text (handles ```json fences, stray prose, <think> blocks)."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S)
    if m:
        text = m.group(1)
    start = text.find("{")
    if start < 0:
        raise PatchError("No JSON object found in the reply.")
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            esc = (ch == "\\") and not esc
            if ch == '"' and not esc:
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError as e:
                    raise PatchError(f"Reply is not valid JSON: {e}")
    raise PatchError("Reply JSON object is not closed (output may have been cut off).")


def _fmt(e: ValidationError) -> str:
    return "\n".join(f"- {'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors())


def parse_patch(obj: dict) -> Patch:
    try:
        return Patch.model_validate(obj)
    except ValidationError as e:
        raise PatchError("Patch format is invalid:\n" + _fmt(e))


def apply_patch(level: Level, patch: Patch) -> Level:
    data = copy.deepcopy(level.model_dump())
    ents = data["entities"]
    by_id = lambda i: next((e for e in ents if e["id"] == i), None)  # noqa: E731
    problems = []
    for n, op in enumerate(patch.ops):
        where = f"op {n} ({op.op})"
        if op.op == "add":
            if by_id(op.entity.id):
                problems.append(f"{where}: id '{op.entity.id}' already exists; use a new id")
                continue
            ents.append(op.entity.model_dump())
            continue
        if op.op == "set_physics":
            data["physics"][op.key] = op.value
            continue
        ent = by_id(op.id)
        if ent is None:
            problems.append(f"{where}: no entity with id '{op.id}'")
            continue
        if op.op == "remove":
            ents.remove(ent)
        elif op.op == "move":
            ent["x"], ent["y"] = op.x, op.y
        elif op.op == "set":
            if op.key.startswith("props."):
                ent["props"][op.key[6:]] = op.value
            elif op.key in SETTABLE:
                ent[op.key] = op.value
            else:
                problems.append(f"{where}: can't set '{op.key}'; allowed: {sorted(SETTABLE)} or props.<name>")
    if problems:
        raise PatchError("Patch could not be applied:\n" + "\n".join(f"- {p}" for p in problems))
    try:
        return Level.model_validate(data)
    except ValidationError as e:
        raise PatchError("Patched level is invalid:\n" + _fmt(e))
