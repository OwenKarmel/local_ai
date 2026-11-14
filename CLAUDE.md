# CLAUDE.md — Voice game copilot (name TBD)

Standing instructions for every Claude Code session on this repo. Ashwin and Owen each run their own session in parallel. Keep this file current and concise. `plan.md` holds the demo script (the one goal), the task board, the contracts and the decisions.

## Core principle (read first)
**Nothing about what a command does is hardcoded.** No keyword matching, no "if it hears X, do Y", no prebuilt difficulty steps, no pre-written abilities. Every command goes to Bonsai, which decides what to change and writes any new game code itself. Judges may try their own commands at the finals, so the system must stay general.

Our code provides only:
- **Building blocks:** the engine plus a documented mechanics API the model codes against (spawn entities and projectiles, physics bodies, velocity, collisions, input keys, timers, entity properties, tint and sprite). Rich enough that typical abilities take the model 10–30 lines.
- **Context in the prompt:** compact level summary, current physics, the player's current abilities and limits, player position, cursor tile.
- **Guardrails:** schema validation, the code sandbox (model code only in mechanics.js, syntax check, runtime error capture, automatic rollback), the playability checker, and at most one retry that feeds the error back to the model.
- **Measurement:** stats on every change.
- **An immediate spoken acknowledgment** ("On it") while the model works. This is feedback, not behavior.

**Test for any code:** if it only exists to handle one specific command, it's hardcoding and doesn't belong. If many different commands could use it, it's a building block.
- Prompt examples must not match the demo commands (e.g. show a bouncing-coin behavior, not fireballs).
- When a demo beat fails more than 1 time in 5, fix the API, the prompt context or the examples, never by hardcoding the behavior. If it still fails Sunday morning, cut the beat rather than fake it.
- Keyword stubs exist only behind `STUB_COMMANDS=1`, for frontend work without a model.

## Project
An offline voice copilot that edits your game while you play. A 2D platformer changes live while you play it. Hold V, say "lower the gravity", "make this harder" or "give me fireballs", and the running game changes without restarting. The copilot talks back through text-to-speech, and it refuses changes that would make the level impossible, explaining why out loud. It recreates Rosebud AI (edit games by chatting with a cloud AI) fully on-device. Built for the Cornell Local AI Hackathon; must use Bonsai (PrismML) and Argmax. Working beats polished.

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
- **Tasks are claimed by number** on plan.md's board (status `doing (<name>)`) before starting. Whoever claims a task owns its files until it merges. Don't edit files another open task has claimed; describe the change in your PR instead.
- **Mac-only work** (MLX models, Argmax, recording; marked 🍎 on the board) happens on Ashwin's Mac, the demo machine. Owen has no Mac (Acer laptop) and works against the stubs, or against Ashwin's model server over the local network.
- **Shared** (heads-up to the other person before changing): `CLAUDE.md`, `plan.md`, the shared physics config, the level schema (`backend/schema.py` and the JSON below), the interface contracts, the checker interface.

