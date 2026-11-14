"""High-level ("intent") ops the model emits. The backend turns them into coordinates.

The model refers only to ids/regions from summary.summary_text(); intent_schema() restricts those
fields to ids that actually exist, so the model can't invent one.
"""
import copy
import re
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field, ValidationError

from .looks import AddReaction, RemoveReaction, SetLook, SetScene, add_reaction, remove_reaction, restrict_schema, set_look, set_scene
from .patcher import Editor, PatchError, _rect_overlap, fmt_validation
from .schema import Level, Scalar
from .summary import FIXED_REGIONS, PLAYER_REGIONS, analyze, overlaps_x, prop_spec, regions, roam_span, support_of

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
    key: str = Field(description="a prop the object's behaviors read (see the summary), or behaviors")
    value: Union[Scalar, list[str]]


class SetPhysics(BaseModel):
    op: Literal["set_physics"]
    key: Literal["gravity", "jump_velocity", "run_speed"]
    value: float


class AddPlatform(BaseModel):
    op: Literal["add_platform"]
    over: str = Field(description="gap id, region, or platform id the new platform floats over")
    height: int = Field(3, ge=1, le=6, description="tiles above the ground")
    width: int = Field(3, ge=1, le=6)


class AddPickup(BaseModel):
    op: Literal["add_pickup"]
    kind: Literal["double_jump", "grow"]
    region: str
    count: int = Field(1, ge=1, le=3)


class Unsupported(BaseModel):
    op: Literal["unsupported"]
    reason: str = Field(description="what part of the command these operations can't express")


IntentOp = Annotated[Union[WidenGap, ShrinkPlatform, AddEnemy, AddHazardNear, AddCoins, AddPlatform, AddPickup, Remove,
                           SetProperty, SetPhysics, SetLook, SetScene, AddReaction, RemoveReaction, Unsupported],
                     Field(discriminator="op")]


class IntentPatch(BaseModel):
    # Written BEFORE ops (intent_schema makes it required and first), so the model decides what the command
    # asks for, and which op does exactly that, before committing to ops. Lenient here: a missing plan is not an error.
    plan: str = ""
    ops: list[IntentOp]
    # Per op: the words of the command it carries out ("asked", written right after "op"; see intent_schema).
    # Kept beside ops (not on each op model) so the op classes stay what compile_intent consumes.
    asked: list[str] = []


PLAN_MAX_CHARS = 200
ASKED_MAX_CHARS = 60
_WORD = re.compile(r"[a-z0-9]+")
PICKUP_ID_PREFIX = {"double_jump": "dj", "grow": "grow"}


# ---------- schema restricted to this level's ids ----------
def intent_schema(level: dict, player: dict | None) -> dict:
    s = copy.deepcopy(IntentPatch.model_json_schema())
    a = analyze(level, player)
    all_ids = [e["id"] for e in level["entities"]]
    plat_ids = [p["id"] for p in a["ground"] + a["floating"]]
    gap_ids = [g["id"] for g in a["gaps"]] or ["none"]
    region_names = list(FIXED_REGIONS) + (list(PLAYER_REGIONS) if player else []) + plat_ids
    # Grammar-constrained decoders emit required properties first, in this order. `plan` was optional, so the
    # model chose ops first and wrote the explanation afterwards as a justification. Required + first = think first.
    s["properties"] = {"plan": {**s["properties"]["plan"], "maxLength": PLAN_MAX_CHARS}, "ops": s["properties"]["ops"]}
    s["required"] = ["plan", "ops"]
    s["properties"]["ops"]["minItems"] = 1  # declining must be an explicit `unsupported` op, not an empty list
    s["properties"]["ops"]["maxItems"] = 6  # long op lists cost seconds of decode time
    d = s["$defs"]
    d["WidenGap"]["properties"]["gap_id"]["enum"] = gap_ids
    d["ShrinkPlatform"]["properties"]["id"]["enum"] = plat_ids
    d["AddHazardNear"]["properties"]["platform_id"]["enum"] = plat_ids
    for k in ("AddEnemy", "AddCoins", "AddPickup"):
        d[k]["properties"]["region"]["enum"] = region_names
    d["AddPlatform"]["properties"]["over"]["enum"] = [g for g in gap_ids if g != "none"] + region_names
    for k in ("Remove", "SetProperty"):
        d[k]["properties"]["id"]["enum"] = all_ids
    restrict_schema(d, all_ids)
    # Every op starts with "asked" (right after "op"): the command's own words that this op carries out. Writing
    # it before the op's fields ties each op to something the player said, so the model stops adding extras
    # ("make me big" -> also a brown tint and faster running). drop_unasked() enforces it.
    for ref in s["properties"]["ops"]["items"]["oneOf"]:
        od = d[ref["$ref"].rsplit("/", 1)[-1]]
        props = dict(od["properties"])
        od["properties"] = {"op": props.pop("op"),
                            "asked": {"type": "string", "maxLength": ASKED_MAX_CHARS,
                                      "description": "the exact words of the command this op carries out"},
                            **props}
        od["required"] = ["op", "asked"] + [r for r in od.get("required", []) if r != "op"]
    return s


