"""FastAPI app: serves the frontend and holds the current level in memory.

Endpoints marked STUB return realistic fake responses (no model calls) matching the interface
contracts in plan.md, so the frontend can be built before the real versions exist.
"""
import time
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, File, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config
from .schema import Level

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "backend" / "levels" / "sample.json"

app = FastAPI(title="Sketch2Game")
state = {"level": Level.model_validate_json(SAMPLE.read_text()), "version": 1}


@app.get("/api/health")
def health():
    return {"ok": True, "code_model": config.CODE_MODEL, "fast_model": config.FAST_MODEL,
            "bonsai_base_url": config.BONSAI_BASE_URL, "argmax_url": config.ARGMAX_URL}


@app.get("/api/level")
def get_level():
    return state["level"].model_dump()


@app.post("/api/level/reset")
def reset_level():
    state["level"] = Level.model_validate_json(SAMPLE.read_text())
    return state["level"].model_dump()


# ---------- Interface contracts (see plan.md). ----------

class CommandIn(BaseModel):
    text: str
    source: Literal["typed", "voice"] = "typed"


class LogEntry(BaseModel):
    model: str
    latency_ms: int
    errors: list[str] = []
    repairs: list[str] = []


class CommandOut(BaseModel):
    ok: bool
    version: int
    patch: Optional[dict]  # {"explanation": str, "ops": [...]} — see CLAUDE.md patch format
    log: list[LogEntry]
    message: str


@app.post("/api/command", response_model=CommandOut)
def command(cmd: CommandIn):
    # STUB: replaced by "patches + undo" (feat/patches, Ashwin)
    time.sleep(0.3)
    return CommandOut(
        ok=True,
        version=state["version"],
        patch={"explanation": f"(stub) received: {cmd.text}", "ops": []},
        log=[LogEntry(model="stub-Ternary-Bonsai-2-9B-mlx-2bit", latency_ms=300, errors=[], repairs=[])],
        message=f"(stub, source={cmd.source}) No changes made. Real model edits arrive with feat/patches.",
    )


# Proposed contracts (not in the original three; confirm with Owen): version history + undo for the side panel.
@app.get("/api/history")
def history():
    # STUB: replaced by "patches + undo" (feat/patches, Ashwin)
    return {"current": state["version"], "versions": [{"version": 1, "label": "sample level", "time": "00:00:00"}]}


@app.post("/api/undo")
def undo():
    # STUB: replaced by "patches + undo" (feat/patches, Ashwin)
    return {"ok": False, "version": state["version"], "message": "(stub) Nothing to undo."}


@app.post("/api/patch")
def apply_patch_direct(patch: dict):
    # STUB: replaced by "patches + undo" (feat/patches, Ashwin). Proposed: drawing applies its own
    # {"explanation", "ops"} patch here (no model), same validation + version history as /api/command.
    return {"ok": True, "version": state["version"], "message": f"(stub) would apply {len(patch.get('ops', []))} ops"}


class BBoxTiles(BaseModel):
    x: int
    y: int
    w: int
    h: int


class LabelIn(BaseModel):
    image: str  # base64 PNG crop of one drawn object (no "data:" prefix needed; either is accepted)
    bbox_tiles: BBoxTiles


Label = Literal["platform", "spikes", "enemy", "coin", "double_jump", "goal", "player_spawn"]


class LabelOut(BaseModel):
    label: Label
    confidence: float  # 0..1
    model: str
    latency_ms: int


@app.post("/api/label", response_model=LabelOut)
def label(req: LabelIn):
    # STUB: replaced by "vision labeling endpoint" (Ashwin)
    time.sleep(0.2)
    return LabelOut(label="platform", confidence=0.87, model="stub-Ternary-Bonsai-2-2B-mlx-2bit", latency_ms=200)


class TranscribeOut(BaseModel):
    text: str
    latency_ms: int


@app.post("/api/transcribe", response_model=TranscribeOut)
async def transcribe(audio: UploadFile = File(...)):
    # STUB: replaced by "Argmax speech-to-text offline" (Owen; backend forwards to ARGMAX_URL)
    await audio.read()
    return TranscribeOut(text="add three enemies near the end", latency_ms=450)


# Must be last: serves index.html, game.js, mechanics.js, vendor/
app.mount("/", StaticFiles(directory=ROOT / "frontend", html=True), name="frontend")
