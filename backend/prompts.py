"""Prompts for the level-edit model (intent format). Examples are built from summary_text so they always match."""
import json
import re
from pathlib import Path

from .looks import SPRITE_NAMES
from .summary import summary_text

_CATALOG = Path(__file__).resolve().parent.parent / "frontend" / "assets" / "catalog.json"
_KINDS = ("coin", "double_jump", "grow", "spikes", "lava", "enemy", "goal", "platform")


def _load_looks() -> dict[str, str]:
    """kind -> what its default sprite looks like, from the sprite catalog, so players can name things by their
    look ("the star", "a mushroom", "that slime")."""
    try:
        cat = json.loads(_CATALOG.read_text())
    except (OSError, ValueError):
        return {}
    desc = {s["name"]: s.get("description", "") for s in cat.get("sprites", [])}
    out = {}
    for kind in _KINDS:
        d = desc.get(cat.get("defaults", {}).get(kind, ""), "")
        d = re.sub(r"\s*\(default [^)]*\)", "", d).split(":")[0].strip()
        if d:
            out[kind] = d
    return out


_LOOKS = _load_looks()


def _k(kind: str) -> str:
    """'grow [looks like: red mushroom]' (or just the kind if the catalog has no description)."""
    return f"{kind} [looks like: {_LOOKS[kind]}]" if kind in _LOOKS else kind


INTENT_SYSTEM = """You are a game copilot editing a 2D platformer while it is played. Choose high-level ops; the engine computes positions.
Input: LEVEL SUMMARY (objects with ids) + COMMAND. Reply ONLY JSON {"plan": "<few words>", "ops": [...]}. Every op has "asked": the exact command words it carries out (copy them; for a vague command like "spice it up", every op quotes the whole command). The JSON schema lists allowed values.

KINDS (players may name them by looks): <<K:coin>> pickup. <<K:double_jump>> powerup: one extra air jump. <<K:grow>> powerup: become big, survive one hit. <<K:spikes>>, <<K:lava>>: kill on touch. <<K:enemy>>: patrols, dies when stomped. <<K:goal>>: finish. platform: ground or ledge.

OPS
widen_gap {gap_id, tiles}: + wider, - narrower
shrink_platform {id, tiles, side}: + narrower, - wider
add_enemy {region, count, speed}: 60 normal, 100+ fast
add_hazard_near {platform_id, kind, width, side}
add_coins {region, count}
add_platform {over: gap/region/platform, height, width}
add_pickup {kind, region, count}
remove {id}
set_property {id, key, value}: props read by behaviors (patrol: speed, range; others in the summary)
set_physics {key, value}: LEVEL-WIDE gravity (1200), jump_velocity (560), run_speed (200)
set_look {target, sprite, tint, top_tint, body_tint, scale, scale_x, scale_y, alpha, flip_y, glow, effects, reset}: visual only
set_scene {overlay, overlay_alpha, weather, weather_color, filter, hue_shift, saturation, brightness, pixelate, zoom, reset}: whole screen, visual only
add_reaction {event, effect, color, size} / remove_reaction {event, effect}: visual effect when something happens
unsupported {reason}: only for a part no op can do
REGIONS: start, middle, end, a platform id; while playing also near_player, ahead.
SPRITES: <<SPRITES>>

RULES
- Do only what is asked: most commands need one op, at most 6. No extras. Plural = one op per matching id.
- Looks (color, size, sprite, glow, effects, weather, filters) use set_look/set_scene/add_reaction only. Colors are hex. bigger 1.5, huge 2.5, smaller 0.6, tiny 0.4. Grass = top_tint, dirt = body_tint.
- Never substitute a different thing; use unsupported for that part. Anything outside the level and its looks (sound, music, saving, menus) is unsupported. Gap size: always widen_gap. Physics only via set_physics.
- While the PLAYER line is present, changes go AHEAD of the player ([ahead] items, the next gap, ahead/near_player) unless the command names a place or the whole level. Prefer things ahead over physics. Never edit [behind the player].
- Modest amounts: a bit = 1 tile / 15%; more, bigger = 1-2 tiles / 25%; a lot = 3 tiles / 50%. Only ids from the summary.

<<EXAMPLES>>"""
INTENT_SYSTEM = INTENT_SYSTEM.replace("<<SPRITES>>", ", ".join(SPRITE_NAMES))
INTENT_SYSTEM = re.sub(r"<<K:(\w+)>>", lambda m: _k(m.group(1)), INTENT_SYSTEM)
INTENT_SYSTEM = re.sub(r"<<L:(\w+)>>", lambda m: _LOOKS.get(m.group(1), "see above"), INTENT_SYSTEM)

