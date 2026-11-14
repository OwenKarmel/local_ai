# CLAUDE.md — Sketch2Game

Standing instructions for every Claude Code session on this repo. Two people (each with their own Claude session) work here in parallel. Keep this file current and concise.

## Project
Sketch2Game is an offline, AI-powered 2D platformer maker. The user draws a level on a canvas (or starts from the sample), plays it in a Phaser 3 runtime, and edits it with natural-language commands ("make the gaps bigger", "add three enemies near the end"). A local LLM (Bonsai 2) returns a validated *patch* to the level JSON, and when a command needs new behavior ("make enemies jump toward the player") it also writes a new behavior function into `mechanics.js`. Hackathon MVP: working beats polished.

## Hard constraints
- **Runs with Wi-Fi off.** No CDN links, no cloud APIs, no fonts/images from the web. Phaser is bundled at `frontend/vendor/phaser.min.js`.
- **Models: Bonsai 2 only**, via a local OpenAI-compatible server (we use `mlx_vlm.server`; LM Studio / llama.cpp also fine). Two models, set by env vars:
  - `CODE_MODEL` (default Bonsai 2 9B): level patches and mechanics code.
  - `FAST_MODEL` (default Bonsai 2 2B): conversational replies and simple classification (incl. drawing labels, see plan.md).
  - Log which model handled each request and its latency (backend log + side panel).
- Speech (Argmax local transcription) comes later: a transcript must enter the **same command pipeline** as typed text (`source: "text" | "voice"`).

## Rules
- Model-written code may only go in `frontend/mechanics.js`. Never let the model touch any other file.
- Never add network calls to anything except the local backend (`/api/*`) and the local model endpoint.
- Keep `backend/levels/sample.json` loading and playable at all times.
- Don't build items listed under "Later" in plan.md unless asked.

## Workflow (both sessions)
- Start of every session: `git checkout main && git pull`, read `plan.md`, and check `gh pr list` for PRs waiting on your review.
- Stay inside the files your task needs; don't edit files the other person has claimed.
- Update this file whenever architecture, file map, schema, or run instructions change.
- Details: see "Git workflow" below.

## Git workflow

Setup (once): make sure `gh` (GitHub CLI) is installed and logged in.

Starting a task:
1. `git checkout main && git pull`
2. `git checkout -b feat/<short-name>`
3. Claim it in plan.md "In progress" with owner and branch, commit that on the branch.

While working:
- Commit whenever something works, even partially. Medium-sized commits with clear messages ("add patch validation", "fix enemy stomp hitbox").
- Push the branch at least every hour so work is never only on one laptop: `git push -u origin feat/<short-name>`
- If main has moved and you touch the same files, rebase early: `git fetch && git rebase origin/main`

Opening a PR:
- Open it when the feature works end to end, even if rough: `gh pr create --fill`
- PR description: what changed, how to test it (exact commands or clicks), anything half-done.
- Keep PRs under a few hundred lines when possible. Split big features.

Reviewing the other person's PR:
- `gh pr checkout <number>`, run it, try the test steps.
- Check for: anything that breaks the sample level, network calls, model-written code outside mechanics.js, files that shouldn't be committed.
- Approve or leave short comments: `gh pr review <number> --approve` (or `--comment -b "..."`)
- Review within ~15 minutes. If the reviewer is unavailable for 20+ minutes and the change is small and tested, the author may merge it and say so in plan.md.

Merging:
- `gh pr merge <number> --squash --delete-branch`
- Then on main: update plan.md (check off the task, clear "In progress", refresh "Next up"), commit, push.
- After the other person merges, pull main before starting anything new.

Never commit:
- Model weights, the mlx-venv, `__pycache__`, level version history files, `.env` files. Keep these in `.gitignore`.

Attribution:
- Never add Claude as a co-author or contributor: no `Co-Authored-By: Claude …` trailer in commits, no "Generated with Claude Code" line in PR descriptions. Commits are authored by the human whose machine they're on.