## Rules
- Model-written code may only go in `frontend/mechanics.js`, and only through the sandbox (syntax check, runtime error capture, automatic rollback).
- Everything serves the demo script in plan.md. Work not tied to a beat goes under "Later".
- No network calls except the local backend (`/api/*`), the local model server and the local Argmax server.
- Keep `backend/levels/sample.json` loading and playable at all times.
- Physics numbers only in the shared config (once A3 lands).
- Contract changes need a decisions-log entry in plan.md and a heads-up.
- Never read, search, or edit the bundled Phaser file (`frontend/vendor/phaser.min.js`); it's a third-party library and reading it wastes context. Use the Phaser 3 API from memory or its official docs. When searching the codebase, exclude it.
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
| `backend/main.py` | FastAPI app: serves `frontend/`, version stack, all `/api/*` endpoints. `/api/transcribe` and `/api/speak` are still `STUB`s |
| `backend/schema.py` | Pydantic models: `Level` (with `abilities`), `Entity`, `Physics`, `LowLevelOp` |
| `backend/config.py` | Env-var config: `BONSAI_BASE_URL`, `FAST_BASE_URL`, `CODE_MODEL`, `FAST_MODEL`, `ARGMAX_URL` |
| `backend/levels/sample.json` | Handwritten sample level, 40×15, 4 coins (must always work) |
| `backend/requirements.txt` | Python deps |
| `frontend/index.html` | The single page: game plus side panel |
| `frontend/game.js` | Phaser scene: builds the level from JSON, player controls, collisions, win/death |
| `frontend/voice.js` | Hold-to-talk (button or V), listening badge + mic meter, typed fallback; calls `/api/transcribe`, `/api/command`, `/api/speak` |
| `frontend/sprites.js` | `window.SPRITES`: loads the sprite catalog, skins entities (with fallbacks), particle effects, projectile visuals |
| `frontend/assets/catalog.json` | Sprite catalog: name, file, type, description, size, animations, tilesets, per-type defaults |
| `frontend/assets/catalog.txt` | Compact `name: description` list for model prompts |
| `frontend/assets/sprites/` | The PNGs we use (about 200 KB) plus `License.txt` |
| `tools/build_catalog.py` | Rebuilds `frontend/assets/` from a downloaded Kenney pack |
| `frontend/mechanics.js` | Behavior registry (`patrol`). The only file model-written code may go in |
| `frontend/vendor/phaser.min.js` | Phaser 3.80.1, bundled locally |
| `testbonsai/` | Dev-only: run Bonsai 2 GGUF with llama.cpp (CUDA) + Open WebUI on a non-Mac machine (WSL2). Not part of the demo |

| `backend/llm.py` | Client for the local model server; logs model + latency |
| `backend/summary.py` | Level analysis + the text summary the model sees (ground, gaps, platforms, objects, regions, player) |
| `backend/intents.py` | High-level ops the model emits (widen_gap, add_enemy, set_ability, …), id-restricted JSON schema, compiler to coordinates |
| `backend/patcher.py` | `Editor` (working copy + automatic fixes), `diff_levels` (old vs new → LowLevelOps), `apply_low_level` |
| `backend/pipeline.py` | `run_command(level, text, model, player)`: prompt → model → intents → fixes → validate → contract response. Max 1 model retry |
| `backend/prompts.py` | System prompt + 2 worked examples |
| `backend/speech.py` | `/api/transcribe` helper: ffmpeg convert + pad, forward to the Argmax server |
| `backend/stub_commands.py` | Canned keyword responses for `/api/command` when `STUB_COMMANDS=1` |
| `backend/eval_commands.py` | `python -m backend.eval_commands --models 4B`: success, latency and tok/s per model |

## Contracts
The source of truth is **plan.md → "Interface contracts"**: `/api/transcribe`, `/api/command`, `LowLevelOp`, `/api/speak`, `/api/level`, `/api/undo`, and what each stub returns.

## Level JSON schema (tile units; origin top-left, y grows down)
```json
{
  "name": "Sample",
  "tile_size": 32, "width": 40, "height": 15,
  "physics": { "gravity": 1200, "jump_velocity": 560, "run_speed": 200 },
  "abilities": { "bouncy_coins": { "enabled": true } },
  "spawn": { "x": 2, "y": 11 },
  "entities": [
    { "id": "ground1", "type": "platform", "x": 0, "y": 13, "w": 14, "h": 2 },
    { "id": "enemy1", "type": "enemy", "x": 23, "y": 12, "behaviors": ["patrol"], "props": { "speed": 60, "range": 3 }, "sprite": "enemy_frog", "tint": "#3399ff" }
  ]
}
```
- `type` ∈ `platform | spikes | lava | enemy | coin | double_jump | goal`.
- `x, y` = top-left tile; `w, h` = size in tiles (default 1). Must lie inside `width × height`. `id`s unique.
- `behaviors`: names of functions in `MECHANICS`. `props`: free-form scalars read by behaviors.
- `sprite`, `tint`: optional, default `null`. See "Assets and sprites".
- `abilities`: optional, default `{}`. Settings for abilities whose code the model wrote in mechanics.js (task 6). No ability is pre-written.
- Spikes/lava kill on touch. Enemies die when stomped from above, kill otherwise. `double_jump` grants one air jump. `goal` = win.

