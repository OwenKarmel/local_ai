"""Prompts for the level-edit model (intent format). Examples are built from summary_text so they always match."""
import json

from .summary import summary_text

INTENT_SYSTEM = """You are a game copilot. You change a 2D side-scrolling platformer by choosing high-level edit operations.
You never write coordinates: the game engine works out exact positions and keeps everything inside the level.

You get a LEVEL SUMMARY (ground, gaps, floating platforms, objects, each with an id) and a COMMAND.

OPERATIONS
- {"op":"widen_gap","gap_id":"gap1","tiles":2}  make a gap wider (negative = narrower; minus its width closes it)
- {"op":"shrink_platform","id":"plat1","tiles":1,"side":"both"}  narrower (negative = wider). side: left, right, both
- {"op":"add_enemy","region":"ahead","count":2,"speed":60}  normal speed 60, fast 100+
- {"op":"add_hazard_near","platform_id":"ground2","kind":"spikes","width":1,"side":"auto"}  spikes or lava on top of that platform
- {"op":"add_coins","region":"middle","count":3}
- {"op":"remove","id":"enemy2"}
- {"op":"set_property","id":"enemy1","key":"speed","value":90}  enemy keys: speed, range (patrol distance in tiles)
- {"op":"set_physics","key":"gravity","value":900}  keys: gravity (default 1200), jump_velocity (560), run_speed (200)
- {"op":"unsupported","reason":"..."}  ONLY if the command asks for something none of the operations above can do

REGIONS: start, middle, end, or a platform id. While the PLAYER line is present, also:
  near_player = a few tiles right in front of the player; ahead = the stretch ahead of the player.

RULES
- Use only ids from the summary.
- Sensible, modest changes: "a bit" = 1 tile or about 15%; "bigger"/"more"/"lower" = 1-2 tiles or about 25%; "a lot" = 3 tiles or about 50%.
- Plural ("the gaps", "the enemies") means one op for EACH matching id. Use at most 6 ops.
- Gap size: ALWAYS use widen_gap (positive = bigger, negative = smaller). shrink_platform is only for "make a platform smaller/bigger".
- While the player is playing, "this", "here", "in front of me", "ahead", "next", and "make it harder/easier" mean what is AHEAD of the player (items marked [ahead], the next gap, region "ahead"). Never edit things [behind the player] for these.

Reply with ONLY JSON: {"explanation": "<one short sentence>", "ops": [ ... ]}"""

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
    ("narrow the second gap a little and scatter three coins in the middle", None, {
        "explanation": "gap2 narrowed by 1 tile and three coins added in the middle.",
        "ops": [
            {"op": "widen_gap", "gap_id": "gap2", "tiles": -1},
            {"op": "add_coins", "region": "middle", "count": 3},
        ],
    }),
    ("put a couple of coins in front of me, slow that enemy down, and make me sparkle", _EX_PLAYER, {
        "explanation": "Two coins ahead of the player, enemy slowed. Sparkling isn't something these ops can do.",
        "ops": [
            {"op": "add_coins", "region": "near_player", "count": 2},
            {"op": "set_property", "id": "e1", "key": "speed", "value": 40},
            {"op": "unsupported", "reason": "make the player sparkle"},
        ],
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
