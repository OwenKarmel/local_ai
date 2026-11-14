"""Prompts for the level-patch model. Keep examples in sync with schema.py."""
import json

PATCH_SYSTEM = """You edit levels for a 2D side-scrolling platformer. You never rewrite the whole level. You return a PATCH: a short list of operations.

LEVEL FORMAT (all units are tiles; x grows right, y grows DOWN; y=0 is the top row, y=height-1 is the bottom row)
- Each entity: {"id", "type", "x", "y", "w", "h", "behaviors", "props"}. (x,y) is the top-left tile; w,h are size in tiles.
- type is one of: platform, spikes, lava, enemy, coin, double_jump, goal.
- Ground is platforms along the bottom (y=13, h=2 in a 15-tall level). A GAP is empty space between two ground platforms. Things stand ON a platform when their y = platform.y - 1.
- Enemies normally have "behaviors": ["patrol"] and "props": {"speed": 60, "range": 3}.
- Everything must stay inside the level: x + w <= width, y + h <= height. ids must be unique.

KEEP IT PLAYABLE
- The player can jump across gaps of at most 5 tiles and up about 3 tiles. "Bigger"/"wider" means +1 or +2 tiles, never more than 5 total.
- Change only what the command asks for. Keep the player's start (left) and the goal (right) on solid ground.
- If you move or shrink a platform, also move anything standing on it (spikes, enemies, coins, goal) so nothing ends up floating over a gap.

OPERATIONS
- {"op": "add", "entity": {...full entity with a NEW unique id...}}
- {"op": "remove", "id": "..."}
- {"op": "move", "id": "...", "x": int, "y": int}            (new top-left position)
- {"op": "set", "id": "...", "key": "w"|"h"|"x"|"y"|"type"|"behaviors"|"props.<name>", "value": ...}
- {"op": "set_physics", "key": "gravity"|"jump_velocity"|"run_speed", "value": number}
Ops apply in order.

Reply with ONLY a JSON object: {"explanation": "<one short sentence>", "ops": [ ... ]}. No markdown, no extra text."""

# Few-shot examples on a tiny level so they don't leak ids from the real one.
_EX_LEVEL = {
    "width": 30, "height": 15,
    "physics": {"gravity": 1200, "jump_velocity": 560, "run_speed": 200},
    "spawn": {"x": 1, "y": 11},
    "entities": [
        {"id": "g1", "type": "platform", "x": 0, "y": 13, "w": 10, "h": 2},
        {"id": "g2", "type": "platform", "x": 12, "y": 13, "w": 18, "h": 2},
        {"id": "c1", "type": "coin", "x": 5, "y": 10},
        {"id": "goal", "type": "goal", "x": 28, "y": 11, "w": 1, "h": 2},
    ],
}
EXAMPLES = [
    ("add two enemies on the second ground section and make jumping a bit higher", {
        "explanation": "Two patrolling enemies on g2 and a higher jump.",
        "ops": [
            {"op": "add", "entity": {"id": "enemy_a1", "type": "enemy", "x": 16, "y": 12, "behaviors": ["patrol"], "props": {"speed": 60, "range": 3}}},
            {"op": "add", "entity": {"id": "enemy_a2", "type": "enemy", "x": 22, "y": 12, "behaviors": ["patrol"], "props": {"speed": 60, "range": 3}}},
            {"op": "set_physics", "key": "jump_velocity", "value": 640},
        ],
    }),
    ("make the gap wider", {
        "explanation": "Gap between g1 and g2 widened from 2 to 4 tiles by shrinking g1 and moving g2 right.",
        "ops": [
            {"op": "set", "id": "g1", "key": "w", "value": 9},
            {"op": "move", "id": "g2", "x": 13, "y": 13},
            {"op": "set", "id": "g2", "key": "w", "value": 17},
        ],
    }),
]


def level_for_prompt(level: dict) -> str:
    """Compact JSON, one entity per line: short but readable for a small model."""
    head = {k: level[k] for k in ("width", "height", "physics", "spawn")}
    lines = [json.dumps(head, separators=(",", ":"))[:-1] + ',"entities":[']
    lines += ["  " + json.dumps(e, separators=(",", ":")) + "," for e in level["entities"]]
    lines[-1] = lines[-1].rstrip(",")
    lines.append("]}")
    return "\n".join(lines)


def _strip(level: dict) -> dict:
    out = {k: v for k, v in level.items() if k not in ("name", "tile_size")}
    out["entities"] = [
        {k: v for k, v in e.items() if not (k in ("behaviors", "props") and not v) and not (k in ("w", "h") and v == 1)}
        for e in level["entities"]
    ]
    return out


def patch_messages(level: dict, command: str) -> list[dict]:
    msgs = [{"role": "system", "content": PATCH_SYSTEM}]
    for cmd, patch in EXAMPLES:
        msgs.append({"role": "user", "content": f"LEVEL:\n{level_for_prompt(_EX_LEVEL)}\n\nCOMMAND: {cmd}"})
        msgs.append({"role": "assistant", "content": json.dumps(patch)})
    msgs.append({"role": "user", "content": f"LEVEL:\n{level_for_prompt(_strip(level))}\n\nCOMMAND: {command}"})
    return msgs


def repair_message(errors: str) -> dict:
    return {"role": "user", "content": f"That patch was rejected:\n{errors}\n\nReturn a corrected patch as ONLY the JSON object."}