## Assets and sprites
- **Art:** Kenney "New Platformer Pack 1.1" (kenney.nl), **CC0** (public domain; credit optional). The license file is at `frontend/assets/sprites/License.txt`. `ball_white.png` and `effect_*.png` are derived or generated from it. No other art sources without checking the license; never Nintendo or other copyrighted game art.
- Only the sprites we use are in the repo. Never commit the full downloaded pack. To add sprites: edit `tools/build_catalog.py`, then run `python tools/build_catalog.py <extracted pack folder>` (needs Pillow).
- Entities take optional `sprite` (a catalog name) and `tint` (hex like `#3399ff`). Unknown sprite name → the type's default sprite → a plain colored rectangle. The game never crashes on a bad name or tint.
- Physics bodies do not depend on the art: player 24×30, enemy 28×24, whatever sprite is used.
- Live look changes: `Sketch2Game.setAppearance(id, {sprite, tint})`, `Sketch2Game.setPlayerLook({sprite, tint})`. Projectile visuals: `SPRITES.spawnProjectile(scene, x, y, dir, {sprite, tint, speed})` and `SPRITES.setProjectileLook(scene, projectile, {sprite, tint})`.

## Working without a Mac (Windows, Linux, or a Mac without the models)
Everything except the models and Argmax runs anywhere: the game, the backend, the stub endpoints, and the playability checker. Needs Python 3.10+, git, and `gh` logged in (`gh auth login`).

**Windows (PowerShell):**
```powershell
git clone https://github.com/OwenKarmel/local_ai.git; cd local_ai
py -3 -m venv .venv                       # or: python -m venv .venv
.venv\Scripts\Activate.ps1                # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -r backend/requirements.txt
$env:STUB_COMMANDS = "1"                  # canned /api/command responses, no model server
$env:STUB_SPEECH = "1"                    # fixed /api/transcribe text, no Argmax
uvicorn backend.main:app --reload --port 8000
# new PowerShell window:
start http://localhost:8000
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/command -ContentType "application/json" `
  -Body '{"text":"lower the gravity","source":"typed","speaker":null,"player":null}'
```
**macOS / Linux:**
```bash
git clone https://github.com/OwenKarmel/local_ai.git && cd local_ai
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
STUB_COMMANDS=1 STUB_SPEECH=1 uvicorn backend.main:app --reload --port 8000     # then open http://localhost:8000
```
- Speech needs Argmax (Mac only). Also set `STUB_SPEECH=1` (PowerShell: `$env:STUB_SPEECH = "1"`) so `/api/transcribe` returns fixed text; without it, it returns HTTP 503. `/api/speak` is a stub (beep wav) until O4.
- Without `STUB_COMMANDS=1`, `/api/command` tries the model server and returns `status: "error"` ("Model server not reachable").
- No model server, Argmax, `~/models` folder or `.env` is needed.

**Optional: real models from another machine (development only).** The demo runs entirely on Ashwin's Mac. For testing against the real 4B from Owen's machine:
1. Ashwin starts the model server on the local network: `~/models/mlx-venv/bin/python -m mlx_vlm.server --model ~/models/prism-ml/Ternary-Bonsai-2-4B-mlx-2bit --host 0.0.0.0 --port 1234`. Find the Mac's address with `ipconfig getifaddr en0`, and allow Python through the macOS firewall prompt.
2. Owen gets the model id: `Invoke-RestMethod http://<mac-ip>:1234/v1/models` (it's an absolute path on Ashwin's Mac).
3. Owen sets `$env:BONSAI_BASE_URL = "http://<mac-ip>:1234/v1"` and `$env:CODE_MODEL` / `$env:FAST_MODEL` to that id, clears `STUB_COMMANDS`, and runs the backend as usual.
- Both machines must be on the same network. Venue Wi-Fi often blocks device-to-device traffic; a phone hotspot works.
- The server has no authentication: only do this on a network you trust, and go back to `--host 127.0.0.1` afterwards.
- Both people sharing one model server slows each other's requests.

## Setup on the demo Mac (Apple silicon; models and Argmax)
Needs: Python 3.10+, git, `gh` logged in. Steps 1–3 and 6–7 are enough for the game and all stub endpoints; **the model server (4–5) is only needed for real model calls.** Steps 4–5 are macOS-only.
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
~/models/mlx-venv/bin/python -m mlx_vlm.server --model ~/models/prism-ml/Ternary-Bonsai-2-4B-mlx-2bit --host 127.0.0.1 --port 1234

