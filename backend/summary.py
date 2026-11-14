"""Level analysis: ground segments, gaps, floating platforms, regions, and what stands where.

The model never sees raw coordinates; it sees summary_text() and refers to ids from it.
"""

REGIONS = ("start", "middle", "end")


def overlaps_x(a: dict, x0: int, x1: int) -> bool:
    """a spans [x, x+w); test against [x0, x1)."""
    return a["x"] < x1 and a["x"] + a["w"] > x0


def regions(width: int) -> dict[str, tuple[int, int]]:
    """Half-open x ranges for start/middle/end thirds."""
    t1, t2 = round(width / 3), round(2 * width / 3)
    return {"start": (0, t1), "middle": (t1, t2), "end": (t2, width)}


def support_of(e: dict, ents: list[dict]) -> dict | None:
    """Platform this entity stands on (its bottom touches the platform's top row)."""
    for p in ents:
        if p["type"] == "platform" and p["y"] == e["y"] + e["h"] and overlaps_x(p, e["x"], e["x"] + e["w"]):
            return p
    return None


def analyze(level: dict) -> dict:
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
    return {"W": W, "H": H, "ground": ground, "floating": floating, "ground_top": ground_top, "gaps": gaps, "regions": regions(W)}


def _span(e: dict) -> str:
    return f"x {e['x']}" if e["w"] == 1 else f"x {e['x']}-{e['x'] + e['w'] - 1}"


def summary_text(level: dict) -> str:
    a = analyze(level)
    ents = level["entities"]
    ph = level["physics"]
    gap_lava = {lid for g in a["gaps"] for lid in g["lava"]}
    L = [f"Level: {a['W']} tiles wide, {a['H']} tall. The player runs left to right from the start to the goal."]
    L.append("Regions: " + ", ".join(f"{k} = x {lo}-{hi - 1}" for k, (lo, hi) in a["regions"].items()))
    L.append(f"Physics: gravity {ph['gravity']:g}, jump_velocity {ph['jump_velocity']:g}, run_speed {ph['run_speed']:g}")
    L.append("Ground, left to right:")
    gaps_after = {g["left"]: g for g in a["gaps"]}
    for g in a["ground"]:
        L.append(f"  {g['id']}: ground, {_span(g)} ({g['w']} wide)")
        if g["id"] in gaps_after:
            gp = gaps_after[g["id"]]
            kind = f"lava pit ({', '.join(gp['lava'])})" if gp["lava"] else "bottomless pit"
            L.append(f"  {gp['id']}: GAP between {gp['left']} and {gp['right']}, {gp['w']} tiles wide (x {gp['x']}-{gp['x'] + gp['w'] - 1}), {kind}")
    if a["floating"]:
        L.append("Floating platforms:")
        for p in a["floating"]:
            L.append(f"  {p['id']}: {_span(p)} ({p['w']} wide), {a['ground_top'] - p['y']} tiles above the ground")
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
            extra = f", speed {e['props'].get('speed', 60)}, patrol range {e['props'].get('range', 3)}"
        elif e["type"] in ("spikes", "lava") and e["w"] > 1:
            extra = f", {e['w']} wide"
        L.append(f"  {e['id']}: {e['type']} {where} at {_span(e)}{extra}")
    return "\n".join(L)
