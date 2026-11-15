"""Level analysis: ground segments, gaps, floating platforms, regions, and what stands where.

The model never sees raw coordinates for editing; it sees summary_text() and refers to ids from it.
player = {"x", "y", "has_double_jump", "is_big"} in tiles (the tile containing the player's center), or None.
"""

FIXED_REGIONS = ("start", "middle", "end")
PLAYER_REGIONS = ("near_player", "ahead")  # only offered while the game is being played
NEAR_TILES = (2, 6)    # near_player = x+2 .. x+5
AHEAD_TILES = (2, 15)  # ahead       = x+2 .. x+14
# Category word shown after each object's type, so players' words ("powerup", "hazard", "flag") match an object.
# The prompt's OBJECT KINDS legend explains each category once.
# Props each behavior in mechanics.js reads, with allowed ranges: shown to the model (only for behaviors present
# in the level) and enforced by set_property. ENEMY_PROPS are read by game.js for every enemy.
# Model-written behaviors (task 6) may read other keys; those are allowed but not range-checked.
# A max given as another prop's name means "below that prop" (that prop's value - 1, default 1).
ENEMY_PROPS = {"hp": ("hits to defeat (stomps); default 1", 1, 30)}
BEHAVIOR_PROPS = {
    "patrol": {"speed": ("walk speed px/s", 20, 300), "range": ("tiles it walks each way", 1, 20)},
    "boss": {
        "phase2_at": ("phase 2 starts when hp left <= this; must stay below hp, or it starts in phase 2", 0, "hp"),
        "speed": ("phase 1 walk speed px/s", 20, 300),
        "phase2_speed": ("phase 2 walk speed px/s", 20, 400),
        "jump_every": ("seconds between hops, 0 = never", 0, 20),
        "shoot_every": ("fire rate: seconds between shots in phase 2; higher = shoots less often, 0 = never", 0, 20),
        "shot_speed": ("how fast each projectile flies, px/s", 80, 600),
    },
}


def prop_spec(e: dict, key: str) -> tuple[str, float, float] | None:
    """(meaning, min, max) for a prop of entity e, or None if no known behavior reads it."""
    spec = ENEMY_PROPS.get(key) if e["type"] == "enemy" else None
    for b in e.get("behaviors", []):
        spec = spec or BEHAVIOR_PROPS.get(b, {}).get(key)
    if spec is None:
        return None
    meaning, lo, hi = spec
    if isinstance(hi, str):  # bounded by another prop: stay below it
        other = (e.get("props") or {}).get(hi, 1)
        hi = max(lo, (other if isinstance(other, (int, float)) else 1) - 1)
    return meaning, lo, hi


KIND_TAG = {"coin": "pickup", "double_jump": "powerup", "grow": "powerup", "spikes": "hazard", "lava": "hazard", "enemy": "enemy",
            "goal": "finish flag"}


def overlaps_x(a: dict, x0: int, x1: int) -> bool:
    """a spans [x, x+w); test against [x0, x1)."""
    return a["x"] < x1 and a["x"] + a["w"] > x0


def regions(width: int, player: dict | None = None) -> dict[str, tuple[int, int]]:
    """Half-open x ranges. Thirds of the level, plus player-relative ranges when playing."""
    t1, t2 = round(width / 3), round(2 * width / 3)
    out = {"start": (0, t1), "middle": (t1, t2), "end": (t2, width)}
    if player:
        px = player["x"]
        out["near_player"] = (min(width - 1, px + NEAR_TILES[0]), min(width, px + NEAR_TILES[1]))
        out["ahead"] = (min(width - 1, px + AHEAD_TILES[0]), min(width, px + AHEAD_TILES[1]))
    return out


def support_of(e: dict, ents: list[dict]) -> dict | None:
    """Platform this entity stands on (its bottom touches the platform's top row)."""
    for p in ents:
        if p["type"] == "platform" and p["y"] == e["y"] + e["h"] and overlaps_x(p, e["x"], e["x"] + e["w"]):
            return p
    return None


def roam_span(e: dict, ents: list[dict]) -> dict:
    """x extent an object can be found in: its own tiles, or for a moving enemy (one with behaviors)
    the whole platform it walks on. Used for "ahead of / behind the player"."""
    if e.get("type") == "enemy" and e.get("behaviors"):
        sup = support_of(e, ents)
        if sup:
            lo, hi = min(e["x"], sup["x"]), max(e["x"] + e["w"], sup["x"] + sup["w"])
            return {"id": e["id"], "x": lo, "w": hi - lo}
    return e