Conflicts:
- plan.md conflicts are expected; keep both sides' entries.
- For code conflicts, the person rebasing resolves them and reruns the game before pushing.

## Architecture
```
Browser (one page, plain JS)                 FastAPI (Python)                 Local model
 ┌ Phaser game (game.js) ┐  GET /api/level   ┌ main.py ─ in-memory current ┐  OpenAI-compatible
 │  calls MECHANICS[name] │ ◄──────────────── │   level + version history   │  /v1/chat/completions
 │  (mechanics.js)        │  POST /api/command│ llm.py (planned) ──────────►│  Bonsai 2 (CODE/FAST)
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
| `backend/config.py` | Env-var config: `BONSAI_BASE_URL`, `CODE_MODEL`, `FAST_MODEL` |
| `backend/levels/sample.json` | Handwritten sample level, 40×15, 4 coins (must always work) |
| `backend/requirements.txt` | Python deps |
| `frontend/index.html` | The single page: game left, side panel right |
| `frontend/game.js` | Phaser scene: builds level from JSON, player controls, collisions, win/death |
| `frontend/mechanics.js` | Behavior registry — the ONLY file the model may write |
| `frontend/vendor/phaser.min.js` | Phaser 3.80.1, bundled locally |

## Level JSON schema (tile units; origin top-left, y grows down)
```json
{
  "name": "Sample",
  "tile_size": 32, "width": 40, "height": 15,
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
| `CODE_MODEL` | `~/models/prism-ml/Ternary-Bonsai-2-9B-mlx-2bit` (patches, mechanics code) |
| `FAST_MODEL` | `~/models/prism-ml/Ternary-Bonsai-2-2B-mlx-2bit` (chat replies, classification) |
Env values must match the IDs at `GET $BONSAI_BASE_URL/models` (for mlx_vlm.server that's the absolute folder path; for LM Studio, its model key).

### Model setup (Mac, MLX — what we use)
Bonsai 2 MLX packs (`model_type: prism_hadamard_qwen35`) need **mlx-vlm ≥ 0.7.8**; released mlx-lm (and so likely LM Studio's MLX engine) can't load them yet. One-time, needs internet:
```bash
mkdir -p ~/models/prism-ml && cd ~/models/prism-ml
for s in 2B 4B 9B; do hf download prism-ml/Ternary-Bonsai-2-$s-mlx-2bit --local-dir Ternary-Bonsai-2-$s-mlx-2bit; done
python3 -m venv ~/models/mlx-venv && ~/models/mlx-venv/bin/pip install "mlx-vlm>=0.7.8"
```
Run the server (offline OK):
```bash
~/models/mlx-venv/bin/python -m mlx_vlm.server --model ~/models/prism-ml/Ternary-Bonsai-2-9B-mlx-2bit --host 127.0.0.1 --port 1234
```
- Thinking is off by default (`--enable-thinking` turns it on). Send sampler params per request; non-thinking: `temperature 0.7, top_p 0.8, top_k 20, presence_penalty 1.5`.
- Sizes on disk: 2B 1.2 GB, 4B 1.9 GB, 9B 3.5 GB. All are vision models (needed for drawing labels).
- Fallback for non-Mac / llama.cpp: `prism-ml/Ternary-Bonsai-2-*-gguf`.

## Conventions
- Python: type hints, Pydantic v2, keep endpoints in `main.py` until it hurts.
- JS: plain browser scripts (no build step, no modules, no npm deps at runtime). Globals: `window.MECHANICS`, `window.Sketch2Game` (`loadLevel(json)`, `log(msg, kind)`, `.level`, `.scene` for debugging).
- Behavior signature: `MECHANICS.name = function (entity, scene, dt) {}` — `entity` is a Phaser sprite with `.def` (JSON), `.props`, `.state` (scratch object); `dt` in seconds.
- No new dependencies without logging a decision in plan.md.
