"""Level analysis: ground segments, gaps, floating platforms, regions, and what stands where.

The model never sees raw coordinates for editing; it sees summary_text() and refers to ids from it.
player = {"x", "y", "has_double_jump"} in tiles (the tile containing the player's center), or None.
"""

FIXED_REGIONS = ("start", "middle", "end")
PLAYER_REGIONS = ("near_player", "ahead")  # only offered while the game is being played
NEAR_TILES = (2, 6)    # near_player = x+2 .. x+5
AHEAD_TILES = (2, 15)  # ahead       = x+2 .. x+14
# Category word shown after each object's type, so players' words ("powerup", "hazard", "flag") match an object.
# The prompt's OBJECT KINDS legend explains each category once.
KIND_TAG = {"coin": "pickup", "double_jump": "powerup", "spikes": "hazard", "lava": "hazard", "enemy": "enemy",
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


def summary_text(level: dict, player: dict | None = None) -> str:
    a = analyze(level, player)
    ents = level["entities"]
    ph = level["physics"]
    px = player["x"] if player else None
    gap_lava = {lid for g in a["gaps"] for lid in g["lava"]}

    def rel(e: dict) -> str:
        if px is None:
            return ""
        if e["x"] + e["w"] - 1 < px:
            return " [behind the player]"
        return " [player is here]" if e["x"] <= px else " [ahead]"

    L = [f"Level: {a['W']} tiles wide, {a['H']} tall. The player runs left to right from the start to the goal."]
    L.append("Regions: " + ", ".join(f"{k} = x {lo}-{hi - 1}" for k, (lo, hi) in a["regions"].items()))
    L.append(f"Physics (level-wide): gravity {ph['gravity']:g}, jump_velocity {ph['jump_velocity']:g}, run_speed {ph['run_speed']:g}")
    ab = [k for k, v in level.get("abilities", {}).items() if v.get("enabled")]
    L.append("Abilities on: " + (", ".join(ab) if ab else "none"))
    if player:
        on = next((g["id"] for g in a["ground"] + a["floating"] if g["x"] <= px < g["x"] + g["w"]), "nothing (in the air)")
        L.append(f"PLAYER: playing right now, at x {px} above {on}"
                 f"{', has double jump' if player.get('has_double_jump') else ''}. "
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
        if e["type"] == "enemy":
            extra = f", speed {e['props'].get('speed', 60)}"
        elif e["type"] in ("spikes", "lava") and e["w"] > 1:
            extra = f", {e['w']} wide"
        tag = KIND_TAG.get(e["type"])
        kind = e["type"] if tag in (None, e["type"]) else f"{e['type']} ({tag})"
        L.append(f"  {e['id']}: {kind} {where} at {_span(e)}{extra}{rel(e)}")
    return "\n".join(L)