def parse_intent(obj: dict) -> IntentPatch:
    asked = []
    if isinstance(obj, dict) and isinstance(obj.get("ops"), list):
        obj = {**obj, "ops": [dict(o) if isinstance(o, dict) else o for o in obj["ops"]]}
        asked = [str(o.pop("asked", "") or "") if isinstance(o, dict) else "" for o in obj["ops"]]
    try:
        intent = IntentPatch.model_validate(obj)
    except ValidationError as e:
        raise PatchError("Patch format is invalid:\n" + fmt_validation(e))
    intent.asked = asked
    return intent


def _from_command(quote: str, command: str) -> bool:
    """True if `quote` is (mostly) words the player actually said. Lenient on purpose: at least half of the quote's
    words must appear in the command, so small paraphrases ("bigger" for "big") pass but invented reasons don't."""
    q = _WORD.findall(quote.lower())
    if not q:
        return False
    said = _WORD.findall(command.lower())

    def heard(w: str) -> bool:  # same word, or one is a prefix of the other ("big"/"bigger", "enemy"/"enemies" no)
        return any(w == s or (min(len(w), len(s)) >= 3 and (w.startswith(s) or s.startswith(w))) for s in said)

    return sum(map(heard, q)) * 2 >= len(q)


def drop_unasked(intent: IntentPatch, command: str) -> list[str]:
    """Remove ops whose "asked" quote isn't from the command (changes nobody asked for). Returns notes for the log.
    An op with no quote at all is kept (older replies / servers that ignore the schema)."""
    keep, notes, asked = [], [], intent.asked or [""] * len(intent.ops)
    for n, (op, q) in enumerate(zip(intent.ops, asked)):
        if op.op != "unsupported" and q.strip() and not _from_command(q, command):
            notes.append(f"op {n + 1} ({op.op}) dropped: \"{q}\" is not something the command asked for")
            continue
        keep.append((op, q))
    intent.ops = [o for o, _ in keep]
    intent.asked = [q for _, q in keep]
    return notes


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


def _tiles(n: int) -> str:
    return f"{n} tile" if n == 1 else f"{n} tiles"


def _behind(ed: Editor, e: dict, where: str) -> bool:
    """While playing, edits target what's ahead. True (and a repair note) if e is fully behind the player."""
    p = ed.player
    if p and e["x"] + e["w"] - 1 < p["x"] - 1:
        ed.repairs.append(f"{where}: skipped {e['id']} because it is behind the player (edits apply ahead of the player while playing)")
        return True
    return False


def _on(spawn: dict, p: dict) -> bool:
    return p["x"] <= spawn["x"] < p["x"] + p["w"] and spawn["y"] + 1 == p["y"]


