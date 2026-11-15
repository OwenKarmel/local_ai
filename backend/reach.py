"""Player reach from the current level's physics: a lightweight safety layer (the full playability checker is
under "Later" in plan.md).

- reach(physics): how far and how high the player can jump, with and without double jump. Goes into every prompt.
- gap_violations(old, new): gaps the edit made wider than the player can jump. The pipeline rejects those patches.

The movement constants mirror frontend/game.js (COYOTE_MS, PLAYER_W, double jump = 0.9 x jump_velocity).
Keep them in sync with game.js (decisions log 11-14 21:30). Estimates assume a full-speed run-up and the
double jump used at the top of the first jump; they ignore the variable-jump cut (releasing early only shortens).
"""
import math

from .summary import analyze

TILE = 32
COYOTE_S = 0.100     # game.js COYOTE_MS
PLAYER_W = 24        # game.js PLAYER_W (px)
DOUBLE_JUMP = 0.9    # game.js: second jump = jump_velocity * 0.9


def reach(physics: dict) -> dict:
    g, v, r = float(physics["gravity"]), float(physics["jump_velocity"]), float(physics["run_speed"])
    h1 = v * v / (2 * g)                       # apex height of one jump (px)
    t1 = 2 * v / g                             # airtime landing at the take-off height (s)
    h2 = (DOUBLE_JUMP * v) ** 2 / (2 * g)      # extra height from the double jump at the apex
    t2 = v / g + DOUBLE_JUMP * v / g + math.sqrt(2 * (h1 + h2) / g)
    gap = lambda t: max(0, math.floor((r * (t + COYOTE_S) - PLAYER_W) / TILE))  # noqa: E731
    return {
        "max_gap": gap(t1),
        "max_height": max(0, math.floor(h1 / TILE)),
        "max_gap_double": gap(t2),
        "max_height_double": max(0, math.floor((h1 + h2) / TILE)),
    }


def reach_line(physics: dict) -> str:
    rc = reach(physics)
    return (f"Player reach with this physics: gaps up to {rc['max_gap']} tiles, ledges up to {rc['max_height']} tiles high "
            f"(with double jump: {rc['max_gap_double']} tiles, {rc['max_height_double']} high). Never make a gap wider than "
            f"{rc['max_gap']} tiles.")


def gap_violations(old: dict, new: dict) -> list[str]:
    """Gaps in `new` wider than the player can jump that weren't already that wide in `old`. Messages say how to fix."""
    rn = reach(new["physics"])["max_gap"]
    ro = reach(old["physics"])["max_gap"]
    before = {(g["left"], g["right"]): g["w"] for g in analyze(old)["gaps"]}
    out = []
    for g in analyze(new)["gaps"]:
        if g["w"] <= rn:
            continue
        prev = before.get((g["left"], g["right"]))
        if prev is not None and prev >= g["w"] and prev > ro:
            continue  # already impossible before this edit; not this command's doing
        out.append(f"{g['id']} would be {g['w']} tiles wide, but with this physics the player can jump at most {rn} tiles. "
                   f"Keep every gap at {rn} tiles or less (or don't widen it).")
    return out
