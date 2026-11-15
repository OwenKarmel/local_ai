"""FastAPI app: serves the frontend, holds level versions in memory, runs commands through the model.

Endpoint shapes are the interface contracts in plan.md. Endpoints marked STUB return canned responses.
/api/command always calls the model server; there is no canned-response mode.
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
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, traces
from .pipeline import run_command
from .schema import Level
from .speech import SpeechError, transcribe as argmax_transcribe

log = logging.getLogger("api")

ROOT = Path(__file__).resolve().parent.parent
LEVEL_DIR = ROOT / "backend" / "levels"
STAGES = ["sample", "boss"]  # play order: beating a stage's goal moves on to the next one

app = FastAPI(title="Voice game copilot (name TBD)")


def _load(stage: int) -> Level:
    return Level.model_validate_json((LEVEL_DIR / f"{STAGES[stage]}.json").read_text())


# In-memory version stacks, one per stage. Commands, undo, history and reset act on the active stage.
# Version numbers are global and never reused, even after undo.
_counter = [0]
stacks: list[list[dict]] = []
active = [0]  # index into STAGES


def _version(level: Level, label: str) -> dict:
    _counter[0] += 1
    return {"version": _counter[0], "label": label, "time": time.strftime("%H:%M:%S"), "level": level}


for _i, _name in enumerate(STAGES):
    stacks.append([_version(_load(_i), f"{_name} level")])


def _stack() -> list[dict]:
    return stacks[active[0]]


def _current() -> Level:
    return _stack()[-1]["level"]


HISTORY_DIR = ROOT / "backend" / "data" / "versions"  # gitignored; one JSON per version, for debugging
lock = threading.Lock()  # one edit at a time


def _push(level: Level, label: str, extra: dict | None = None, stage: int | None = None) -> int:
    v = _version(level, label)
    stacks[active[0] if stage is None else stage].append(v)
    try:
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        (HISTORY_DIR / f"v{v['version']:03d}.json").write_text(
            json.dumps({"label": label, "stage": STAGES[active[0] if stage is None else stage], **(extra or {}),
                        "level": level.model_dump()}, indent=1))
    except OSError:
        pass
    return v["version"]


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
    """Resets the active stage to its level file."""
    with lock:
        _push(_load(active[0]), f"reset {STAGES[active[0]]}")
        return _current().model_dump()


def _stage_info() -> dict:
    return {"index": active[0], "count": len(STAGES), "names": [s["level"].name for s in (st[-1] for st in stacks)]}


@app.get("/api/stage")
def get_stage():
    return _stage_info()


class StageIn(BaseModel):
    index: int


@app.post("/api/stage")
def set_stage(req: StageIn):
    """Switch the active stage (e.g. after beating a level). Edits made to a stage are kept when you leave it."""
    with lock:
        ok = 0 <= req.index < len(STAGES)
        if ok:
            active[0] = req.index
        return {"ok": ok, **_stage_info(), "level": _current().model_dump()}


@app.get("/api/history")
def history():
    st = _stack()
    return {"current": st[-1]["version"], "stage": active[0],
            "versions": [{"version": v["version"], "label": v["label"], "time": v["time"]} for v in st]}


@app.post("/api/undo")
def undo():
    with lock:
        st = _stack()
        ok = len(st) > 1
        if ok:
            st.pop()
        return {"ok": ok, "version": st[-1]["version"], "level": _current().model_dump()}


# ---------- POST /api/command ----------
class PlayerIn(BaseModel):
    x: int                 # tile containing the player's center
    y: int
    has_double_jump: bool = False
    is_big: bool = False   # picked up a "grow" powerup


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
    stage: int             # index of the stage (level) this command edited; see /api/stage
    spoken: str
    reason: Optional[str]  # null when applied
    log: list[LogStep]
    trace_id: Optional[str] = None  # snapshot in backend/data/traces/; flag it with POST /api/traces/{id}/flag


@app.post("/api/command", response_model=CommandOut)
def command(cmd: CommandIn):
    text = cmd.text.strip()
    player = cmd.player.model_dump() if cmd.player else None
    with lock:
        level = _current()
        trace = traces.new_trace(text, cmd.source, player, STAGES[active[0]], _stack()[-1]["version"], level.model_dump())
        if not text:
            r = {"ok": False, "status": "error", "route": "level", "model": "", "latency_ms": 0, "patch": [],
                 "level": level.model_dump(), "spoken": "I didn't catch that.", "reason": "Empty command.", "log": []}
        else:
            try:
                r = run_command(level, text, config.CODE_MODEL, player, trace)
            except Exception as e:  # record harness crashes too, then let FastAPI return the 500
                trace["outcome"] = {"status": "crash", "reason": f"{type(e).__name__}: {e}"}
                traces.save(trace)
                raise
        version = _stack()[-1]["version"]
        if r["status"] == "applied":
            version = _push(Level.model_validate(r["level"]), f"[{cmd.source}] {text}",
                            {"command": cmd.model_dump(), "patch": r["patch"], "log": r["log"], "trace_id": trace["id"]})
        trace["version_after"] = version
        trace["outcome"] = trace.get("outcome") or {"status": r["status"], "spoken": r["spoken"], "reason": r["reason"]}
        traces.save(trace)
        log.info("command=%r status=%s route=%s model=%s latency_ms=%s ops=%d", text, r["status"], r["route"], r["model"],
                 r["latency_ms"], len(r["patch"]))
        return CommandOut(version=version, stage=active[0], trace_id=trace["id"], **r)


# ---------- traces (debugging the harness; see backend/traces.py) ----------
@app.get("/api/traces")
def list_traces(limit: int = 50, failures: bool = False):
    return {"traces": traces.recent(limit, failures)}


@app.get("/api/traces/{tid}")
def get_trace(tid: str):
    t = traces.load(tid)
    return t if t else JSONResponse({"detail": "no such trace"}, status_code=404)


class FlagIn(BaseModel):
    note: str = ""


@app.post("/api/traces/{tid}/flag")
def flag_trace(tid: str, req: FlagIn):
    t = traces.flag(tid, req.note.strip())
    return traces.summary(t) if t else JSONResponse({"detail": "no such trace"}, status_code=404)


# ---------- POST /api/transcribe ----------
class TranscribeOut(BaseModel):
    text: str
    latency_ms: int
    speaker: Optional[str] = None  # null until SpeakerKit chaos mode (O5); then "player" | "friend" | enrolled name


@app.post("/api/transcribe", response_model=TranscribeOut)
async def transcribe(audio: UploadFile = File(...)):
    """Forwards to the local Argmax server (ARGMAX_URL). STUB_SPEECH=1 returns fixed text (no Argmax needed).
    On failure: HTTP 503 with {"detail": "..."}. speaker stays null until O5 (SpeakerKit)."""
    data = await audio.read()
    if config.STUB_SPEECH:
        return TranscribeOut(text="lower the gravity", latency_ms=450, speaker=None)
    try:
        r = await run_in_threadpool(argmax_transcribe, data, audio.filename, audio.content_type)
    except SpeechError as e:
        log.warning("transcribe failed: %s", e)
        return JSONResponse(status_code=503, content={"detail": str(e)})
    return TranscribeOut(text=r["text"], latency_ms=r["latency_ms"], speaker=None)


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
    return {"ok": True, "version": _stack()[-1]["version"], "message": f"(stub) would apply {len(patch.get('ops', []))} ops"}


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