def analyze(level: dict, player: dict | None = None) -> dict:
    W, H, ents = level["width"], level["height"], level["entities"]
    plats = [e for e in ents if e["type"] == "platform"]
    ground = sorted([p for p in plats if p["y"] + p["h"] >= H], key=lambda p: p["x"])
    floating = sorted([p for p in plats if p["y"] + p["h"] < H], key=lambda p: (p["x"], p["y"]))
    ground_top = min((g["y"] for g in ground), default=H - 2)
    gaps = []
    for a, b in zip(ground, ground[1:]):
        gx = a["x"] + a["w"]
        if b["x"] > gx:
            lava = [e["id"] for e in ents if e["type"] == "lava" and e["y"] >= ground_top and overlaps_x(e, gx, b["x"])]
            gaps.append({"id": f"gap{len(gaps) + 1}", "left": a["id"], "right": b["id"], "x": gx, "w": b["x"] - gx, "lava": lava})
    next_gap = None
    if player:
        next_gap = next((g["id"] for g in gaps if g["x"] + g["w"] > player["x"] + 1), None)
    return {"W": W, "H": H, "ground": ground, "floating": floating, "ground_top": ground_top, "gaps": gaps,
            "regions": regions(W, player), "next_gap": next_gap}


def _span(e: dict) -> str:
    return f"x {e['x']}" if e["w"] == 1 else f"x {e['x']}-{e['x'] + e['w'] - 1}"


def _look_str(look: dict | None, sprite=None, tint=None) -> str:
    """'sprite gem_red, tint #e53935, scale 1.5, effects pulse+spin' (only what differs from the default)."""
    parts = [f"sprite {sprite}"] if sprite else []
    if tint:
        parts.append(f"tint {tint}")
    for k, v in (look or {}).items():
        if v in (None, [], False) or k in ("sprite", "tint"):
            continue
        parts.append(f"{k} {'+'.join(v) if isinstance(v, list) else (f'{v:g}' if isinstance(v, float) else v)}")
    return ", ".join(parts)


def looks_text(level: dict) -> list[str]:
    """Current non-default looks: player, scene, reactions, and objects grouped by identical look."""
    L = []
    pl = level.get("player_look") or {}
    s = _look_str(pl, pl.get("sprite"), pl.get("tint"))
    if s:
        L.append(f"  player: {s}")
    by: dict[str, list[str]] = {}
    for e in level["entities"]:
        s = _look_str(e.get("look"), e.get("sprite"), e.get("tint"))
        if s:
            by.setdefault(s, []).append(e["id"])
    for s, ids in by.items():
        L.append(f"  {', '.join(ids)}: {s}")
    sc = _look_str(level.get("scene"))
    if sc:
        L.append(f"  scene: {sc}")
    for r in level.get("reactions") or []:
        L.append(f"  reaction: on {r['event']} -> {r['effect']}{' ' + r['color'] if r.get('color') else ''}")
    return (["Current looks (everything else is the default look):"] + L) if L else ["Current looks: all default"]


