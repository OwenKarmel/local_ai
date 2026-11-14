"""High-level ("intent") ops the model emits. The backend turns them into coordinates.

The model refers only to ids/regions from summary.summary_text(); intent_schema() restricts
those fields to ids that actually exist, so the model can't invent one.
"""
import copy
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, ValidationError

from .patcher import Editor, PatchError, fmt_validation
from .schema import Level, Scalar
from .summary import REGIONS, analyze, overlaps_x, support_of

MIN_GROUND = 3  # a ground platform never shrinks below this many tiles
PHYSICS_LIMITS = {"gravity": (300, 3000), "jump_velocity": (200, 1200), "run_speed": (80, 500)}


class WidenGap(BaseModel):
    op: Literal["widen_gap"]
    gap_id: str
    tiles: int = Field(ge=-6, le=6, description="positive = wider, negative = narrower")


class ShrinkPlatform(BaseModel):
    op: Literal["shrink_platform"]
    id: str
    tiles: int = Field(ge=-8, le=8, description="positive = narrower, negative = wider")
    side: Literal["left", "right", "both"] = "both"


class AddEnemy(BaseModel):
    op: Literal["add_enemy"]
    region: str
    count: int = Field(1, ge=1, le=5)
    speed: int = Field(60, ge=30, le=200)


class AddHazardNear(BaseModel):
    op: Literal["add_hazard_near"]
    platform_id: str
    kind: Literal["spikes", "lava"] = "spikes"
    width: int = Field(1, ge=1, le=3)
    side: Literal["left", "right", "auto"] = "auto"


class AddCoins(BaseModel):
    op: Literal["add_coins"]
    region: str
    count: int = Field(3, ge=1, le=8)


class Remove(BaseModel):
    op: Literal["remove"]
    id: str


class SetProperty(BaseModel):
    op: Literal["set_property"]
    id: str
    key: str = Field(description="speed, range, or behaviors")
    value: Union[Scalar, list[str]]


class SetPhysics(BaseModel):
    op: Literal["set_physics"]
    key: Literal["gravity", "jump_velocity", "run_speed"]
    value: float


IntentOp = Annotated[Union[WidenGap, ShrinkPlatform, AddEnemy, AddHazardNear, AddCoins, Remove, SetProperty, SetPhysics],
                     Field(discriminator="op")]


class IntentPatch(BaseModel):
    explanation: str = ""
    ops: list[IntentOp]


# ---------- schema restricted to this level's ids ----------
def intent_schema(level: dict) -> dict:
    s = copy.deepcopy(IntentPatch.model_json_schema())
    a = analyze(level)
    all_ids = [e["id"] for e in level["entities"]]
    plat_ids = [p["id"] for p in a["ground"] + a["floating"]]
    gap_ids = [g["id"] for g in a["gaps"]] or ["none"]
    d = s["$defs"]
    d["WidenGap"]["properties"]["gap_id"]["enum"] = gap_ids
    d["ShrinkPlatform"]["properties"]["id"]["enum"] = plat_ids
    d["AddHazardNear"]["properties"]["platform_id"]["enum"] = plat_ids
    for k in ("AddEnemy", "AddCoins"):
        d[k]["properties"]["region"]["enum"] = list(REGIONS) + plat_ids
    for k in ("Remove", "SetProperty"):
        d[k]["properties"]["id"]["enum"] = all_ids
    return s


def parse_intent(obj: dict) -> IntentPatch:
    try:
        return IntentPatch.model_validate(obj)
    except ValidationError as e:
        raise PatchError("Patch format is invalid:\n" + fmt_validation(e))


# ---------- compiling intents to coordinates ----------
def _riders(ed: Editor, p: dict) -> list[dict]:
    """Objects standing on platform p (plus coins floating just above it)."""
    out = []
    for e in ed.ents:
        if e is p or e["type"] == "platform":
            continue
        if support_of(e, ed.ents) is p or (e["type"] == "coin" and e["y"] < p["y"] and overlaps_x(p, e["x"], e["x"] + 1)
                                            and p["y"] - e["y"] <= 2):
            out.append(e)
    return out


def _reseat(ed: Editor, p: dict, riders: list[dict], spawn_on: bool):
    """After p changed size/position, keep its riders on it."""
    lo, hi = p["x"], p["x"] + p["w"]
    for e in riders:
        nx = min(max(e["x"], lo), max(lo, hi - e["w"]))
        if nx != e["x"]:
            ed.repairs.append(f"kept {e['id']} on {p['id']} (x {e['x']}→{nx})")
            ed.move(e, nx, e["y"])
    if spawn_on:
        s = ed.d["spawn"]
        nx = min(max(s["x"], lo), hi - 1)
        if nx != s["x"]:
            ed.repairs.append(f"kept player start on {p['id']} (x {s['x']}→{nx})")
            s["x"] = nx


def _on(spawn: dict, p: dict) -> bool:
    return p["x"] <= spawn["x"] < p["x"] + p["w"] and spawn["y"] + 1 == p["y"]