_EX_LEVEL = {
    "name": "example", "tile_size": 32, "width": 30, "height": 15,
    "physics": {"gravity": 1200, "jump_velocity": 560, "run_speed": 200}, "abilities": {},
    "spawn": {"x": 1, "y": 12},
    "entities": [
        {"id": "g1", "type": "platform", "x": 0, "y": 13, "w": 10, "h": 2, "behaviors": [], "props": {}},
        {"id": "g2", "type": "platform", "x": 12, "y": 13, "w": 8, "h": 2, "behaviors": [], "props": {}},
        {"id": "g3", "type": "platform", "x": 22, "y": 13, "w": 8, "h": 2, "behaviors": [], "props": {}},
        {"id": "p1", "type": "platform", "x": 14, "y": 9, "w": 3, "h": 1, "behaviors": [], "props": {}},
        {"id": "e1", "type": "enemy", "x": 15, "y": 12, "w": 1, "h": 1, "behaviors": ["patrol"], "props": {"speed": 60, "range": 2}},
        {"id": "c1", "type": "coin", "x": 15, "y": 8, "w": 1, "h": 1, "behaviors": [], "props": {}},
        {"id": "goal", "type": "goal", "x": 28, "y": 11, "w": 1, "h": 2, "behaviors": [], "props": {}},
    ],
}
_EX_PLAYER = {"x": 13, "y": 12, "has_double_jump": False}
EXAMPLES = [  # must not match demo commands (see CLAUDE.md core principle)
    ("narrow the second gap a little and scatter coins all over the level", False, {
        "plan": "gap2 1 narrower; coins at start, middle, end",
        "ops": [
            {"op": "widen_gap", "asked": "narrow the second gap a little", "gap_id": "gap2", "tiles": -1},
            {"op": "add_coins", "asked": "scatter coins all over the level", "region": "start", "count": 1},
            {"op": "add_coins", "asked": "scatter coins all over the level", "region": "middle", "count": 1},
            {"op": "add_coins", "asked": "scatter coins all over the level", "region": "end", "count": 1},
        ],
    }),
    ("put a small ledge in front of me, slow that enemy down and paint it teal", True, {
        "plan": "ledge near player; slow e1; teal tint on e1",
        "ops": [
            {"op": "add_platform", "asked": "put a small ledge in front of me", "over": "near_player", "height": 2, "width": 2},
            {"op": "set_property", "asked": "slow that enemy down", "id": "e1", "key": "speed", "value": 40},
            {"op": "set_look", "asked": "paint it teal", "target": "e1", "tint": "#1fb5a8"},
        ],
    }),
    ("make the next bit more fun", True, {
        "plan": "vague, while playing: things ahead, not physics",
        "ops": [
            {"op": "add_coins", "asked": "make the next bit more fun", "region": "ahead", "count": 3},
            {"op": "add_platform", "asked": "make the next bit more fun", "over": "ahead", "height": 2, "width": 3},
        ],
    }),
    ("cozy autumn evening, a ripple when I grab coins, and let me save my game", False, {
        "plan": "warm wash + leaves; ring on coin; saving unsupported",
        "ops": [
            {"op": "set_scene", "asked": "cozy autumn evening", "overlay": "#ff7a30", "overlay_alpha": 0.15, "weather": ["leaves"]},
            {"op": "add_reaction", "asked": "a ripple when I grab coins", "event": "coin", "effect": "ring", "color": "#ffd27a"},
            {"op": "unsupported", "asked": "let me save my game", "reason": "save the game"},
        ],
    }),
]


def _examples_text() -> str:
    lines = ["EXAMPLE LEVEL (when playing, the player is at x 13):", summary_text(_EX_LEVEL, _EX_PLAYER), "", "EXAMPLES"]
    for cmd, playing, patch in EXAMPLES:
        lines.append(f"COMMAND{' (playing)' if playing else ''}: {cmd}")
        lines.append(json.dumps(patch, separators=(",", ":")))
    return "\n".join(lines)


INTENT_SYSTEM = INTENT_SYSTEM.replace("<<EXAMPLES>>", _examples_text())


def intent_messages(level: dict, command: str, player: dict | None = None) -> list[dict]:
    """Static instructions + examples first (reusable prefix), then this level and command."""
    return [{"role": "system", "content": INTENT_SYSTEM},
            {"role": "user", "content": f"LEVEL SUMMARY:\n{summary_text(level, player)}\n\nCOMMAND: {command}"}]


def retry_message(errors: list[str]) -> dict:
    lines = "\n".join(f"- {e}" for e in errors)
    return {"role": "user", "content": f"Some of those operations could not be applied:\n{lines}\n\n"
                                       "Return the whole corrected JSON object (all ops, fixed as described), nothing else."}
