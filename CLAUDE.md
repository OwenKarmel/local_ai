# CLAUDE.md — Voice game copilot (name TBD)

Standing instructions for every Claude Code session on this repo. Ashwin and Owen each run their own session in parallel. Keep this file current and concise. `plan.md` holds the contracts, task board and decisions.

## Project
An offline voice copilot that modifies a 2D platformer live while you play it. Hold V, say "lower the gravity", "make this harder" or "give me fireballs", and the running game changes without restarting. The copilot talks back through text-to-speech, and it refuses changes that would make the level impossible, explaining why out loud. It recreates Rosebud AI (edit games by chatting with a cloud AI) fully on-device. Built for the Cornell Local AI Hackathon; must use Bonsai (PrismML) and Argmax. Working beats polished.

## Hard constraints
- **Runs with Wi-Fi off.** No CDN links, no cloud APIs, no fonts/images from the web. Phaser is bundled at `frontend/vendor/phaser.min.js`.
- **Language models: Bonsai 2 only**, via a local OpenAI-compatible server (`mlx_vlm.server`).
- **Speech: Argmax only.** WhisperKit for speech-to-text, TTSKit for the copilot's voice, SpeakerKit for chaos mode.
- **No "Mario" or any Nintendo name or art** anywhere in the repo, UI or docs.

## Architecture
```
Hold V → record audio → POST /api/transcribe (Argmax WhisperKit, local) → transcript in HUD
  → POST /api/command
      → router: "fast" (settings, abilities; FAST_MODEL, tiny prompt)
                "level" (geometry, entities; CODE_MODEL, level summary)
      → model returns intent-level ops
      → backend converts to concrete LowLevelOps, validates the schema
      → playability checker
      → applied: patch + new level + short spoken message
        refused: reason + spoken message
  → frontend applies the patch live to the running scene (keeps position, score, power-ups)
  → POST /api/speak (Argmax TTSKit) → play the audio
```
Key principles:
- **The model chooses intent; deterministic code does geometry and enforces rules.**
- **Every change goes through the playability checker.** Nothing reaches the game unless the goal is still reachable.
- **Edits apply live.** Full level reload is only a fallback if live apply fails.
- **Jump physics live in ONE shared config file** read by both game.js and the checker (gravity, jump velocity, run speed, player size, double-jump strength, coyote time). Never duplicate these numbers.
- **Latency is a first-class concern.** Log model, route and latency for every command.

Level state lives on the backend, in memory, as a stack of versions (loaded from `sample.json` at startup). Frontend and backend meet only through the HTTP contracts in plan.md.

## Ownership
- **Ashwin owns `backend/`** and the playability checker.
- **Owen owns `frontend/`** and the Argmax setup. Owen also owns two small backend edits: the bodies of `/api/transcribe` (O1, O5) and `/api/speak` (O4).
- **Shared** (heads-up to the other person before changing): `CLAUDE.md`, `plan.md`, the shared physics config, the level schema (`backend/schema.py` and the JSON below), the interface contracts.
- Each session stays in its owner's files. If a task needs a change on the other side, describe it in the PR instead of making it.

## Rules
- Model-written code may only go in `frontend/mechanics.js`.
- No network calls except the local backend (`/api/*`), the local model server and the local Argmax server.
- Keep `backend/levels/sample.json` loading and playable at all times.
- Physics numbers only in the shared config (once A3 lands).
- Contract changes need a decisions-log entry in plan.md and a heads-up.
- Never add Claude as a co-author or contributor: no `Co-Authored-By: Claude …` trailer, no "Generated with Claude Code" line.

## Git and PR workflow
Start of every session: `git checkout main && git pull`, read `plan.md`, run `gh pr list` and review anything waiting on you.