def _resize(ed: Editor, p: dict, new_x: int, new_w: int):
    riders, spawn_on = _riders(ed, p), _on(ed.d["spawn"], p)
    if new_w != p["w"]:
        ed.set(p, "w", new_w)
    ed.move(p, new_x, p["y"])
    _reseat(ed, p, riders, spawn_on)


def widen_gap(ed: Editor, op: WidenGap, where: str):
    a = analyze(ed.d)
    gap = next((g for g in a["gaps"] if g["id"] == op.gap_id), None)
    if gap is None:
        ed.errors.append(f"{where}: no gap '{op.gap_id}'. Gaps: {', '.join(g['id'] for g in a['gaps']) or 'none'}")
        return
    L, R = ed.get(gap["left"]), ed.get(gap["right"])
    t = op.tiles
    if t > 0:
        left_to_do = t
        for p in sorted([R, L], key=lambda p: -p["w"]):  # take from the wider side first
            k = min(left_to_do, p["w"] - MIN_GROUND)
            if k <= 0:
                continue
            if p is R:
                _resize(ed, R, R["x"] + k, R["w"] - k)
            else:
                _resize(ed, L, L["x"], L["w"] - k)
            left_to_do -= k
        if left_to_do:
            ed.repairs.append(f"{op.gap_id} widened by {t - left_to_do} instead of {t} (neighbouring ground would get too small)")
    elif t < 0:
        n = min(-t, gap["w"])
        if n < -t:
            ed.repairs.append(f"{op.gap_id} is only {gap['w']} wide; closed it instead of narrowing by {-t}")
        _resize(ed, R, R["x"] - n, R["w"] + n)
    # lava in the pit follows the gap
    new_x, new_w = L["x"] + L["w"], R["x"] - (L["x"] + L["w"])
    for lid in gap["lava"]:
        lv = ed.get(lid)
        if new_w <= 0:
            ed.remove(lid)
        elif lv:
            ed.set(lv, "w", new_w)
            ed.move(lv, new_x, lv["y"])


