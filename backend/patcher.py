"""Apply level edits with deterministic auto-fixes and clear errors.

Editor mutates a working copy of a level. The patch returned to the frontend is computed by diff()
between the base level and the result, so it is always exactly the concrete LowLevelOps that were
applied (add_entity, remove_entity, update_entity, set_physics, set_ability, set_player_look, set_scene,
set_reactions; see plan.md).
"""
import copy
import json
import re

from pydantic import ValidationError

from .schema import Level, LowLevelPatch

ENTITY_FIELDS = ("x", "y", "w", "h", "type", "behaviors")


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
        raise PatchError("No JSON object found in the reply. Reply with only the JSON object.")
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
                    raise PatchError(f"Reply is not valid JSON ({e}). Reply with only the JSON object.")
    raise PatchError("Reply JSON object is not closed (output may have been cut off). Use fewer ops.")


def fmt_validation(e: ValidationError) -> str:
    out = []
    for err in e.errors():
        msg = err["msg"].removeprefix("Value error, ")
        loc = ".".join(str(p) for p in err["loc"])
        out.append(f"- {loc}: {msg}" if loc else f"- {msg}")
    return "\n".join(out)


def _rect_overlap(a: dict, b: dict) -> bool:
    return a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"] and a["y"] < b["y"] + b["h"] and b["y"] < a["y"] + a["h"]


class Editor:
    """Working copy of a level. player = {"x", "y", "has_double_jump"} in tiles, or None."""

    def __init__(self, level: Level, player: dict | None = None):
        self.base = level.model_dump()
        self.d = copy.deepcopy(self.base)
        self.player = player
        self.repairs: list[str] = []   # deterministic fixes we made
        self.errors: list[str] = []    # problems we could not fix (each says how to fix it)
        self.done: list[str] = []      # short past-tense notes for the spoken reply ("added 3 enemies")
        self.added: set[str] = set()   # ids added during this edit

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
            self.errors.append(f"{where}: there is no object '{eid}'. Use one of these ids: {self.ids_by_type()}")
            return None
        if type_ and e["type"] != type_:
            ok = ", ".join(x["id"] for x in self.ents if x["type"] == type_)
            self.errors.append(f"{where}: '{eid}' is a {e['type']}, not a {type_}. Use one of: {ok}")
            return None
        return e

    def new_id(self, prefix: str) -> str:
        taken = {e["id"] for e in self.ents}
        n = 1
        while f"{prefix}{n}" in taken:
            n += 1
        return f"{prefix}{n}"

    def player_cells(self) -> set[tuple[int, int]]:
        """Tiles the player occupies (plus one tile of margin left/right); empty if not playing."""
        p = self.player
        if not p:
            return set()
        return {(p["x"] + dx, p["y"] + dy) for dx in (-1, 0, 1) for dy in (-1, 0)}

    # ----- primitive edits -----
    def add(self, ent: dict) -> dict:
        ent = {"w": 1, "h": 1, "behaviors": [], "props": {}, **ent}
        if self.get(ent["id"]):
            old, prefix = ent["id"], re.sub(r"\d+$", "", ent["id"]) or ent["type"]
            ent["id"] = self.new_id(prefix)
            self.repairs.append(f"renamed new object '{old}' to '{ent['id']}' (id already used)")
        self.ents.append(ent)
        self.added.add(ent["id"])
        return ent

    def remove(self, eid: str):
        e = self.get(eid)
        if e:
            self.ents.remove(e)

    def move(self, e: dict, x: int, y: int):
        e["x"], e["y"] = x, y

    def set(self, e: dict, key: str, value):
        if key.startswith("props."):
            e["props"][key[6:]] = value
        else:
            e[key] = value

    def set_physics(self, key: str, value: float):
        self.d["physics"][key] = value

    def set_ability(self, ability: str, settings: dict):
        self.d.setdefault("abilities", {})[ability] = settings

    # ----- deterministic fixes -----
    def autofix(self):
        W, H = self.d["width"], self.d["height"]
        # 1. bring everything inside the level. Platforms that run off the right/bottom edge are
        #    shrunk (moving ground left would close a gap); other objects are shifted.
        for e in self.ents:
            before = (e["x"], e["y"], e["w"], e["h"])
            e["x"], e["y"] = max(e["x"], 0), max(e["y"], 0)
            if e["type"] == "platform":
                if e["x"] >= W:
                    e["x"] = W - 1
                if e["y"] >= H:
                    e["y"] = H - 1
                e["w"], e["h"] = max(1, min(e["w"], W - e["x"])), max(1, min(e["h"], H - e["y"]))
            else:
                e["w"], e["h"] = min(e["w"], W), min(e["h"], H)
                e["x"], e["y"] = min(e["x"], W - e["w"]), min(e["y"], H - e["h"])
            after = (e["x"], e["y"], e["w"], e["h"])
            if after != before:
                what = "shrunk" if e["type"] == "platform" and after[2:] != before[2:] else "moved"
                self.repairs.append(f"{what} {e['id']} to fit inside the level: (x,y,w,h) {before} -> {after}")
        plats = [p for p in self.ents if p["type"] == "platform"]
        # 2. lava in pits: trim to the open span (it must not sit inside ground)
        for e in [e for e in self.ents if e["type"] == "lava"]:
            hits = [p for p in plats if _rect_overlap(e, p)]
            if not hits:
                continue
            free = [x for x in range(e["x"], e["x"] + e["w"]) if not any(_rect_overlap({**e, "x": x, "w": 1}, p) for p in hits)]
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
            e["x"], e["w"] = lo, hi - lo + 1
        # 3. nudge objects out of solid platforms (move them up to stand on top)
        for e in self.ents:
            if e["type"] in ("platform", "lava"):
                continue
            for p in plats:
                if _rect_overlap(e, p) and p["y"] - e["h"] >= 0:
                    self.repairs.append(f"moved {e['id']} up out of {p['id']} (y {e['y']} -> {p['y'] - e['h']})")
                    e["y"] = p["y"] - e["h"]
                    break
        # 4. new objects never land on the player: shift them right (or left at the level edge)
        cells = self.player_cells()
        if cells:
            for e in self.ents:
                if e["id"] not in self.added:
                    continue
                def hits(x):
                    return any((cx, cy) in cells for cx in range(x, x + e["w"]) for cy in range(e["y"], e["y"] + e["h"]))
                if hits(e["x"]):
                    for x in [*range(e["x"] + 1, W - e["w"] + 1), *range(e["x"] - 1, -1, -1)]:
                        if not hits(x):
                            self.repairs.append(f"moved new {e['id']} off the player (x {e['x']} -> {x})")
                            e["x"] = x
                            break
        # 5. spawn: inside the level and not inside a platform
        s = self.d["spawn"]
        sx, sy = min(max(s["x"], 0), W - 1), min(max(s["y"], 0), H - 1)
        for p in plats:
            if p["x"] <= sx < p["x"] + p["w"] and p["y"] <= sy < p["y"] + p["h"]:
                sy = max(0, p["y"] - 1)
        if (sx, sy) != (s["x"], s["y"]):
            self.repairs.append(f"moved player start ({s['x']},{s['y']}) -> ({sx},{sy})")
            s["x"], s["y"] = sx, sy

    def result(self) -> Level:
        try:
            return Level.model_validate(self.d)
        except ValidationError as e:
            raise PatchError("The edited level is invalid:\n" + fmt_validation(e))

    def diff(self) -> list[dict]:
        return diff_levels(self.base, self.d)


