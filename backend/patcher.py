"""Apply level edits with deterministic auto-fixes and clear errors.

Editor mutates a working copy of a level and records every change as a low-level op, so the
result is always reproducible as a plain Patch (CLAUDE.md format). Used by both:
  - intents.py  (model's high-level ops -> coordinates)
  - apply_low_level()  (drawings / POST /api/patch)
"""
import copy
import json
import re

from pydantic import ValidationError

from .schema import Level, Patch

SETTABLE = {"x", "y", "w", "h", "type", "behaviors"}


class PatchError(Exception):
    """Human/model-readable reason an edit was rejected."""


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
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
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
                    return json.loads(text[start: i + 1])
                except json.JSONDecodeError as e:
                    raise PatchError(f"Reply is not valid JSON: {e}")
    raise PatchError("Reply JSON object is not closed (output may have been cut off).")


def fmt_validation(e: ValidationError) -> str:
    return "\n".join(f"- {'.'.join(str(p) for p in err['loc']) or 'level'}: {err['msg']}" for err in e.errors())


def _rect_overlap(a: dict, b: dict) -> bool:
    return a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"] and a["y"] < b["y"] + b["h"] and b["y"] < a["y"] + a["h"]


class Editor:
    def __init__(self, level: Level):
        self.d = copy.deepcopy(level.model_dump())
        self.ops: list[dict] = []      # low-level ops actually applied, in order
        self.repairs: list[str] = []   # deterministic fixes we made
        self.errors: list[str] = []    # problems we could not fix

    # ----- lookups -----
    @property
    def ents(self) -> list[dict]:
        return self.d["entities"]

    def get(self, eid: str) -> dict | None:
        return next((e for e in self.ents if e["id"] == eid), None)

    def ids_by_type(self) -> str:
        groups: dict[str, list[str]] = {}
        for e in self.ents:
            groups.setdefault(e["type"], []).append(e["id"])
        return "; ".join(f"{t}: {', '.join(ids)}" for t, ids in groups.items())

    def require(self, eid: str, where: str, type_: str | None = None) -> dict | None:
        e = self.get(eid)
        if e is None:
            self.errors.append(f"{where}: there is no object with id '{eid}'. Existing ids — {self.ids_by_type()}")
            return None
        if type_ and e["type"] != type_:
            self.errors.append(f"{where}: '{eid}' is a {e['type']}, not a {type_}")
            return None
        return e

    def new_id(self, prefix: str) -> str:
        taken = {e["id"] for e in self.ents}
        n = 1
        while f"{prefix}{n}" in taken:
            n += 1
        return f"{prefix}{n}"

    # ----- primitive edits (each records a low-level op) -----
    def add(self, ent: dict) -> dict:
        ent = {"w": 1, "h": 1, "behaviors": [], "props": {}, **ent}
        if self.get(ent["id"]):
            old, prefix = ent["id"], re.sub(r"\d+$", "", ent["id"]) or ent["type"]
            ent["id"] = self.new_id(prefix)
            self.repairs.append(f"renamed new object '{old}' to '{ent['id']}' (id already used)")
        self.ents.append(ent)
        self.ops.append({"op": "add", "entity": copy.deepcopy(ent)})
        return ent

    def remove(self, eid: str):
        e = self.get(eid)
        if e:
            self.ents.remove(e)
            self.ops.append({"op": "remove", "id": eid})

    def move(self, e: dict, x: int, y: int):
        if (e["x"], e["y"]) != (x, y):
            e["x"], e["y"] = x, y
            self.ops.append({"op": "move", "id": e["id"], "x": x, "y": y})

    def set(self, e: dict, key: str, value):
        if key.startswith("props."):
            e["props"][key[6:]] = value
        elif e.get(key) == value:
            return
        else:
            e[key] = value
        self.ops.append({"op": "set", "id": e["id"], "key": key, "value": value})

    def set_physics(self, key: str, value: float):
        self.d["physics"][key] = value
        self.ops.append({"op": "set_physics", "key": key, "value": value})

    # ----- deterministic fixes -----
    def autofix(self):
        W, H = self.d["width"], self.d["height"]
        # 1. clamp everything into the level
        for e in self.ents:
            w, h = min(e["w"], W), min(e["h"], H)
            x, y = min(max(e["x"], 0), W - w), min(max(e["y"], 0), H - h)
            if (x, y, w, h) != (e["x"], e["y"], e["w"], e["h"]):
                self.repairs.append(f"clamped {e['id']} into the level: x {e['x']}→{x}, y {e['y']}→{y}, w {e['w']}→{w}, h {e['h']}→{h}")
                if w != e["w"]:
                    self.set(e, "w", w)
                if h != e["h"]:
                    self.set(e, "h", h)
                self.move(e, x, y)
        plats = [p for p in self.ents if p["type"] == "platform"]
        # 2. lava in pits: trim to the free span (it must not sit inside ground)
        for e in [e for e in self.ents if e["type"] == "lava"]:
            hits = [p for p in plats if _rect_overlap(e, p)]
            if not hits:
                continue
            free = [x for x in range(e["x"], e["x"] + e["w"]) if not any(p["x"] <= x < p["x"] + p["w"] and _rect_overlap({**e, "x": x, "w": 1}, p) for p in hits)]
            if not free:
                self.repairs.append(f"removed {e['id']} (it was buried inside a platform)")
                self.remove(e["id"])
                continue
            runs, start = [], free[0]
            for a, b in zip(free, free[1:] + [None]):
                if b != a + 1:
                    runs.append((start, a))
                    start = b
            lo, hi = max(runs, key=lambda r: r[1] - r[0])
            self.repairs.append(f"trimmed {e['id']} to the open pit x {lo}-{hi}")
            self.set(e, "w", hi - lo + 1)
            self.move(e, lo, e["y"])
        # 3. nudge objects out of solid platforms (move them up to stand on top)
        for e in self.ents:
            if e["type"] in ("platform", "lava"):
                continue
            for p in plats:
                if _rect_overlap(e, p) and p["y"] - e["h"] >= 0:
                    self.repairs.append(f"moved {e['id']} up out of {p['id']} (y {e['y']}→{p['y'] - e['h']})")
                    self.move(e, e["x"], p["y"] - e["h"])
                    break
        # 4. spawn: inside the level and not inside a platform
        s = self.d["spawn"]
        sx, sy = min(max(s["x"], 0), W - 1), min(max(s["y"], 0), H - 1)
        for p in plats:
            if p["x"] <= sx < p["x"] + p["w"] and p["y"] <= sy < p["y"] + p["h"]:
                sy = max(0, p["y"] - 1)
        if (sx, sy) != (s["x"], s["y"]):
            self.repairs.append(f"moved player start ({s['x']},{s['y']})→({sx},{sy})")
            s["x"], s["y"] = sx, sy

    def result(self) -> Level:
        try:
            return Level.model_validate(self.d)
        except ValidationError as e:
            raise PatchError("The edited level is invalid:\n" + fmt_validation(e))


def parse_patch(obj: dict) -> Patch:
    try:
        return Patch.model_validate(obj)
    except ValidationError as e:
        raise PatchError("Patch format is invalid:\n" + fmt_validation(e))


def apply_low_level(level: Level, patch: Patch) -> Editor:
    """Apply a coordinate-level patch (drawings, /api/patch), then auto-fix. Check ed.errors / ed.result()."""
    ed = Editor(level)
    for n, op in enumerate(patch.ops):
        where = f"op {n + 1} ({op.op})"
        if op.op == "add":
            ed.add(op.entity.model_dump())
        elif op.op == "set_physics":
            ed.set_physics(op.key, op.value)
        else:
            e = ed.require(op.id, where)
            if e is None:
                continue
            if op.op == "remove":
                ed.remove(op.id)
            elif op.op == "move":
                ed.move(e, op.x, op.y)
            elif op.op == "set":
                if op.key in SETTABLE or op.key.startswith("props."):
                    ed.set(e, op.key, op.value)
                else:
                    ed.errors.append(f"{where}: can't set '{op.key}'; allowed keys: {sorted(SETTABLE)} or props.<name>")
    ed.autofix()
    return ed