- **One branch per task ID**, e.g. `a2-intent-ops`, `o3-live-apply`. Set the task's status to `doing` on the board.
- Medium-sized commits with clear messages. Push at least hourly: `git push -u origin <branch>`.
- If main moved and you touch the same files, rebase early: `git fetch && git rebase origin/main`.
- **Open a PR when the task meets its "done when"**: `gh pr create`. Title starts with the task ID. Description: what changed, how to test (exact steps), anything unfinished, any contract change.
- **Ashwin's session reviews Owen's PRs and vice versa.** Review within about 15 minutes: `gh pr checkout <n>`, run it, then `gh pr review <n> --approve` or `--comment -b "..."`. If the reviewer is unavailable for 20+ minutes and the change is small and tested, the author may merge and note it in plan.md.
- **Review checklist:**
  - runs from a clean pull; sample level still works
  - no network calls or CDN links
  - no model weights, venvs or `.env` committed
  - contract unchanged, or the change is logged
  - stays in the owner's files
  - model-written code only in mechanics.js
  - physics numbers only in the shared config
- **Merge:** `gh pr merge <n> --squash --delete-branch`, then update the task board on main and push.
- plan.md conflicts are expected; keep both sides' entries. For code conflicts, the person rebasing resolves them and reruns the game.
- **Sunday 9am: feature freeze and tag `demo-v1`.**
- Never commit model weights, the mlx-venv, `__pycache__`, level version history files or `.env` files.

## File map
| Path | What it does |
|---|---|
| `backend/main.py` | FastAPI app: serves `frontend/`, version stack, all `/api/*` endpoints. Endpoints marked `STUB: replaced by <task ID>` return canned responses |
| `backend/schema.py` | Pydantic models: `Level` (with `abilities`), `Entity`, `Physics`; older patch-op models used by `feat/patches` |
| `backend/config.py` | Env-var config: `BONSAI_BASE_URL`, `FAST_BASE_URL`, `CODE_MODEL`, `FAST_MODEL`, `ARGMAX_URL` |
| `backend/levels/sample.json` | Handwritten sample level, 40×15, 4 coins (must always work) |
| `backend/requirements.txt` | Python deps |
| `frontend/index.html` | The single page: game plus side panel |
| `frontend/game.js` | Phaser scene: builds the level from JSON, player controls, collisions, win/death |
| `frontend/mechanics.js` | Behavior registry (`patrol`). The only file model-written code may go in |
| `frontend/vendor/phaser.min.js` | Phaser 3.80.1, bundled locally |