def _resize(ed: Editor, p: dict, new_x: int, new_w: int):
    """Resize platform p and keep its riders (and the player start) on it."""
    riders, spawn_on = _riders(ed, p), _on(ed.d["spawn"], p)
    p["x"], p["w"] = new_x, new_w
    lo, hi = p["x"], p["x"] + p["w"]
    for e in riders:
        nx = min(max(e["x"], lo), max(lo, hi - e["w"]))
        if nx != e["x"]:
            ed.repairs.append(f"kept {e['id']} on {p['id']} (x {e['x']} -> {nx})")
            e["x"] = nx
    if spawn_on:
        s = ed.d["spawn"]
        nx = min(max(s["x"], lo), hi - 1)
        if nx != s["x"]:
            ed.repairs.append(f"kept player start on {p['id']} (x {s['x']} -> {nx})")
            s["x"] = nx


def widen_gap(ed: Editor, op: WidenGap, where: str):
    a = analyze(ed.d)
    gap = next((g for g in a["gaps"] if g["id"] == op.gap_id), None)
    if gap is None:
        ed.errors.append(f"{where}: there is no gap '{op.gap_id}'. Use one of: {', '.join(g['id'] for g in a['gaps']) or 'none (the level has no gaps; use another op)'}")
        return
    L, R = ed.get(gap["left"]), ed.get(gap["right"])
    if _behind(ed, {"id": op.gap_id, "x": gap["x"], "w": gap["w"]}, where):
        return
    t, done = op.tiles, 0
    if t > 0:
        todo = t
        px = ed.player["x"] if ed.player else None
        on = lambda p: px is not None and p["x"] <= px < p["x"] + p["w"]  # noqa: E731
        for p in sorted([R, L], key=lambda p: (on(p), -p["w"])):  # not under the player, then the wider side
            k = min(todo, p["w"] - MIN_GROUND)
            if k <= 0:
                continue
            if p is R:
                _resize(ed, R, R["x"] + k, R["w"] - k)
            else:
                _resize(ed, L, L["x"], L["w"] - k)
            todo -= k
        done = t - todo
        if todo:
            ed.repairs.append(f"{op.gap_id} widened by {done} instead of {t} (the ground next to it can't get narrower than {MIN_GROUND})")
    elif t < 0:
        n = min(-t, gap["w"])
        if n < -t:
            ed.repairs.append(f"{op.gap_id} is only {gap['w']} wide; closed it instead of narrowing by {-t}")
        _resize(ed, R, R["x"] - n, R["w"] + n)
        done = -n
    new_x, new_w = L["x"] + L["w"], R["x"] - (L["x"] + L["w"])
    for lid in gap["lava"]:  # lava in the pit follows the gap
        lv = ed.get(lid)
        if new_w <= 0:
            ed.remove(lid)
        elif lv:
            lv["x"], lv["w"] = new_x, new_w
    if done > 0:
        ed.done.append(f"widened {op.gap_id} to {_tiles(gap['w'] + done)}")
    elif done < 0:
        ed.done.append(f"closed {op.gap_id}" if new_w <= 0 else f"narrowed {op.gap_id} to {_tiles(new_w)}")