def diff_levels(old: dict, new: dict) -> list[dict]:
    """Concrete LowLevelOps that turn `old` into `new` (removes, updates, adds, physics, abilities)."""
    ops: list[dict] = []
    o = {e["id"]: e for e in old["entities"]}
    n = {e["id"]: e for e in new["entities"]}
    for eid in o:
        if eid not in n:
            ops.append({"op": "remove_entity", "id": eid})
    for eid, ne in n.items():
        oe = o.get(eid)
        if oe is None:
            continue
        if oe["type"] != ne["type"]:  # type changes are not live-updatable: replace the entity
            ops += [{"op": "remove_entity", "id": eid}, {"op": "add_entity", "entity": copy.deepcopy(ne)}]
            continue
        ch = {k: ne[k] for k in ENTITY_FIELDS if k != "type" and ne.get(k) != oe.get(k)}
        props = {k: v for k, v in ne.get("props", {}).items() if oe.get("props", {}).get(k) != v}
        if props:
            ch["props"] = props
        for k in ne:  # optional fields added by other tasks (e.g. sprite, tint)
            if k not in ENTITY_FIELDS and k not in ("id", "props") and ne.get(k) != oe.get(k):
                ch[k] = ne[k]
        if ch:
            ops.append({"op": "update_entity", "id": eid, "changes": ch})
    for eid, ne in n.items():
        if eid not in o:
            ops.append({"op": "add_entity", "entity": copy.deepcopy(ne)})
    for k, v in new["physics"].items():
        if old["physics"].get(k) != v:
            ops.append({"op": "set_physics", "key": k, "value": v})
    for k, v in new.get("abilities", {}).items():
        if old.get("abilities", {}).get(k) != v:
            ops.append({"op": "set_ability", "ability": k, "settings": copy.deepcopy(v)})
    for field, op, key in (("player_look", "set_player_look", "look"), ("scene", "set_scene", "scene"),
                           ("reactions", "set_reactions", "reactions")):
        if old.get(field) != new.get(field):
            ops.append({"op": op, key: copy.deepcopy(new.get(field))})
    return ops


def apply_low_level(level: Level, ops: list[dict], player: dict | None = None) -> Editor:
    """Apply concrete LowLevelOps (stub mode, debugging), then auto-fix. Check ed.errors / ed.result()."""
    try:
        parsed = LowLevelPatch.model_validate({"ops": ops}).ops
    except ValidationError as e:
        raise PatchError("Invalid ops:\n" + fmt_validation(e))
    ed = Editor(level, player)
    for n, op in enumerate(parsed):
        where = f"op {n + 1} ({op.op})"
        if op.op == "add_entity":
            ed.add(op.entity.model_dump())
        elif op.op == "set_physics":
            ed.set_physics(op.key, op.value)
        elif op.op == "set_ability":
            ed.set_ability(op.ability, op.settings)
        elif op.op == "set_player_look":
            ed.d["player_look"] = op.look.model_dump()
        elif op.op == "set_scene":
            ed.d["scene"] = op.scene.model_dump()
        elif op.op == "set_reactions":
            ed.d["reactions"] = [r.model_dump() for r in op.reactions]
        else:
            e = ed.require(op.id, where)
            if e is None:
                continue
            if op.op == "remove_entity":
                ed.remove(op.id)
            else:
                for k, v in op.changes.items():
                    if k == "props" and isinstance(v, dict):
                        e["props"].update(v)
                    elif k in ("id",):
                        ed.errors.append(f"{where}: ids can't be changed; remove the entity and add a new one")
                    else:
                        e[k] = v
    ed.autofix()
    return ed