# 6. Backend (separate terminal, from the repo root). Without the model server: STUB_COMMANDS=1 uvicorn ...
source .venv/bin/activate && uvicorn backend.main:app --reload --port 8000

# 7. Open the game
open http://localhost:8000
```
No `.env` needed. Check with `curl localhost:8000/api/health`. Try a command: `curl -s localhost:8000/api/command -H 'Content-Type: application/json' -d '{"text":"lower the gravity","source":"typed","speaker":null,"player":null}'`.

**No model server?** Start the backend with `STUB_COMMANDS=1 uvicorn backend.main:app --reload --port 8000`. `/api/command` then returns canned keyword responses (plan.md → "Stubs").

### Argmax setup (speech; macOS 14+, TTSKit needs 15+, Xcode 16+)
Lives outside the repo in `~/argmax`. One-time, needs internet, about 3 GB (build 1.3 GB, Whisper models 740 MB, TTS model 1 GB):
```bash
mkdir -p ~/argmax && cd ~/argmax && git clone https://github.com/argmaxinc/argmax-oss-swift.git && cd argmax-oss-swift
BUILD_ALL=1 swift build -c release --product argmax-cli          # about 3 min; BUILD_ALL=1 includes the server
make download-model MODEL=large-v3-v20240930_626MB                # demo model (598 MB); also: MODEL=base.en (140 MB)
rm -rf Models/whisperkit-coreml/.git/lfs/objects                  # optional: git-lfs keeps a duplicate copy of every model
brew install ffmpeg                                               # backend uses it to convert/pad audio (see backend/speech.py)
```
`make setup` is not needed (it installs fastlane/xcbeautify for the iOS example apps).

Run the speech-to-text server (separate terminal, works offline):
```bash
cd ~/argmax/argmax-oss-swift && .build/release/argmax-cli serve \
  --model-path Models/whisperkit-coreml/openai_whisper-large-v3-v20240930_626MB --host 127.0.0.1 --port 50060 --language en
```
- The first start of a model compiles it for this Mac (about 1.5 min for large-v3); later starts take about 2 s.
- Check: `curl -s localhost:8000/api/transcribe -F audio=@some.wav`, or straight to Argmax: `curl -s localhost:50060/v1/audio/transcriptions -F file=@some.wav -F model=whisper -F response_format=json`.
- Server quirks (argmax-oss-swift `9f99b5c`): the `model` form field is required but ignored, and `temperature=0` returns HTTP 500 (`0.0` works). `backend/speech.py` handles both.
- Whisper returns empty text for clips under about 1 s, so the backend pads audio to 2 s. It also converts webm/opus (what browsers record) to WAV.

Text-to-speech (O4 will wrap this in `/api/speak`):
```bash
.build/release/argmax-cli tts --model 0.6b --text "Gravity lowered." --play                                   # speakers
.build/release/argmax-cli tts --model 0.6b --text "Gravity lowered." --output-path out --output-format wav   # out.wav, 24 kHz
```
The 0.6b model (about 1 GB) downloads to `~/Documents/huggingface` on first use. Voices: `--speaker aiden|ryan|eric|dylan|serena|vivian|…`.

Controls: arrows/WASD move, Space/Up/W jump, R restart. `--reload` watches `.py` only; after editing `sample.json`, restart the backend or use the Reset button.

## Config (env vars)
| Env var | Default |
|---|---|
| `BONSAI_BASE_URL` | `http://localhost:1234/v1` |
| `FAST_BASE_URL` | same as `BONSAI_BASE_URL`. Point it at a second `mlx_vlm.server` (e.g. port 1235, loaded with the 2B) to keep both models in memory |
| `CODE_MODEL` | `~/models/prism-ml/Ternary-Bonsai-2-4B-mlx-2bit` (level route) |
| `FAST_MODEL` | `~/models/prism-ml/Ternary-Bonsai-2-4B-mlx-2bit` (fast route, A4). Same model on purpose: one server, no swapping |
| `STUB_COMMANDS` | unset. `1` = `/api/command` returns canned keyword responses, no model server needed |
| `BONSAI_MODELS_DIR` | `~/models/prism-ml` (base for the two defaults above) |
| `ARGMAX_URL` | `http://localhost:50060/v1` (`argmax-cli serve` default port) |
| `STUB_SPEECH` | unset. `1` = `/api/transcribe` returns fixed text, no Argmax needed |

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