def shrink_platform(ed: Editor, op: ShrinkPlatform, where: str):
    p = ed.require(op.id, where, "platform")
    if p is None or op.tiles == 0 or _behind(ed, p, where):
        return
    W = ed.d["width"]
    if op.tiles > 0:
        floor = MIN_GROUND if p["y"] + p["h"] >= ed.d["height"] else 1
        t = min(op.tiles, p["w"] - floor)
        if t < op.tiles:
            ed.repairs.append(f"{p['id']} shrunk by {max(t, 0)} instead of {op.tiles} (minimum width {floor})")
        if t <= 0:
            return
        left = {"left": t, "right": 0, "both": t // 2}[op.side]
        _resize(ed, p, p["x"] + left, p["w"] - t)
        ed.done.append(f"shrank {p['id']} to {_tiles(p['w'])}")
    else:
        g = -op.tiles
        solids = [q for q in ed.ents if q["type"] == "platform" and q is not p and q["y"] < p["y"] + p["h"] and p["y"] < q["y"] + q["h"]]
        room_l = p["x"] - max([q["x"] + q["w"] for q in solids if q["x"] + q["w"] <= p["x"]] + [0])
        room_r = min([q["x"] for q in solids if q["x"] >= p["x"] + p["w"]] + [W]) - (p["x"] + p["w"])
        want_l = {"left": g, "right": 0, "both": g // 2}[op.side]
        gl, gr = min(want_l, room_l), min(g - want_l, room_r)
        if gl + gr < g:
            ed.repairs.append(f"{p['id']} grew by {gl + gr} instead of {g} (hit a neighbour or the level edge)")
        if gl + gr:
            _resize(ed, p, p["x"] - gl, p["w"] + gl + gr)
            ed.done.append(f"widened {p['id']} to {_tiles(p['w'])}")


def _blocked_cols(ed: Editor, y: int) -> set[int]:
    """Columns at row y already taken by something you can't stack an enemy/hazard on (and the player)."""
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
    cols.update(cx for cx, cy in ed.player_cells() if cy == y)
    return cols


def _region(ed: Editor, region: str, where: str) -> tuple[list[dict], tuple[int, int]] | None:
    a = analyze(ed.d, ed.player)
    regs = regions(ed.d["width"], ed.player)
    if region in regs:
        lo, hi = regs[region]
        return [p for p in a["ground"] + a["floating"] if overlaps_x(p, lo, hi)], (lo, hi)
    p = ed.get(region)
    if p and p["type"] == "platform":
        return [p], (p["x"], p["x"] + p["w"])
    ed.errors.append(f"{where}: region must be one of {', '.join(regs)} or a platform id; got '{region}'")
    return None


def _spots(ed: Editor, plats: list[dict], lo: int, hi: int, min_w: int = 1) -> list[tuple[int, dict]]:
    out = []
    for p in plats:
        if p["w"] < min_w or p["y"] - 1 < 0:
            continue
        blocked = _blocked_cols(ed, p["y"] - 1)
        out += [(x, p) for x in range(max(p["x"], lo), min(p["x"] + p["w"], hi)) if x not in blocked]
    # nearest-first when the region is relative to the player, left-to-right otherwise
    px = ed.player["x"] if ed.player else None
    return sorted(out, key=lambda s: (abs(s[0] - px), s[0]) if px is not None and lo > px else (s[0],))


def _spread(spots: list, n: int) -> list:
    if n >= len(spots):
        return spots
    if n == 1:
        return [spots[len(spots) // 2]]
    return [spots[round(i * (len(spots) - 1) / (n - 1))] for i in range(n)]


def _where_words(region: str) -> str:
    return {"near_player": "right in front of you", "ahead": "ahead of you", "start": "near the start",
            "middle": "in the middle", "end": "near the end"}.get(region, f"on {region}")


def add_enemy(ed: Editor, op: AddEnemy, where: str):
    r = _region(ed, op.region, where)
    if r is None:
        return
    plats, (lo, hi) = r
    spots = _spots(ed, plats, lo, hi, min_w=2)
    if op.region in PLAYER_REGIONS:  # closest solid ground first, each a couple of tiles apart
        picked, last = [], None
        for s in sorted(spots, key=lambda s: s[0]):
            if last is None or s[0] - last >= 2:
                picked.append(s)
                last = s[0]
        picked = picked[:op.count]
    else:
        picked = [s for i, s in enumerate(_spread(sorted(spots, key=lambda s: s[0]), op.count))]
    chosen = []
    for x, p in picked:
        if any(abs(x - c) < 2 for c in chosen):
            continue
        rng = max(1, min(3, x - p["x"], p["x"] + p["w"] - 1 - x))
        ed.add({"id": ed.new_id("enemy"), "type": "enemy", "x": x, "y": p["y"] - 1,
                "behaviors": ["patrol"], "props": {"speed": op.speed, "range": rng}})
        chosen.append(x)
    if 0 < len(chosen) < op.count:
        ed.repairs.append(f"only room for {len(chosen)} of {op.count} enemies {_where_words(op.region)}")
    if not chosen:
        ed.errors.append(f"{where}: no free solid ground {_where_words(op.region)} for an enemy. "
                         f"Pick another region ({', '.join(regions(ed.d['width'], ed.player))}) or a platform id")
        return
    ed.done.append(f"added {'an enemy' if len(chosen) == 1 else f'{len(chosen)} enemies'} {_where_words(op.region)}")


def add_hazard_near(ed: Editor, op: AddHazardNear, where: str):
    p = ed.require(op.platform_id, where, "platform")
    if p is None or _behind(ed, p, where):
        return
    if p["w"] < 3:
        big = [q["id"] for q in ed.ents if q["type"] == "platform" and q["w"] >= 3]
        ed.errors.append(f"{where}: {p['id']} is only {p['w']} wide; a hazard needs a platform at least 3 wide. Use one of: {', '.join(big)}")
        return
    width = min(op.width, p["w"] - 2)
    a = analyze(ed.d)
    landing_left = any(g["right"] == p["id"] for g in a["gaps"]) or p in a["floating"]
    sides = [op.side] if op.side != "auto" else (["left", "right"] if landing_left else ["right", "left"])
    y = p["y"] - 1
    blocked = _blocked_cols(ed, y)
    for side in sides + [s for s in ("left", "right") if s not in sides]:
        x = p["x"] + 1 if side == "left" else p["x"] + p["w"] - 1 - width
        if not any(c in blocked for c in range(x, x + width)):
            ed.add({"id": ed.new_id(op.kind), "type": op.kind, "x": x, "y": y, "w": width, "h": 1})
            ed.done.append(f"added {op.kind}")
            return
    ed.errors.append(f"{where}: no free spot on {p['id']} (the start, the goal, the player or other objects are in the way); pick another platform")


def add_coins(ed: Editor, op: AddCoins, where: str):
    r = _region(ed, op.region, where)
    if r is None:
        return
    plats, (lo, hi) = r
    coin_cells = {(e["x"], e["y"]) for e in ed.ents if e["type"] == "coin"}
    spots = [(x, p) for x, p in _spots(ed, plats, lo, hi) if (x, p["y"] - 1) not in coin_cells]
    picked = _spread(sorted(spots, key=lambda s: s[0]), op.count)
    for x, p in picked:
        ed.add({"id": ed.new_id("coin"), "type": "coin", "x": x, "y": p["y"] - 1})
    if len(picked) < op.count:
        ed.repairs.append(f"only room for {len(picked)} of {op.count} coins {_where_words(op.region)}")
    if picked:
        ed.done.append(f"added {len(picked)} coin{'s' if len(picked) > 1 else ''} {_where_words(op.region)}")


def add_pickup(ed: Editor, op: AddPickup, where: str):
    r = _region(ed, op.region, where)
    if r is None:
        return
    plats, (lo, hi) = r
    coin_cells = {(e["x"], e["y"]) for e in ed.ents if e["type"] == "coin"}  # _spots already avoids other objects
    spots = [(x, p) for x, p in _spots(ed, plats, lo, hi) if (x, p["y"] - 1) not in coin_cells]
    picked = _spread(sorted(spots, key=lambda s: s[0]), op.count)
    for x, p in picked:
        ed.add({"id": ed.new_id(PICKUP_ID_PREFIX.get(op.kind, op.kind)), "type": op.kind, "x": x, "y": p["y"] - 1})
    name = op.kind.replace("_", " ")
    if not picked:
        ed.errors.append(f"{where}: no free spot {_where_words(op.region)} for a {name} pickup. "
                         f"Pick another region ({', '.join(regions(ed.d['width'], ed.player))}) or a platform id")
        return
    if len(picked) < op.count:
        ed.repairs.append(f"only room for {len(picked)} of {op.count} {name} pickups {_where_words(op.region)}")
    many = len(picked) > 1
    ed.done.append(f"added {len(picked) if many else 'a'} {name} pickup{'s' if many else ''} {_where_words(op.region)}")


def _span_of(ed: Editor, over: str, where: str) -> tuple[int, int, str] | None:
    """x range [lo, hi) for a gap id, region or platform id, plus words for the spoken reply."""
    gap = next((g for g in analyze(ed.d)["gaps"] if g["id"] == over), None)
    if gap:
        return gap["x"], gap["x"] + gap["w"], f"over {over}"
    regs = regions(ed.d["width"], ed.player)
    if over in regs:
        lo, hi = regs[over]
        return lo, hi, _where_words(over)
    p = ed.get(over)
    if p and p["type"] == "platform":
        return p["x"], p["x"] + p["w"], f"above {over}"
    ed.errors.append(f"{where}: 'over' must be a gap id, one of {', '.join(regs)}, or a platform id; got '{over}'")
    return None


def add_platform(ed: Editor, op: AddPlatform, where: str):
    span = _span_of(ed, op.over, where)
    if span is None:
        return
    lo, hi, words = span
    if _behind(ed, {"id": op.over, "x": lo, "w": hi - lo}, where):
        return
    W, ground_top = ed.d["width"], analyze(ed.d)["ground_top"]
    w = min(op.width, W)
    cells = ed.player_cells()

    def fits(x: int, y: int) -> bool:
        if x < 0 or x + w > W or y < 1:
            return False
        rect = {"x": x, "y": y, "w": w, "h": 1}
        pad = {"x": x - 1, "y": y - 1, "w": w + 2, "h": 3}  # keep a tile clear of other platforms (no accidental walls)
        if any(_rect_overlap(pad if e["type"] == "platform" else rect, e) for e in ed.ents):
            return False
        return not any((cx, y) in cells for cx in range(x, x + w))

    center = (lo + hi - w) // 2  # centered on the span; may overhang it if the span is narrower than the platform
    xs = sorted(range(max(0, lo - w + 1), min(W - w, hi - 1) + 1), key=lambda x: (abs(x - center), x))
    for h in sorted(range(1, 7), key=lambda h: (abs(h - op.height), h)):  # requested height first, then nearest
        y = ground_top - h
        x = next((x for x in xs if fits(x, y)), None)
        if x is None:
            continue
        if h != op.height:
            ed.repairs.append(f"{where}: no room {op.height} tiles up {words}; placed it {h} tiles up")
        ed.add({"id": ed.new_id("plat"), "type": "platform", "x": x, "y": y, "w": w, "h": 1})
        ed.done.append(f"added a platform {words}")
        return
    ed.errors.append(f"{where}: no free space for a {w}-wide platform {words}; other objects are in the way. "
                     "Try a smaller width, or another gap, region or platform")


def set_physics(ed: Editor, op: SetPhysics, where: str):
    lo, hi = PHYSICS_LIMITS[op.key]
    v = float(min(max(op.value, lo), hi))
    if v != op.value:
        ed.repairs.append(f"{op.key} clamped {op.value:g} -> {v:g} (allowed {lo}-{hi})")
    old = ed.d["physics"][op.key]
    ed.set_physics(op.key, v)
    name = op.key.replace("_", " ").replace("jump velocity", "jump strength")
    if v != old:
        ed.done.append(f"{'raised' if v > old else 'lowered'} {name} to {v:g}")
    else:  # shown to the model in the retry message if the whole reply changed nothing
        ed.repairs.append(f"{where}: {op.key} is already {old:g}, so this changed nothing; "
                          f"use a value higher or lower than {old:g}, as the command asks")


def compile_intent(level: Level, intent: IntentPatch, player: dict | None = None) -> Editor:
    """Apply intent ops to a copy of level. Inspect ed.errors (unfixable), ed.repairs, ed.done; ed.diff(); ed.result()."""
    ed = Editor(level, player)
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
        elif op.op == "add_platform":
            add_platform(ed, op, where)
        elif op.op == "add_pickup":
            add_pickup(ed, op, where)
        elif op.op == "remove":
            e = ed.require(op.id, where)
            if e is not None:
                if e["type"] == "goal" and sum(x["type"] == "goal" for x in ed.ents) == 1:
                    ed.errors.append(f"{where}: can't remove the only goal; leave it in place")
                elif e["type"] == "platform" and _on(ed.d["spawn"], e):
                    ed.errors.append(f"{where}: can't remove {e['id']}, the player starts on it; shrink it instead")
                else:
                    ed.remove(op.id)
                    ed.done.append(f"removed {op.id}")
        elif op.op == "set_property":
            e = ed.require(op.id, where)
            if e is None or _behind(ed, roam_span(e, ed.ents), where):
                continue
            old = e["props"].get(op.key.removeprefix("props."))
            if op.key == "behaviors":
                ed.set(e, "behaviors", op.value if isinstance(op.value, list) else [str(op.value)])
            elif op.key in ("x", "y", "w", "h", "type", "id"):
                ed.errors.append(f"{where}: can't set '{op.key}' directly; use widen_gap or shrink_platform, or remove it and add a new one")
                continue
            elif op.key.removeprefix("props.") in PHYSICS_LIMITS:
                ed.errors.append(f"{where}: {op.key.removeprefix('props.')} is a level-wide physics setting, not a property "
                                 f"of {e['id']}; use set_physics")
                continue
            elif not e["behaviors"]:  # props are read only by behaviors (mechanics.js), so this would do nothing
                with_b = ", ".join(f"{x['id']} ({'/'.join(x['behaviors'])})" for x in ed.ents if x["behaviors"]) or "none"
                ed.errors.append(f"{where}: {e['id']} has no behaviors, so props.{op.key.removeprefix('props.')} would do "
                                 f"nothing (props are only read by behaviors). Objects with behaviors: {with_b}")
                continue
            else:
                k = op.key.removeprefix("props.")
                value, spec = op.value, prop_spec(e, k)
                if spec:
                    _, lo, hi = spec
                    if isinstance(value, bool) or not isinstance(value, (int, float)):
                        ed.errors.append(f"{where}: {e['id']} {k} must be a number from {lo:g} to {hi:g}; got {value!r}")
                        continue
                    clamped = min(max(value, lo), hi)
                    if clamped != value:
                        ed.repairs.append(f"{e['id']} {k} clamped {value:g} -> {clamped:g} (allowed {lo:g}-{hi:g})")
                        value = clamped
                ed.set(e, f"props.{k}", value)
                op = op.model_copy(update={"value": value})
            k = op.key.removeprefix("props.")
            if k == "speed" and isinstance(op.value, (int, float)) and isinstance(old, (int, float)) and op.value != old:
                alike = sum(x["type"] == e["type"] and x["behaviors"] == e["behaviors"] for x in ed.ents)
                ed.done.append(f"made {e['type'] + 's' if alike > 1 else e['id']} {'faster' if op.value > old else 'slower'}")
            elif k != "behaviors" and isinstance(op.value, (int, float)) and not isinstance(op.value, bool):
                ed.done.append(f"set {e['id']} {k.replace('_', ' ')} to {op.value:g}")
            else:
                ed.done.append(f"changed {e['type']} {k}")
        elif op.op == "set_physics":
            set_physics(ed, op, where)
        elif op.op == "set_look":
            set_look(ed, op, where)
        elif op.op == "set_scene":
            set_scene(ed, op, where)
        elif op.op == "add_reaction":
            add_reaction(ed, op, where)
        elif op.op == "remove_reaction":
            remove_reaction(ed, op, where)
    ed.autofix()
    return ed
