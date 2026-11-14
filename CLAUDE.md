# CLAUDE.md — Sketch2Game

Standing instructions for every Claude Code session on this repo. Two people (each with their own Claude session) work here in parallel. Keep this file current and concise.

## Project
Sketch2Game is an offline, AI-powered 2D platformer maker. The user draws a level on a canvas (or starts from the sample), plays it in a Phaser 3 runtime, and edits it with natural-language commands ("make the gaps bigger", "add three enemies near the end"). A local LLM (Bonsai 2, 9B) returns a validated *patch* to the level JSON, and when a command needs new behavior ("make enemies jump toward the player") it also writes a new behavior function into `mechanics.js`. Hackathon MVP: working beats polished.

## Hard constraints
- **Runs with Wi-Fi off.** No CDN links, no cloud APIs, no fonts/images from the web. Phaser is bundled at `frontend/vendor/phaser.min.js`.
- **Model: Bonsai 2 (9B) only**, via a local OpenAI-compatible server (LM Studio or llama.cpp `server`).
- Speech (Argmax local transcription) comes later: a transcript must enter the **same command pipeline** as typed text (`source: "text" | "voice"`).

## Rules
- Model-written code may only go in `frontend/mechanics.js`. Never let the model touch any other file.
- Never add network calls to anything except the local backend (`/api/*`) and the local model endpoint.
- Keep `backend/levels/sample.json` loading and playable at all times.
- Don't build items listed under "Later" in plan.md unless asked.

## Workflow (both sessions)
1. Start of every session: `git pull`, then read `plan.md`.
2. Before starting a task: claim it under "In progress" in plan.md (task, owner, files touched), commit, push — so the other session doesn't start it too.
3. Stay inside the files your task needs; don't edit files the other person has claimed.
4. Commit small and often with clear messages; `git pull --rebase` before pushing.
5. After finishing: update plan.md (check off, clear "In progress", log decisions, known issues, refresh "Next up"), commit, push.
6. Update this file whenever architecture, file map, schema, or run instructions change.

## Architecture
```
Browser (one page, plain JS)                 FastAPI (Python)                 Local model
 ┌ Phaser game (game.js) ┐  GET /api/level   ┌ main.py ─ in-memory current ┐  OpenAI-compatible
 │  calls MECHANICS[name] │ ◄──────────────── │   level + version history   │  /v1/chat/completions
 │  (mechanics.js)        │  POST /api/command│ llm.py (planned) ──────────►│  Bonsai 2 9B
 └ side panel (log/undo) ┘ ────────────────► │ schema.py (Pydantic)        │
```
- Level state lives on the backend (in memory, loaded from `sample.json` at startup). Frontend fetches it and renders.
- Commands (typed now, voice later) → backend → model returns a patch → Pydantic validation (retry with errors, max 2) → apply → new version → frontend reloads level via `window.Sketch2Game.loadLevel(level)`.
- Entity behaviors are named functions in `mechanics.js` (`window.MECHANICS`), called each frame for entities whose `behaviors` list names them. Calls are wrapped in try/catch.

## File map
| Path | What it does |
|---|---|
| `backend/main.py` | FastAPI app: serves `frontend/`; `GET /api/level`, `POST /api/level/reset`, `GET /api/health` |
| `backend/schema.py` | Pydantic models: `Level`, `Entity`, `Physics`, patch ops |
| `backend/config.py` | Env-var config (model URL/name) |
| `backend/levels/sample.json` | Handwritten sample level (must always work) |
| `backend/requirements.txt` | Python deps |
| `frontend/index.html` | The single page: game left, side panel right |
| `frontend/game.js` | Phaser scene: builds level from JSON, player controls, collisions, win/death |
| `frontend/mechanics.js` | Behavior registry — the ONLY file the model may write |
| `frontend/vendor/phaser.min.js` | Phaser 3.80.1, bundled locally |

## Level JSON schema (tile units; origin top-left, y grows down)
```json
{
  "name": "Sample",
  "tile_size": 32, "width": 80, "height": 15,
  "physics": { "gravity": 1200, "jump_velocity": 560, "run_speed": 200 },
  "spawn": { "x": 2, "y": 11 },
  "entities": [
    { "id": "plat1", "type": "platform", "x": 0, "y": 13, "w": 18, "h": 2 },
    { "id": "enemy1", "type": "enemy", "x": 27, "y": 12, "behaviors": ["patrol"], "props": { "speed": 60, "range": 3 } }
  ]
}
```
- `type` ∈ `platform | spikes | lava | enemy | coin | double_jump | goal`.
- `x, y` = top-left tile; `w, h` = size in tiles (default 1). Must lie inside `width × height`. `id`s unique.
- `behaviors`: names of functions in `MECHANICS`. `props`: free-form scalars read by behaviors.
- Spikes/lava kill on touch. Enemies die when stomped from above, kill otherwise. `double_jump` grants one air jump. `goal` = win.

## Patch format (what the model returns)
```json
{ "explanation": "short text",
  "ops": [
    { "op": "add", "entity": { "id": "enemy9", "type": "enemy", "x": 70, "y": 12 } },
    { "op": "remove", "id": "coin3" },
    { "op": "move", "id": "plat2", "x": 24, "y": 9 },
    { "op": "set", "id": "plat2", "key": "w", "value": 6 },
    { "op": "set", "id": "enemy1", "key": "props.speed", "value": 90 },
    { "op": "set_physics", "key": "gravity", "value": 900 }
  ] }
```
`set` keys: `x, y, w, h, type, behaviors`, or `props.<name>`. `set_physics` keys: `gravity, jump_velocity, run_speed`. Ops apply in order; result must validate as a `Level`.

## Run
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --port 8000
# open http://localhost:8000
```
Controls: arrows/WASD move, Space/Up/W jump, R restart.

## Model endpoint config
| Env var | Default |
|---|---|
| `BONSAI_BASE_URL` | `http://localhost:1234/v1` |
| `BONSAI_MODEL` | `bonsai-2-9b` |
Start LM Studio's local server (or `llama-server --port 1234`) with Bonsai loaded.

## Conventions
- Python: type hints, Pydantic v2, keep endpoints in `main.py` until it hurts.
- JS: plain browser scripts (no build step, no modules, no npm deps at runtime). Globals: `window.MECHANICS`, `window.Sketch2Game` (`loadLevel(json)`, `log(msg, kind)`, `.level`, `.scene` for debugging).
- Behavior signature: `MECHANICS.name = function (entity, scene, dt) {}` — `entity` is a Phaser sprite with `.def` (JSON), `.props`, `.state` (scratch object); `dt` in seconds.
- No new dependencies without logging a decision in plan.md.
