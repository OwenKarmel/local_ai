"""FastAPI app: serves the frontend and holds level versions in memory.

Endpoints marked STUB return canned responses (no model calls) in the exact shapes of the
interface contracts in plan.md, so the frontend can be built before the real backend exists.
"""
import io
import math
import struct
import time
import wave
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config
from .schema import Entity, Level

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "backend" / "levels" / "sample.json"

app = FastAPI(title="Voice game copilot (name TBD)")


def _sample() -> Level:
    return Level.model_validate_json(SAMPLE.read_text())


# In-memory version stack. Version numbers are never reused, even after undo.
versions: list[dict] = [{"version": 1, "label": "sample level", "time": time.strftime("%H:%M:%S"), "level": _sample()}]
_counter = [1]


def _current() -> Level:
    return versions[-1]["level"]


def _push(level: Level, label: str) -> int:
    _counter[0] += 1
    versions.append({"version": _counter[0], "label": label, "time": time.strftime("%H:%M:%S"), "level": level})
    return _counter[0]


@app.get("/api/health")
def health():
    return {"ok": True, "code_model": config.CODE_MODEL, "fast_model": config.FAST_MODEL,
            "bonsai_base_url": config.BONSAI_BASE_URL, "fast_base_url": config.FAST_BASE_URL,
            "argmax_url": config.ARGMAX_URL}


@app.get("/api/level")
def get_level():
    return _current().model_dump()


@app.post("/api/level/reset")
def reset_level():
    _push(_sample(), "reset to sample")
    return _current().model_dump()


@app.get("/api/history")
def history():
    # STUB: replaced by A1 (same shape; real history comes with the real command pipeline)
    return {"current": versions[-1]["version"],
            "versions": [{"version": v["version"], "label": v["label"], "time": v["time"]} for v in versions]}


@app.post("/api/undo")
def undo():
    # STUB: replaced by A1 (same shape). Works for real against the stub's version stack.
    if len(versions) <= 1:
        return {"ok": False, "version": versions[-1]["version"], "message": "Nothing to undo."}
    gone = versions.pop()
    return {"ok": True, "version": versions[-1]["version"], "message": f"Undid: {gone['label']}"}


# ---------- POST /api/command ----------
class CommandIn(BaseModel):
    text: str
    source: Literal["typed", "voice"] = "typed"
    speaker: Optional[str] = None


class LogStep(BaseModel):
    step: str            # "route" | "model" | "convert" | "check"
    model: Optional[str]  # null for steps that don't call a model
    latency_ms: int
    errors: list[str] = []
    repairs: list[str] = []


class CommandOut(BaseModel):
    ok: bool
    status: Literal["applied", "refused", "error"]
    version: int
    route: Literal["fast", "level"]
    model: str
    latency_ms: int
    patch: list[dict]      # LowLevelOp[]; empty unless status == "applied"
    level: dict            # full Level after the change (unchanged if refused/error)
    spoken: str
    reason: Optional[str]  # null when applied
    log: list[LogStep]


STUB_FAST = "stub-Ternary-Bonsai-2-2B-mlx-2bit"
STUB_LEVEL = "stub-Ternary-Bonsai-2-9B-mlx-2bit"
_ENEMY_SPOTS = [8, 19, 26, 36]  # x tiles on the sample level's ground (y = 12)


def _stub_apply(level: Level, ops: list[dict]) -> Level:
    """Minimal LowLevelOp applier for the stub. No auto-fixes, no playability check."""
    d = level.model_dump()
    for op in ops:
        kind = op["op"]
        if kind == "set_physics":
            d["physics"][op["key"]] = op["value"]
        elif kind == "set_ability":
            d["abilities"][op["ability"]] = op["settings"]
        elif kind == "add_entity":
            d["entities"].append(op["entity"])
        elif kind == "remove_entity":
            d["entities"] = [e for e in d["entities"] if e["id"] != op["id"]]
        elif kind == "update_entity":
            ent = next(e for e in d["entities"] if e["id"] == op["id"])
            changes = dict(op["changes"])
            ent["props"].update(changes.pop("props", {}))
            ent.update(changes)
    return Level.model_validate(d)