def summary_text(level: dict, player: dict | None = None) -> str:
    a = analyze(level, player)
    ents = level["entities"]
    ph = level["physics"]
    px = player["x"] if player else None
    gap_lava = {lid for g in a["gaps"] for lid in g["lava"]}

    def rel(e: dict) -> str:
        if px is None:
            return ""
        e = roam_span(e, ents)
        if e["x"] + e["w"] - 1 < px:
            return " [behind the player]"
        return " [player is here]" if e["x"] <= px else " [ahead]"

    L = [f"Level: {a['W']} tiles wide, {a['H']} tall. The player runs left to right from the start to the goal."]
    L.append("Regions: " + ", ".join(f"{k} = x {lo}-{hi - 1}" for k, (lo, hi) in a["regions"].items()))
    L.append(f"Physics (level-wide): gravity {ph['gravity']:g}, jump_velocity {ph['jump_velocity']:g}, run_speed {ph['run_speed']:g}")
    from .reach import reach_line  # local import: reach.py imports summary
    L.append(reach_line(ph))
    ab = [k for k, v in level.get("abilities", {}).items() if v.get("enabled")]
    L.append("Abilities on: " + (", ".join(ab) if ab else "none"))
    if player:
        on = next((g["id"] for g in a["ground"] + a["floating"] if g["x"] <= px < g["x"] + g["w"]), "nothing (in the air)")
        L.append(f"PLAYER: playing right now, at x {px} above {on}"
                 f"{', has double jump' if player.get('has_double_jump') else ''}"
                 f"{', is big (grow powerup)' if player.get('is_big') else ''}. "
                 f"The next gap ahead is {a['next_gap'] or 'none'}.")
    L.append("Ground, left to right:")
    gaps_after = {g["left"]: g for g in a["gaps"]}
    for g in a["ground"]:
        L.append(f"  {g['id']}: ground, {_span(g)} ({g['w']} wide){rel(g)}")
        if g["id"] in gaps_after:
            gp = gaps_after[g["id"]]
            kind = f"lava pit ({', '.join(gp['lava'])})" if gp["lava"] else "bottomless pit"
            L.append(f"  {gp['id']}: GAP between {gp['left']} and {gp['right']}, {gp['w']} tiles wide "
                     f"(x {gp['x']}-{gp['x'] + gp['w'] - 1}), {kind}{rel(gp)}")
    if a["floating"]:
        L.append("Floating platforms:")
        for p in a["floating"]:
            L.append(f"  {p['id']}: {_span(p)} ({p['w']} wide), {a['ground_top'] - p['y']} tiles above the ground{rel(p)}")
    L.append("Objects:")
    sx = level["spawn"]["x"]
    start_on = next((g["id"] for g in a["ground"] + a["floating"] if g["x"] <= sx < g["x"] + g["w"]), "?")
    L.append(f"  player start: on {start_on} at x {sx}")
    for e in ents:
        if e["type"] == "platform" or e["id"] in gap_lava:
            continue
        sup = support_of(e, ents)
        where = f"on {sup['id']}" if sup else f"floating {max(0, a['ground_top'] - e['y'] - e['h'])} tiles above the ground"
        extra = ""
        if e["type"] == "enemy" and e["behaviors"] == ["patrol"] and set(e["props"]) <= {"speed", "range"}:
            extra = f", speed {e['props'].get('speed', 60)}"
        elif e["behaviors"]:  # every prop the behaviors read, so the model knows what set_property can change
            props = ", ".join(f"{k} {v:g}" if isinstance(v, (int, float)) and not isinstance(v, bool) else f"{k} {v}"
                              for k, v in e["props"].items())
            extra = f", behaviors {'+'.join(e['behaviors'])} ({props or 'no props'})"
        elif e["type"] in ("spikes", "lava") and e["w"] > 1:
            extra = f", {e['w']} wide"
        if e["w"] > 1 and e["h"] > 1 and e["type"] not in ("spikes", "lava", "goal"):
            extra += f", size {e['w']}x{e['h']} tiles"
        if e["type"] == "goal" and e["props"].get("locked_by"):
            lk = e["props"]["locked_by"]
            alive = any(x["id"] == lk for x in ents)
            extra += f", LOCKED until {lk} is defeated" if alive else ""
        tag = KIND_TAG.get(e["type"])
        kind = e["type"] if tag in (None, e["type"]) else f"{e['type']} ({tag})"
        L.append(f"  {e['id']}: {kind} {where} at {_span(e)}{extra}{rel(e)}")
    L += looks_text(level)
    used = {b for e in ents for b in e["behaviors"] if b in BEHAVIOR_PROPS}
    if any(e["type"] == "enemy" and (e["props"].get("hp", 1) > 1 or set(e["behaviors"]) - {"patrol"}) for e in ents):
        used.add("enemy")
    if used - {"patrol"}:  # the patrol keys are already in the prompt; only spell out the others
        L.append("Behavior props (set_property keys, allowed range):")
        for b in sorted(used):
            spec = ENEMY_PROPS if b == "enemy" else BEHAVIOR_PROPS[b]
            name = "any enemy" if b == "enemy" else b
            L.append(f"  {name}: " + "; ".join(f"{k} = {d} ({lo:g}-{hi:g})" if not isinstance(hi, str) else f"{k} = {d} ({lo:g} to {hi} - 1)"
                                            for k, (d, lo, hi) in spec.items()))
    return "\n".join(L)
