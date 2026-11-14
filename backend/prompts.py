"""Prompts for the level-edit model (intent format). Examples are built from summary_text so they always match."""
import json

from .summary import summary_text

INTENT_SYSTEM = """You edit levels for a 2D side-scrolling platformer by choosing high-level edit operations.
You never write coordinates: the game engine works out exact positions and keeps everything inside the level.

You get a LEVEL SUMMARY (ground platforms, gaps, floating platforms, objects, each with an id) and a COMMAND.

OPERATIONS
- {"op":"widen_gap","gap_id":"gap1","tiles":2}  make a gap wider (negative = narrower; minus its width closes it)
- {"op":"shrink_platform","id":"plat1","tiles":1,"side":"both"}  make a platform narrower (negative = wider). side: left, right, both
- {"op":"add_enemy","region":"end","count":2,"speed":60}  region: start, middle, end, or a platform id. Normal speed 60, fast 100+
- {"op":"add_hazard_near","platform_id":"ground2","kind":"spikes","width":1,"side":"auto"}  spikes or lava on top of that platform, near an edge
- {"op":"add_coins","region":"middle","count":3}
- {"op":"remove","id":"enemy2"}
- {"op":"set_property","id":"enemy1","key":"speed","value":90}  enemy keys: speed, range (patrol distance in tiles)
- {"op":"set_physics","key":"jump_velocity","value":640}  keys: gravity, jump_velocity, run_speed

RULES
- Use only ids that appear in the summary.
- Do what the command asks with a sensible, modest change: "a bit" = 1 tile or about 15%; "bigger"/"more" = 1-2 tiles or about 30%; "a lot" = 3 tiles or about 60%.
- Plural ("the gaps", "the enemies") means one op for EACH matching id in the summary.
- "Near the end/start/middle" means that region.

Reply with ONLY JSON: {"explanation": "<one short sentence>", "ops": [ ... ]}"""

_EX_LEVEL = {
    "name": "example", "tile_size": 32, "width": 30, "height": 15,
    "physics": {"gravity": 1200, "jump_velocity": 560, "run_speed": 200},
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
EXAMPLES = [
    ("make the gaps a lot bigger and put an enemy near the end", {
        "explanation": "Both gaps widened by 3 tiles and one enemy added in the end region.",
        "ops": [
            {"op": "widen_gap", "gap_id": "gap1", "tiles": 3},
            {"op": "widen_gap", "gap_id": "gap2", "tiles": 3},
            {"op": "add_enemy", "region": "end", "count": 1, "speed": 60},
        ],
    }),
    ("make the enemies faster, get rid of the coin, and add spikes on the floating platform", {
        "explanation": "Enemy sped up, coin removed, spikes added on p1.",
        "ops": [
            {"op": "set_property", "id": "e1", "key": "speed", "value": 90},
            {"op": "remove", "id": "c1"},
            {"op": "add_hazard_near", "platform_id": "p1", "kind": "spikes", "width": 1, "side": "auto"},
        ],
    }),
]


def intent_messages(level: dict, command: str) -> list[dict]:
    msgs = [{"role": "system", "content": INTENT_SYSTEM}]
    for cmd, patch in EXAMPLES:
        msgs.append({"role": "user", "content": f"LEVEL SUMMARY:\n{summary_text(_EX_LEVEL)}\n\nCOMMAND: {cmd}"})
        msgs.append({"role": "assistant", "content": json.dumps(patch)})
    msgs.append({"role": "user", "content": f"LEVEL SUMMARY:\n{summary_text(level)}\n\nCOMMAND: {command}"})
    return msgs


def retry_message(errors: list[str]) -> dict:
    lines = "\n".join(f"- {e}" for e in errors)
    return {"role": "user", "content": f"Some of those operations could not be applied:\n{lines}\n\n"
                                       "Return the whole corrected JSON object (all ops, fixed), nothing else."}
