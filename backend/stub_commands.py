"""STUB_COMMANDS=1: canned /api/command responses by keyword, so the frontend works without a model server.

Same response shape as the real pipeline. Keywords (checked in order): "impossible"/"10 tiles" (refused),
"gravity", "fireball", "remove", "faster", "gap", "enemy"; anything else -> error.
"""
import time

from .patcher import PatchError, apply_low_level
from .schema import Entity, Level

STUB_FAST = "stub-Ternary-Bonsai-2-4B-mlx-2bit"
STUB_LEVEL = "stub-Ternary-Bonsai-2-4B-mlx-2bit"
_ENEMY_SPOTS = [8, 19, 26, 36]  # x tiles on the sample level's ground (y = 12)


def _plan(text: str, level: Level, player: dict | None) -> dict:
    t = text.lower()
    enemies = [e for e in level.entities if e.type == "enemy"]
    if "impossible" in t or "10 tiles" in t:
        return {"route": "level", "status": "refused", "ops": [],
                "spoken": "Can't do that: the gap would be 10 tiles and you can jump 5.",
                "reason": "gap1 would be 10 tiles wide; the longest jump with current physics is 5 tiles, so the goal would be unreachable."}
    if "gravity" in t:
        return {"route": "fast", "ops": [{"op": "set_physics", "key": "gravity", "value": max(400.0, level.physics.gravity - 300)}],
                "spoken": "Gravity lowered."}
    if "fireball" in t:
        settings = {"enabled": True, "key": "F", "speed": 420, "cooldown_ms": 400, "bounces": 2, "kills": True}
        return {"route": "fast", "ops": [{"op": "set_ability", "ability": "fireball", "settings": settings}],
                "spoken": "Fireballs are on. Press F to shoot."}
    if "remove" in t:
        if not enemies:
            return {"route": "level", "status": "refused", "ops": [], "spoken": "There are no enemies left to remove.", "reason": "The level has no enemies."}
        return {"route": "level", "ops": [{"op": "remove_entity", "id": enemies[0].id}], "spoken": "Removed an enemy."}
    if "faster" in t:
        if not enemies:
            return {"route": "level", "status": "refused", "ops": [], "spoken": "There are no enemies to speed up.", "reason": "The level has no enemies."}
        ops = [{"op": "update_entity", "id": e.id, "changes": {"props": {"speed": int(e.props.get("speed", 60)) + 40}}} for e in enemies]
        return {"route": "level", "ops": ops, "spoken": "The enemies are faster now."}
    if "gap" in t:
        g2 = next((e for e in level.entities if e.id == "ground2"), None)
        if g2 is None or g2.w <= 4:
            return {"route": "level", "status": "refused", "ops": [], "spoken": "That gap can't get any wider.", "reason": "ground2 is already at its minimum width."}
        return {"route": "level", "ops": [{"op": "update_entity", "id": "ground2", "changes": {"x": g2.x + 1, "w": g2.w - 1}}],
                "spoken": "The first gap is one tile wider."}
    if "enemy" in t:
        n = len([e for e in level.entities if e.id.startswith("enemy_stub")])
        x = min(level.width - 1, player["x"] + 3) if player else _ENEMY_SPOTS[n % len(_ENEMY_SPOTS)]
        ent = Entity(id=f"enemy_stub{n + 1}", type="enemy", x=x, y=12, behaviors=["patrol"], props={"speed": 60, "range": 2}).model_dump()
        return {"route": "level", "ops": [{"op": "add_entity", "entity": ent}], "spoken": "Added an enemy up ahead."}
    return {"route": "level", "status": "error", "ops": [], "spoken": "Sorry, I couldn't do that.",
            "reason": "(stub) No canned response for this text. Keywords: gravity, fireball, enemy, remove, faster, gap, impossible, 10 tiles."}


def run_stub(level: Level, text: str, player: dict | None = None) -> dict:
    t0 = time.perf_counter()
    plan = _plan(text, level, player)
    route = plan["route"]
    model = STUB_FAST if route == "fast" else STUB_LEVEL
    time.sleep(0.6 if route == "fast" else 2.0)  # stand-in for model time so "thinking" UI can be tested
    status, new_level, patch = plan.get("status", "applied"), level, plan["ops"]
    if status == "applied":
        try:
            ed = apply_low_level(level, plan["ops"], player)
            new_level, patch = ed.result(), ed.diff()
        except PatchError as e:
            status, patch, plan["reason"] = "error", [], str(e)
    ms = int((time.perf_counter() - t0) * 1000)
    steps = [
        {"step": "route", "model": model, "latency_ms": 40, "errors": [], "repairs": []},
        {"step": "model", "model": model, "latency_ms": max(0, ms - 60), "errors": [], "repairs": []},
        {"step": "convert", "model": None, "latency_ms": 5, "errors": [], "repairs": []},
        {"step": "check", "model": None, "latency_ms": 15, "errors": [plan["reason"]] if status == "refused" else [], "repairs": []},
    ]
    return {"ok": status == "applied", "status": status, "route": route, "model": model, "latency_ms": ms,
            "patch": patch if status == "applied" else [], "level": new_level.model_dump(), "spoken": plan["spoken"],
            "reason": plan.get("reason"), "log": steps}
