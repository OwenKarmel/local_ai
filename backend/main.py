"""FastAPI app: serves the frontend and holds the current level in memory."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .schema import Level

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "backend" / "levels" / "sample.json"

app = FastAPI(title="Sketch2Game")
state = {"level": Level.model_validate_json(SAMPLE.read_text())}


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/level")
def get_level():
    return state["level"].model_dump()


@app.post("/api/level/reset")
def reset_level():
    state["level"] = Level.model_validate_json(SAMPLE.read_text())
    return state["level"].model_dump()


# Must be last: serves index.html, game.js, mechanics.js, vendor/
app.mount("/", StaticFiles(directory=ROOT / "frontend", html=True), name="frontend")
