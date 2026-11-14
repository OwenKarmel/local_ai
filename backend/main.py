"""FastAPI app: serves the frontend, holds level versions in memory, runs commands through the model.

Endpoint shapes are the interface contracts in plan.md. Endpoints marked STUB return canned responses.
With STUB_COMMANDS=1, /api/command also returns canned keyword responses (no model server needed).
"""
import io
import json
import logging
import math
import struct
import threading
import time
import wave
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config
from .pipeline import run_command
from .schema import Level
from .stub_commands import run_stub

log = logging.getLogger("api")

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


HISTORY_DIR = ROOT / "backend" / "data" / "versions"  # gitignored; one JSON per version, for debugging
lock = threading.Lock()  # one edit at a time


def _push(level: Level, label: str, extra: dict | None = None) -> int:
    _counter[0] += 1
    versions.append({"version": _counter[0], "label": label, "time": time.strftime("%H:%M:%S"), "level": level})
    try:
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        (HISTORY_DIR / f"v{_counter[0]:03d}.json").write_text(json.dumps({"label": label, **(extra or {}), "level": level.model_dump()}, indent=1))
    except OSError:
        pass
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
    with lock:
        _push(_sample(), "reset to sample")
        return _current().model_dump()


@app.get("/api/history")
def history():
    return {"current": versions[-1]["version"],
            "versions": [{"version": v["version"], "label": v["label"], "time": v["time"]} for v in versions]}


@app.post("/api/undo")
def undo():
    with lock:
        ok = len(versions) > 1
        if ok:
            versions.pop()
        return {"ok": ok, "version": versions[-1]["version"], "level": _current().model_dump()}


# ---------- POST /api/command ----------
class PlayerIn(BaseModel):
    x: int                 # tile containing the player's center
    y: int
    has_double_jump: bool = False


class CommandIn(BaseModel):
    text: str
    source: Literal["typed", "voice"] = "typed"
    speaker: Optional[str] = None
    player: Optional[PlayerIn] = None  # null when not playing


class LogStep(BaseModel):
    step: Literal["route", "model", "convert", "check"]
    model: Optional[str]   # null for steps that don't call a model
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


@app.post("/api/command", response_model=CommandOut)
def command(cmd: CommandIn):
    text = cmd.text.strip()
    player = cmd.player.model_dump() if cmd.player else None
    with lock:
        level = _current()
        if not text:
            r = {"ok": False, "status": "error", "route": "level", "model": "", "latency_ms": 0, "patch": [],
                 "level": level.model_dump(), "spoken": "I didn't catch that.", "reason": "Empty command.", "log": []}
        elif config.STUB_COMMANDS:
            r = run_stub(level, text, player)
        else:
            r = run_command(level, text, config.CODE_MODEL, player)
        version = versions[-1]["version"]
        if r["status"] == "applied":
            version = _push(Level.model_validate(r["level"]), f"[{cmd.source}] {text}",
                            {"command": cmd.model_dump(), "patch": r["patch"], "log": r["log"]})
        log.info("command=%r status=%s route=%s model=%s latency_ms=%s ops=%d", text, r["status"], r["route"], r["model"],
                 r["latency_ms"], len(r["patch"]))
        return CommandOut(version=version, **r)


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
    return LabelOut(label="platform", confidence=0.87, model="stub-Ternary-Bonsai-2-4B-mlx-2bit", latency_ms=200)


# Must be last: serves index.html, game.js, mechanics.js, vendor/
app.mount("/", StaticFiles(directory=ROOT / "frontend", html=True), name="frontend")