def _stub_plan(text: str, level: Level) -> dict:
    """Canned plan keyed on keywords. Returns route, ops, spoken, and (for refusals/errors) status + reason."""
    t = text.lower()
    enemies = [e for e in level.entities if e.type == "enemy"]
    if "impossible" in t or "10 tiles" in t:
        return {"route": "level", "status": "refused", "ops": [],
                "spoken": "Can't do that: the gap would be 10 tiles and you can jump 5.",
                "reason": "gap1 would be 10 tiles wide; the longest jump with current physics is 5 tiles, so the goal would be unreachable."}
    if "gravity" in t:
        g = max(400, level.physics.gravity - 300)
        return {"route": "fast", "ops": [{"op": "set_physics", "key": "gravity", "value": g}], "spoken": "Gravity lowered."}
    if "fireball" in t:
        settings = {"enabled": True, "key": "F", "speed": 420, "cooldown_ms": 400, "bounces": 2, "kills": True}
        return {"route": "fast", "ops": [{"op": "set_ability", "ability": "fireball", "settings": settings}],
                "spoken": "Fireballs are on. Press F to shoot."}
    if "remove" in t:
        if not enemies:
            return {"route": "level", "status": "refused", "ops": [], "spoken": "There are no enemies left to remove.",
                    "reason": "The level has no enemies."}
        return {"route": "level", "ops": [{"op": "remove_entity", "id": enemies[0].id}], "spoken": "Removed an enemy."}
    if "faster" in t:
        if not enemies:
            return {"route": "level", "status": "refused", "ops": [], "spoken": "There are no enemies to speed up.",
                    "reason": "The level has no enemies."}
        ops = [{"op": "update_entity", "id": e.id, "changes": {"props": {"speed": int(e.props.get("speed", 60)) + 40}}} for e in enemies]
        return {"route": "level", "ops": ops, "spoken": "The enemies are faster now."}
    if "gap" in t:
        g2 = next((e for e in level.entities if e.id == "ground2"), None)
        if g2 is None or g2.w <= 4:
            return {"route": "level", "status": "refused", "ops": [], "spoken": "That gap can't get any wider.",
                    "reason": "ground2 is already at its minimum width."}
        return {"route": "level", "ops": [{"op": "update_entity", "id": "ground2", "changes": {"x": g2.x + 1, "w": g2.w - 1}}],
                "spoken": "The first gap is one tile wider."}
    if "enemy" in t:
        n = len([e for e in level.entities if e.id.startswith("enemy_stub")])
        ent = Entity(id=f"enemy_stub{n + 1}", type="enemy", x=_ENEMY_SPOTS[n % len(_ENEMY_SPOTS)], y=12,
                     behaviors=["patrol"], props={"speed": 60, "range": 2}).model_dump()
        return {"route": "level", "ops": [{"op": "add_entity", "entity": ent}], "spoken": "Added an enemy up ahead."}
    return {"route": "level", "status": "error", "ops": [], "spoken": "Sorry, I couldn't do that.",
            "reason": "(stub) No canned response for this text. Keywords: gravity, fireball, enemy, remove, faster, gap, impossible, 10 tiles."}


@app.post("/api/command", response_model=CommandOut)
def command(cmd: CommandIn):
    # STUB: replaced by A1 (pipeline + contract), then A4 (routing) and A5 (real refusals)
    t0 = time.perf_counter()
    level = _current()
    plan = _stub_plan(cmd.text, level)
    route = plan["route"]
    model = STUB_FAST if route == "fast" else STUB_LEVEL
    time.sleep(0.6 if route == "fast" else 2.0)  # stand-in for model time so "thinking" UI can be tested
    status = plan.get("status", "applied")
    version = versions[-1]["version"]
    if status == "applied":
        level = _stub_apply(level, plan["ops"])
        version = _push(level, f"[{cmd.source}] {cmd.text}")
    ms = int((time.perf_counter() - t0) * 1000)
    log = [
        LogStep(step="route", model=STUB_FAST, latency_ms=40),
        LogStep(step="model", model=model, latency_ms=ms - 60),
        LogStep(step="convert", model=None, latency_ms=5),
        LogStep(step="check", model=None, latency_ms=15, errors=[plan["reason"]] if status == "refused" else []),
    ]
    return CommandOut(ok=status == "applied", status=status, version=version, route=route, model=model, latency_ms=ms,
                      patch=plan["ops"], level=level.model_dump(), spoken=plan["spoken"], reason=plan.get("reason"), log=log)


# ---------- POST /api/transcribe ----------
class TranscribeOut(BaseModel):
    text: str
    latency_ms: int
    speaker: Optional[str] = None  # null until SpeakerKit chaos mode (O5); then "player" | "friend" | enrolled name


@app.post("/api/transcribe", response_model=TranscribeOut)
async def transcribe(audio: UploadFile = File(...)):
    # STUB: replaced by O1 (forward to Argmax WhisperKit at ARGMAX_URL); speaker filled in by O5
    await audio.read()
    return TranscribeOut(text="lower the gravity", latency_ms=450, speaker=None)


# ---------- POST /api/speak ----------
class SpeakIn(BaseModel):
    text: str
    style: Literal["normal", "refusal", "hype"] = "normal"


def _beep(freq: int, ms: int = 250, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        n = int(rate * ms / 1000)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * freq * i / rate))) for i in range(n)))
    return buf.getvalue()


@app.post("/api/speak")
def speak(req: SpeakIn):
    # STUB: replaced by O4 (Argmax TTSKit). Returns a short beep wav; pitch differs per style.
    return Response(content=_beep({"normal": 660, "refusal": 330, "hype": 880}[req.style]), media_type="audio/wav")


# ---------- Dropped features (canvas drawing + vision labeling). Kept until cleanup; see plan.md "Dropped". ----------
@app.post("/api/patch")
def apply_patch_direct(patch: dict):
    # STUB (dropped feature: canvas drawing). Not part of the current contracts.
    return {"ok": True, "version": versions[-1]["version"], "message": f"(stub) would apply {len(patch.get('ops', []))} ops"}


class BBoxTiles(BaseModel):
    x: int
    y: int
    w: int
    h: int


class LabelIn(BaseModel):
    image: str
    bbox_tiles: BBoxTiles


class LabelOut(BaseModel):
    label: Literal["platform", "spikes", "enemy", "coin", "double_jump", "goal", "player_spawn"]
    confidence: float
    model: str
    latency_ms: int


@app.post("/api/label", response_model=LabelOut)
def label(req: LabelIn):
    # STUB (dropped feature: vision labeling of sketches). Not part of the current contracts.
    return LabelOut(label="platform", confidence=0.87, model=STUB_FAST, latency_ms=200)


# Must be last: serves index.html, game.js, mechanics.js, vendor/
app.mount("/", StaticFiles(directory=ROOT / "frontend", html=True), name="frontend")