def shrink_platform(ed: Editor, op: ShrinkPlatform, where: str):
    p = ed.require(op.id, where, "platform")
    if p is None or op.tiles == 0:
        return
    W = ed.d["width"]
    if op.tiles > 0:
        floor = MIN_GROUND if p["y"] + p["h"] >= ed.d["height"] else 1
        t = min(op.tiles, p["w"] - floor)
        if t < op.tiles:
            ed.repairs.append(f"{p['id']} shrunk by {max(t, 0)} instead of {op.tiles} (minimum width {floor})")
        if t <= 0:
            return
        l = {"left": t, "right": 0, "both": t // 2}[op.side]
        _resize(ed, p, p["x"] + l, p["w"] - t)
    else:
        g = -op.tiles
        solids = [q for q in ed.ents if q["type"] == "platform" and q is not p and q["y"] < p["y"] + p["h"] and p["y"] < q["y"] + q["h"]]
        room_l = p["x"] - max([q["x"] + q["w"] for q in solids if q["x"] + q["w"] <= p["x"]] + [0])
        room_r = min([q["x"] for q in solids if q["x"] >= p["x"] + p["w"]] + [W]) - (p["x"] + p["w"])
        want_l = {"left": g, "right": 0, "both": g // 2}[op.side]
        want_r = g - want_l
        gl, gr = min(want_l, room_l), min(want_r, room_r)
        if gl + gr < g:
            ed.repairs.append(f"{p['id']} grew by {gl + gr} instead of {g} (hit a neighbour or the level edge)")
        _resize(ed, p, p["x"] - gl, p["w"] + gl + gr)


def _blocked_cols(ed: Editor, y: int) -> set[int]:
    """Columns at row y already taken by something you can't stack an enemy/hazard on."""
    cols = set()
    for e in ed.ents:
        if e["type"] in ("platform", "coin"):
            continue
        if e["y"] <= y < e["y"] + e["h"]:
            pad = 1 if e["type"] == "goal" else 0  # keep the goal approachable
            cols.update(range(e["x"] - pad, e["x"] + e["w"] + pad))
    s = ed.d["spawn"]
    if s["y"] == y:
        cols.update({s["x"] - 1, s["x"], s["x"] + 1})
    return cols


def _region_platforms(ed: Editor, region: str, where: str) -> tuple[list[dict], tuple[int, int]] | None:
    a = analyze(ed.d)
    if region in a["regions"]:
        lo, hi = a["regions"][region]
        return [p for p in a["ground"] + a["floating"] if overlaps_x(p, lo, hi)], (lo, hi)
    p = ed.get(region)
    if p and p["type"] == "platform":
        return [p], (p["x"], p["x"] + p["w"])
    ed.errors.append(f"{where}: region must be start, middle, end, or a platform id; got '{region}'")
    return None


def _spots(ed: Editor, plats: list[dict], lo: int, hi: int, min_w: int = 1) -> list[tuple[int, dict]]:
    out = []
    for p in plats:
        if p["w"] < min_w:
            continue
        y = p["y"] - 1
        if y < 0:
            continue
        blocked = _blocked_cols(ed, y)
        out += [(x, p) for x in range(max(p["x"], lo), min(p["x"] + p["w"], hi)) if x not in blocked]
    return sorted(out, key=lambda s: s[0])


def _spread(spots: list, n: int) -> list:
    if n >= len(spots):
        return spots
    if n == 1:
        return [spots[len(spots) // 2]]
    return [spots[round(i * (len(spots) - 1) / (n - 1))] for i in range(n)]


def add_enemy(ed: Editor, op: AddEnemy, where: str):
    r = _region_platforms(ed, op.region, where)
    if r is None:
        return
    plats, (lo, hi) = r
    chosen = []
    for x, p in _spread(_spots(ed, plats, lo, hi, min_w=2), op.count):  # evenly spread across the region
        if any(abs(x - c) < 2 for c in chosen):
            continue
        rng = max(1, min(3, x - p["x"], p["x"] + p["w"] - 1 - x))
        ed.add({"id": ed.new_id("enemy"), "type": "enemy", "x": x, "y": p["y"] - 1,
                "behaviors": ["patrol"], "props": {"speed": op.speed, "range": rng}})
        chosen.append(x)
    if len(chosen) < op.count:
        ed.repairs.append(f"only room for {len(chosen)} of {op.count} enemies in {op.region}")
    if not chosen:
        ed.errors.append(f"{where}: no free ground in {op.region} to place an enemy")


def add_hazard_near(ed: Editor, op: AddHazardNear, where: str):
    p = ed.require(op.platform_id, where, "platform")
    if p is None:
        return
    if p["w"] < 3:
        ed.errors.append(f"{where}: {p['id']} is only {p['w']} wide; too small for a hazard. Pick a platform at least 3 wide")
        return
    width = min(op.width, p["w"] - 2)
    a = analyze(ed.d)
    sides = [op.side] if op.side != "auto" else (["left", "right"] if any(g["right"] == p["id"] for g in a["gaps"]) or p in a["floating"] else ["right", "left"])
    y = p["y"] - 1
    blocked = _blocked_cols(ed, y)
    for side in sides + [s for s in ("left", "right") if s not in sides]:
        x = p["x"] + 1 if side == "left" else p["x"] + p["w"] - 1 - width
        if not any(c in blocked for c in range(x, x + width)):
            ed.add({"id": ed.new_id(op.kind), "type": op.kind, "x": x, "y": y, "w": width, "h": 1})
            return
    ed.errors.append(f"{where}: no free spot on {p['id']} (start, goal or other objects are in the way); pick another platform")


def add_coins(ed: Editor, op: AddCoins, where: str):
    r = _region_platforms(ed, op.region, where)
    if r is None:
        return
    plats, (lo, hi) = r
    coin_cells = {(e["x"], e["y"]) for e in ed.ents if e["type"] == "coin"}
    spots = [(x, p) for x, p in _spots(ed, plats, lo, hi) if (x, p["y"] - 1) not in coin_cells]
    picked = _spread(spots, op.count)
    for x, p in picked:
        ed.add({"id": ed.new_id("coin"), "type": "coin", "x": x, "y": p["y"] - 1})
    if len(picked) < op.count:
        ed.repairs.append(f"only room for {len(picked)} of {op.count} coins in {op.region}")


def compile_intent(level: Level, intent: IntentPatch) -> Editor:
    """Apply intent ops to a copy of level. Inspect ed.errors (unfixable), ed.repairs, ed.ops; call ed.result()."""
    ed = Editor(level)
    for n, op in enumerate(intent.ops):
        where = f"op {n + 1} ({op.op})"
        if op.op == "widen_gap":
            widen_gap(ed, op, where)
        elif op.op == "shrink_platform":
            shrink_platform(ed, op, where)
        elif op.op == "add_enemy":
            add_enemy(ed, op, where)
        elif op.op == "add_hazard_near":
            add_hazard_near(ed, op, where)
        elif op.op == "add_coins":
            add_coins(ed, op, where)
        elif op.op == "remove":
            e = ed.require(op.id, where)
            if e is not None:
                if e["type"] == "goal" and sum(x["type"] == "goal" for x in ed.ents) == 1:
                    ed.errors.append(f"{where}: can't remove the only goal")
                elif e["type"] == "platform" and _on(ed.d["spawn"], e):
                    ed.errors.append(f"{where}: can't remove {e['id']}, the player starts on it")
                else:
                    ed.remove(op.id)
        elif op.op == "set_property":
            e = ed.require(op.id, where)
            if e is None:
                continue
            if op.key == "behaviors":
                ed.set(e, "behaviors", op.value if isinstance(op.value, list) else [str(op.value)])
            elif op.key in ("x", "y", "w", "h", "type", "id"):
                ed.errors.append(f"{where}: can't set '{op.key}' directly; use widen_gap / shrink_platform / remove + add ops")
            else:
                ed.set(e, f"props.{op.key.removeprefix('props.')}", op.value)
        elif op.op == "set_physics":
            lo, hi = PHYSICS_LIMITS[op.key]
            v = min(max(op.value, lo), hi)
            if v != op.value:
                ed.repairs.append(f"{op.key} clamped {op.value:g}→{v:g} (allowed {lo}-{hi})")
            ed.set_physics(op.key, v)
    ed.autofix()
    return ed
