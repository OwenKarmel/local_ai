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


# Kept compact on purpose: every token here is processed on each command (no prefix cache on some servers).
INTENT_SYSTEM = f"""You edit a running 2D platformer by choosing operations. The engine handles all coordinates.
Input: a LEVEL SUMMARY (objects with ids) and a COMMAND.

KINDS: {_k('coin')}: pickup. {_k('double_jump')}: powerup, one extra air jump. {_k('grow')}: powerup, player grows and survives one hit.
{_k('spikes')}, {_k('lava')}: hazards, kill on touch. {_k('enemy')}: patrols, dies when stomped. {_k('goal')}: finish flag. platform: ground or floating ledge.

LEVEL OPS
- widen_gap {{gap_id, tiles}} (+ wider, - narrower)
- shrink_platform {{id, tiles, side: left|right|both}} (+ narrower, - wider)
- add_enemy {{region, count, speed}} (60 normal, 100+ fast)
- add_hazard_near {{platform_id, kind: spikes|lava, width, side}}
- add_coins {{region, count}}
- add_platform {{over: gap, region or platform id, height: tiles above ground, width}}
- add_pickup {{kind: double_jump|grow, region, count}}
- remove {{id}}
- set_property {{id, key, value}}: behavior props (patrol: speed, range; others listed in the summary)
- set_physics {{key: gravity (default 1200)|jump_velocity (560)|run_speed (200), value}}
LOOK OPS (visual only)
- set_look {{target, fields}}: target = an id or a group: player, enemies, coins, powerups, pickups, goals, spikes, lava,
  hazards, platforms, ground, floating_platforms, everything. Fields: sprite (from SPRITES), tint (hex recolor),
  top_tint (only the grass / lava surface), body_tint (only the dirt), scale (1 = normal), scale_x (width), scale_y (height),
  alpha (0.4 = see-through), flip_y (upside down), glow (glow/outline color), effects: pulse, spin, wobble, bob, flicker,
  blink, rainbow, sparkle, trail, fade_far (faint until the player is near); ["none"] clears. reset: true = default look.
- set_scene {{fields}}: sky, sky_bottom (gradient), scenery (false hides hills/clouds), scenery_tint, overlay + overlay_alpha
  (color wash 0-0.8: night, sunset, underwater, spooky), weather: rain, snow, leaves, stars, bubbles, embers, fog, clouds,
  confetti (replaces the list), weather_color, filter: grayscale, sepia, negative, vintage, night_vision, hue_shift (-180..180),
  saturation (-1 gray..1 vivid), brightness (0.3-1.7), pixelate (0-8), zoom (1-2), reset.
- add_reaction {{event, effect, color, size}}: whenever event happens (jump, land, step, hurt, die, coin, powerup, stomp,
  enemy_defeated, win) play effect (shake, flash, sparkles, confetti, burst, ring, zoom_bump, spin, squash, blink,
  mark = footprint). spin/squash/blink/mark act on whoever caused the event.
- remove_reaction {{event or all, effect or all}}
- unsupported {{reason}}: ONLY for what no op can do.
SPRITES: {", ".join(SPRITE_NAMES)}
REGIONS: start, middle, end, a platform id; while playing also near_player, ahead.

RULES
- Do ONLY what is asked. Most commands are ONE op. A set_look sets only the fields the command names.
- Write "plan" first. Each op starts with "asked": the command's words that op carries out.
- "me", "my", "I" = the player: set_look target player. "when I/you <do something>" = add_reaction for that event.
- Looks (color, size, sprite, glow, see-through, effects, sky, weather, filters) use ONLY look ops: never add, remove or
  reshape objects or change physics for them.
- Colors are hex. Grass = top_tint, dirt = body_tint (target platforms or ground). "each X a different color" = one set_look per id.
- Sizes: bigger 1.5, huge/giant 2.5, smaller 0.6, tiny 0.4; wider = scale_x 1.5; taller = scale_y 1.5.
- A theme (place, holiday, mood) = set_scene plus set_look on the groups that fit it.
- Level edits: modest ("a bit" = 1 tile/15%, "more" = 1-2 tiles/25%, "a lot" = 3 tiles/50%). Plural = one op per id (max 6 ops).
  Gap size only with widen_gap. While playing, "this/here/ahead/next/harder/easier" = things marked [ahead], never [behind the player].
- Never swap in a different thing (coins are not platforms). Physics only with set_physics. Use only ids from the summary.
Reply with ONLY JSON: {{"plan": "...", "ops": [...]}}"""

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
EXAMPLES = [  # must not match demo commands (see CLAUDE.md core principle). Short ones last: most commands are one op
    ("narrow the second gap a little, scatter three coins in the middle, and let me run a bit faster", None, {
        "plan": "Three requests: gap2 1 tile narrower, 3 coins in the middle, run speed about 15% higher.",
        "ops": [
            {"op": "widen_gap", "asked": "narrow the second gap a little", "gap_id": "gap2", "tiles": -1},
            {"op": "add_coins", "asked": "scatter three coins in the middle", "region": "middle", "count": 3},
            {"op": "set_physics", "asked": "let me run a bit faster", "key": "run_speed", "value": 230},
        ],
    }),
    ("put a small ledge in front of me, slow that enemy down and paint it teal", _EX_PLAYER, {
        "plan": "Three requests: ledge near the player; slow e1; teal is a look: tint on e1.",
        "ops": [
            {"op": "add_platform", "asked": "put a small ledge in front of me", "over": "near_player", "height": 2, "width": 2},
            {"op": "set_property", "asked": "slow that enemy down", "id": "e1", "key": "speed", "value": 40},
            {"op": "set_look", "asked": "paint it teal", "target": "e1", "tint": "#1fb5a8"},
        ],
    }),
    ("cozy autumn evening vibe, a ripple when I grab coins, and let me save my game", None, {
        "plan": "Evening = set_scene sky, warm wash and falling leaves; ring on coin; saving is unsupported.",
        "ops": [
            {"op": "set_scene", "asked": "cozy autumn evening vibe", "sky": "#ff9a5a", "sky_bottom": "#5b3a8a", "overlay": "#ff7a30", "overlay_alpha": 0.15, "weather": ["leaves"]},
            {"op": "add_reaction", "asked": "a ripple when I grab coins", "event": "coin", "effect": "ring", "color": "#ffd27a"},
            {"op": "unsupported", "asked": "let me save my game", "reason": "save the game"},
        ],
    }),
    ("squash that purple blob", _EX_PLAYER, {
        "plan": "One request: the purple blob is enemy e1, remove it. Nothing else.",
        "ops": [{"op": "remove", "asked": "squash that purple blob", "id": "e1"}],
    }),
    ("drop me something to jump twice in the air", _EX_PLAYER, {
        "plan": "One request: a double_jump powerup (an object to collect) near the player. Not a look change.",
        "ops": [{"op": "add_pickup", "asked": "drop me something to jump twice", "kind": "double_jump", "region": "near_player", "count": 1}],
    }),
    ("make me see-through", _EX_PLAYER, {
        "plan": "One request: see-through is the player's alpha. No other look fields, no physics.",
        "ops": [{"op": "set_look", "asked": "make me see-through", "target": "player", "alpha": 0.4}],
    }),
    ("make the flag bob", None, {
        "plan": "One request: the bob effect on the goal. Only effects, no tint.",
        "ops": [{"op": "set_look", "asked": "make the flag bob", "target": "goal", "effects": ["bob"]}],
    }),
]


def intent_messages(level: dict, command: str, player: dict | None = None) -> list[dict]:
    """System prompt, few-shot turns, then the real command. The example level summary is shown once (first example);
    later examples are command -> reply only, which keeps the prompt about half the size."""
    msgs = [{"role": "system", "content": INTENT_SYSTEM}]
    for n, (cmd, pl, patch) in enumerate(EXAMPLES):
        c = f"LEVEL SUMMARY:\n{summary_text(_EX_LEVEL, _EX_PLAYER)}\n\nCOMMAND: {cmd}" if n == 0 else f"COMMAND: {cmd}"
        msgs.append({"role": "user", "content": c})
        msgs.append({"role": "assistant", "content": json.dumps(patch, separators=(",", ":"))})
    msgs.append({"role": "user", "content": f"LEVEL SUMMARY:\n{summary_text(level, player)}\n\nCOMMAND: {command}"})
    return msgs


def retry_message(errors: list[str]) -> dict:
    lines = "\n".join(f"- {e}" for e in errors)
    return {"role": "user", "content": f"Some of those operations could not be applied:\n{lines}\n\n"
                                       "Return the whole corrected JSON object (all ops, fixed as described), nothing else."}