On `feat/patches` (PR #1, not merged): `backend/llm.py`, `summary.py`, `intents.py`, `patcher.py`, `pipeline.py`, `prompts.py`, `eval_commands.py`.

## Contracts
The source of truth is **plan.md → "Interface contracts"**: `/api/transcribe`, `/api/command`, `LowLevelOp`, `/api/speak`, `/api/level`, `/api/undo`, and what each stub returns.

## Level JSON schema (tile units; origin top-left, y grows down)
```json
{
  "name": "Sample",
  "tile_size": 32, "width": 40, "height": 15,
  "physics": { "gravity": 1200, "jump_velocity": 560, "run_speed": 200 },
  "abilities": { "fireball": { "enabled": true, "key": "F", "speed": 420, "cooldown_ms": 400, "bounces": 2, "kills": true } },
  "spawn": { "x": 2, "y": 11 },
  "entities": [
    { "id": "ground1", "type": "platform", "x": 0, "y": 13, "w": 14, "h": 2 },
    { "id": "enemy1", "type": "enemy", "x": 23, "y": 12, "behaviors": ["patrol"], "props": { "speed": 60, "range": 3 } }
  ]
}
```
- `type` ∈ `platform | spikes | lava | enemy | coin | double_jump | goal`.
- `x, y` = top-left tile; `w, h` = size in tiles (default 1). Must lie inside `width × height`. `id`s unique.
- `behaviors`: names of functions in `MECHANICS`. `props`: free-form scalars read by behaviors.
- `abilities`: optional, default `{}`. Fireball fields are finalized by A9.
- Spikes/lava kill on touch. Enemies die when stomped from above, kill otherwise. `double_jump` grants one air jump. `goal` = win.

## Setup for a new teammate (Apple Silicon Mac)
Needs: Python 3.10+, git, `gh` logged in. Steps 1–3 and 6–7 are enough for the game and all stub endpoints; **the model server (4–5) is only needed for real model calls.**
```bash
# 1. Clone
git clone https://github.com/OwenKarmel/local_ai.git && cd local_ai

# 2. Python env for the backend
python3 -m venv .venv && source .venv/bin/activate

# 3. Backend deps
pip install -r backend/requirements.txt

# 4. Model runtime + Bonsai 2 models (one-time, needs internet, about 6.6 GB of models)
python3 -m venv ~/models/mlx-venv && ~/models/mlx-venv/bin/pip install "mlx-vlm>=0.7.8"
mkdir -p ~/models/prism-ml && cd ~/models/prism-ml
for s in 2B 4B 9B; do ~/models/mlx-venv/bin/hf download prism-ml/Ternary-Bonsai-2-$s-mlx-2bit --local-dir Ternary-Bonsai-2-$s-mlx-2bit; done
cd -

# 5. Model server (separate terminal; works offline)
~/models/mlx-venv/bin/python -m mlx_vlm.server --model ~/models/prism-ml/Ternary-Bonsai-2-9B-mlx-2bit --host 127.0.0.1 --port 1234

# 6. Backend (separate terminal, from the repo root)
source .venv/bin/activate && uvicorn backend.main:app --reload --port 8000

# 7. Open the game
open http://localhost:8000
```
No `.env` needed. Check with `curl localhost:8000/api/health`. Try a stub: `curl -s localhost:8000/api/command -H 'Content-Type: application/json' -d '{"text":"lower the gravity","source":"typed","speaker":null}'`.

Argmax setup (WhisperKit server, TTSKit, SpeakerKit): Owen documents the commands here as O1, O4 and O5 land.

Controls: arrows/WASD move, Space/Up/W jump, R restart. `--reload` watches `.py` only; after editing `sample.json`, restart the backend or use the Reset button.

## Config (env vars)
| Env var | Default |
|---|---|
| `BONSAI_BASE_URL` | `http://localhost:1234/v1` |
| `FAST_BASE_URL` | same as `BONSAI_BASE_URL`. Point it at a second `mlx_vlm.server` (e.g. port 1235, loaded with the 2B) to keep both models in memory |
| `CODE_MODEL` | `~/models/prism-ml/Ternary-Bonsai-2-9B-mlx-2bit` (level route) |
| `FAST_MODEL` | `~/models/prism-ml/Ternary-Bonsai-2-2B-mlx-2bit` (routing, fast route) |
| `BONSAI_MODELS_DIR` | `~/models/prism-ml` (base for the two defaults above) |
| `ARGMAX_URL` | `http://localhost:50060/v1` (placeholder; Owen confirms in O1) |

Model notes:
- Bonsai 2 MLX packs need **mlx-vlm ≥ 0.7.8**; released mlx-lm (and LM Studio's MLX engine) can't load them yet.
- Model ids are the absolute folder paths, as listed at `GET $BONSAI_BASE_URL/models`.
- One server process keeps one model loaded; requesting another swaps it (about 4 s). It honors `response_format: json_schema`.
- Thinking is off by default. Send sampler params per request: `temperature 0.7, top_p 0.8, top_k 20, presence_penalty 1.5`.
- Sizes on disk: 2B 1.2 GB, 4B 1.9 GB, 9B 3.5 GB.

## Conventions
- Python: type hints, Pydantic v2, keep endpoints in `main.py` until it hurts.
- JS: plain browser scripts (no build step, no modules, no npm deps at runtime). Globals: `window.MECHANICS`, `window.Sketch2Game` (working name; `loadLevel(json)`, `log(msg, kind)`, `.level`, `.scene`).
- Behavior signature: `MECHANICS.name = function (entity, scene, dt) {}`. `entity` is a Phaser sprite with `.def` (JSON), `.props`, `.state`; `dt` in seconds.
- No new dependencies without a decisions-log entry in plan.md.
