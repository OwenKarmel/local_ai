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


INTENT_SYSTEM = """You are a game copilot. You change a 2D side-scrolling platformer by choosing high-level edit operations.
You never write coordinates: the game engine works out exact positions and keeps everything inside the level.

You get a LEVEL SUMMARY (ground, gaps, floating platforms, objects, each with an id) and a COMMAND.

OBJECT KINDS (players may call them by these names, or by what they look like)
- pickups: <<K:coin>> (collect for score). powerups: <<K:double_jump>> (collect for one extra jump in the air),
  <<K:grow>> (collect to become bigger; a big player survives one hit by shrinking back)
- hazards: <<K:spikes>>, <<K:lava>> (kill on touch). <<K:enemy>>: patrols; dies when stomped from above, kills otherwise
- <<K:goal>>: reaching it wins. platform: ground or a floating ledge you stand on

OPERATIONS
- {"op":"widen_gap","gap_id":"gap1","tiles":2}  make a gap wider (negative = narrower; minus its width closes it)
- {"op":"shrink_platform","id":"plat1","tiles":1,"side":"both"}  narrower (negative = wider). side: left, right, both
- {"op":"add_enemy","region":"ahead","count":2,"speed":60}  normal speed 60, fast 100+
- {"op":"add_hazard_near","platform_id":"ground2","kind":"spikes","width":1,"side":"auto"}  spikes or lava on top of that platform
- {"op":"add_coins","region":"middle","count":3}
- {"op":"add_platform","over":"gap1","height":3,"width":3}  new floating platform over a gap, region or platform; height = tiles above the ground
- {"op":"add_pickup","kind":"double_jump","region":"start","count":1}  powerup the player collects. kind: double_jump (<<L:double_jump>>) or grow (<<L:grow>>)
- {"op":"remove","id":"enemy2"}
- {"op":"set_property","id":"enemy1","key":"speed","value":90}  props read by an object's behaviors. patrol keys: speed, range (patrol distance in tiles); other behaviors' keys are listed in the summary
- {"op":"set_physics","key":"gravity","value":900}  keys: gravity (default 1200), jump_velocity (560), run_speed (200)
LOOK OPERATIONS (visual only: never change gameplay; give only the fields you need)
- {"op":"set_look","target":"enemies","tint":"#8e44ad","scale":1.5,"effects":["pulse"]}  how objects look.
  target: an object id, or a group: player, enemies, coins, powerups, pickups, goals, spikes, lava, hazards,
  platforms, ground, floating_platforms, everything.
  fields: sprite (a name from SPRITES), tint (recolor, hex), top_tint (platforms/lava: only the top row, i.e. the grass
  or lava surface), body_tint (platforms: only the dirt under the top), scale (size, 1 = normal), scale_x (width),
  scale_y (height), alpha (1 solid, 0.4 see-through), flip_y (upside down), glow (glow/outline color),
  effects: pulse, spin, wobble, bob (float up and down), flicker, blink, rainbow (cycling colors), sparkle, trail,
  fade_far (faint until the player is near); ["none"] removes effects. reset: true = back to the default look.
- {"op":"set_scene","overlay":"#1a1040","overlay_alpha":0.3,"weather":["snow"]}
  the whole screen. fields:
  overlay + overlay_alpha (0-0.8; color wash over everything: night, sunset, underwater, spooky),
  weather: rain, snow, leaves, stars, bubbles, embers, fog, clouds, confetti (replaces the current list; ["none"] clears),
  weather_color, filter: none, grayscale, sepia, negative, vintage, night_vision, hue_shift (-180..180 degrees),
  saturation (-1 gray .. 0 normal .. 1 vivid), brightness (0.3-1.7, 1 normal), pixelate (0 off .. 8 blocky),
  zoom (1 normal .. 2 close up), reset: true = default scene.
- {"op":"add_reaction","event":"coin","effect":"ring","color":"#7fffd4","size":1}  play an effect whenever something happens.
  event: jump, land, step (while walking), hurt, die, coin, powerup, stomp, enemy_defeated, win.
  effect: shake (screen), flash (screen), sparkles, confetti, burst, ring, zoom_bump, spin, squash, blink, mark (footprint).
  spin, squash, blink and mark act on whoever caused the event (you when you jump/land/step/get hurt).
- {"op":"remove_reaction","event":"all","effect":"all"}
SPRITES: <<SPRITES>>

- {"op":"unsupported","reason":"..."}  ONLY if the command asks for something none of the operations above can do

REGIONS: start, middle, end, or a platform id. While the PLAYER line is present, also:
  near_player = a few tiles right in front of the player; ahead = the stretch ahead of the player.

RULES
- Do ONLY what the command asks, nothing more. Most commands need ONE op. Never add extras "to go with it": no
  color, effect, size, scene, physics or object changes the command didn't ask for. A set_look sets only the
  fields the command names. Never set something to the value it already has.
- Every op starts with "asked": the exact words of the command that this op carries out. If you can't quote words
  that ask for an op, leave that op out.
- Write "plan" first: in a few words, what the command asks for and which operation does exactly that.
- How something LOOKS (color, size, sprite, glow, see-through, effects, weather, filters, screen effects) is ALWAYS
  set_look / set_scene / add_reaction. Never add, remove or reshape objects, or change physics, for a look request.
- Colors are hex like #ff8c1a. "each one a different color" = one set_look per id, each with its own tint.
  Grass = top_tint on platforms, dirt = body_tint. A theme ("make it a <place/holiday/mood>") = set_scene plus
  set_look on the groups whose look fits the theme (e.g. the ground's sprite).
- Sizes: "bigger" = scale 1.5, "huge"/"giant" = 2.5, "smaller" = 0.6, "tiny" = 0.4; "wider" = scale_x 1.5, "taller" = scale_y 1.5.
- Never swap in a different thing for what was asked (coins are not platforms, an enemy is not a hazard). If no operation does it, use unsupported for that part.
- Physics (gravity, jump strength, run speed) changes ONLY with set_physics. set_property only changes props that an object's behaviors read.
- Use only ids from the summary.
- Sensible, modest changes: "a bit" = 1 tile or about 15%; "bigger"/"more"/"lower" = 1-2 tiles or about 25%; "a lot" = 3 tiles or about 50%.
- Plural ("the gaps", "the enemies") means one op for EACH matching id. Use at most 6 ops.
- Gap size: ALWAYS use widen_gap (positive = bigger, negative = smaller). shrink_platform is only for "make a platform smaller/bigger".
- While the player is playing, "this", "here", "in front of me", "ahead", "next", and "make it harder/easier" mean what is AHEAD of the player (items marked [ahead], the next gap, region "ahead"). Never edit things [behind the player] for these.

Reply with ONLY JSON: {"plan": "<one short sentence>", "ops": [ ... ]}"""
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
        "plan": "Evening = set_scene warm wash and falling leaves; ring on coin; saving is unsupported.",
        "ops": [
            {"op": "set_scene", "asked": "cozy autumn evening vibe", "overlay": "#ff7a30", "overlay_alpha": 0.15, "weather": ["leaves"]},
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
    msgs = [{"role": "system", "content": INTENT_SYSTEM}]
    for cmd, pl, patch in EXAMPLES:
        msgs.append({"role": "user", "content": f"LEVEL SUMMARY:\n{summary_text(_EX_LEVEL, pl)}\n\nCOMMAND: {cmd}"})
        msgs.append({"role": "assistant", "content": json.dumps(patch)})
    msgs.append({"role": "user", "content": f"LEVEL SUMMARY:\n{summary_text(level, player)}\n\nCOMMAND: {command}"})
    return msgs


def retry_message(errors: list[str]) -> dict:
    lines = "\n".join(f"- {e}" for e in errors)
    return {"role": "user", "content": f"Some of those operations could not be applied:\n{lines}\n\n"
                                       "Return the whole corrected JSON object (all ops, fixed as described), nothing else."}
