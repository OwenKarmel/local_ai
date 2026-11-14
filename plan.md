# plan.md — Sketch2Game

## Goal & demo story
Offline AI platformer maker. Demo (Wi-Fi off): draw a rough level → it becomes a playable Mario-style level → play it → say or type "make the gaps bigger" / "add three enemies near the end" → level updates → "make enemies jump toward the player" → model writes a new behavior into mechanics.js and enemies start hopping → undo if anything breaks.

## Scope
**In:** Phaser runtime + sample level; NL command (typed or spoken via Argmax) → validated patch with retries + undo; drawing canvas → grouped strokes → labeled (vision or pen color) → patch; model-written behaviors in mechanics.js with rollback.
**Out:** multiplayer. Text-to-speech, playability checker etc. are P1/P2 below.

## Deadlines
| When | What |
|---|---|
| Midnight Saturday | All P0 merged |
| 9:00am Sunday | Feature freeze; tag the release (`git tag demo && git push --tags`) |
| 10:30am Sunday | Final demo video recorded |
| 11:30am Sunday | Submitted |

## Checklist (update only when a PR merges)
**P0**
- [ ] Patches + undo (Ashwin)
- [ ] Argmax speech-to-text offline (Owen)
- [ ] Push-to-talk + editable transcript (Owen)
- [ ] Canvas drawing with color fallback (Owen)
- [ ] Vision labeling endpoint (Ashwin)
- [ ] Full offline test, Wi-Fi off (both)
- [ ] Demo video + submission by 11:30am Sunday (both)

**P1**
- [ ] Model-written mechanics with rollback (Ashwin)
- [ ] Playability checker + jump arcs (Ashwin)
- [ ] TTSKit narrator (Owen)
- [ ] Eval table (Ashwin)
- [ ] Backup video by midnight (both)

**P2**
- [ ] Sprites and sound
- [ ] SpeakerKit edit attribution
- [ ] More power-ups and enemies

Done before the checklist existed: [x] Game runtime (feature 1: sample level, all entity types, coyote time, camera, restart, win).

## Interface contracts (source of truth; exact field names and types)
Change these only after telling the other person. Extra response fields are allowed only if listed here.

**`POST /api/command`** (JSON)
- Request: `{ "text": str, "source": "typed" | "voice" }`
- Response: `{ "ok": bool, "version": int, "patch": {"explanation": str, "ops": [op…]} | null, "log": [ {"model": str, "latency_ms": int, "errors": [str], "repairs": [str]} ], "message": str }`
- `log` has one entry per model call (first try plus up to 2 repairs). `errors` = why that attempt was rejected (empty if accepted); `repairs` = repair instructions sent back to the model after it. `message` = patch explanation on success, failure reason otherwise.
- After `ok: true`, the frontend re-fetches `GET /api/level` and reloads the game.

**`POST /api/label`** (JSON)
- Request: `{ "image": str (base64 PNG crop), "bbox_tiles": {"x": int, "y": int, "w": int, "h": int} }`
- Response: `{ "label": "platform"|"spikes"|"enemy"|"coin"|"double_jump"|"goal"|"player_spawn", "confidence": float 0..1, "model": str, "latency_ms": int }`

**`POST /api/transcribe`** (multipart form, field `audio` = audio file)
- Response: `{ "text": str, "latency_ms": int }`
- Backend forwards to the Argmax local server at `ARGMAX_URL` (env var).

**Existing:** `GET /api/level` → Level JSON (CLAUDE.md schema). `POST /api/level/reset` → Level JSON. `GET /api/health` → config info.

**Proposed by Ashwin; confirm with Owen:**
- `GET /api/history` → `{ "current": int, "versions": [ {"version": int, "label": str, "time": "HH:MM:SS"} ] }`
- `POST /api/undo` → `{ "ok": bool, "version": int, "message": str }` (then re-fetch `/api/level`)
- `POST /api/patch` with body `{ "explanation": str, "ops": [op…] }` → `{ "ok": bool, "version": int, "message": str }`. Lets drawing add objects without a model call, using the same validation and history.

**Stubs on main right now** (fake responses, no model calls; each marked `STUB: replaced by <task>` in `backend/main.py`):
`/api/command`, `/api/label`, `/api/transcribe`, `/api/history`, `/api/undo`, `/api/patch`. The feat/patches merge replaces `/api/command`, `/api/history`, `/api/undo` and `/api/patch`.

## In progress
| Task | Owner | Branch | Files touched |
|---|---|---|---|
| Patches + undo (feature 2) | Ashwin | `feat/patches` | backend/llm.py, backend/main.py, backend/patcher.py, backend/prompts.py. Has a prototype side panel (frontend/panel.js); Owen owns the real one, so it gets described in the PR, not merged as-is |

## Decisions log
| Time | Decision | Reason |
|---|---|---|
| 11-14 | Level in tile units, entities as a flat list with ids | Easy for a 9B model to patch by id |
| 11-14 | Patches (add/remove/move/set/set_physics), never full levels | Smaller outputs, fewer model errors, easy undo |
| 11-14 | Level state lives on backend, in memory | One source of truth for version history |
| 11-14 | Enemy patrol lives in mechanics.js from day one | Feature 3 needs the registry anyway; avoids a refactor |
| 11-14 | Phaser 3.80.1 vendored, no build step | Offline + zero tooling |
| 11-14 | All textures drawn in code (generateTexture) | No image assets to manage; offline |
| 11-14 | Hazard hitboxes are inset zones, not full tiles | Forgiving feel; spikes only hurt near the bottom |
| 11-14 | Patch Pydantic models already in schema.py | Shared contract for feature 2 |
| 11-14 | Sample level shortened to 40 wide, 4 coins (schema still allows up to 400) | Faster manual testing; still has every entity type |
| 11-14 | Two models: CODE_MODEL (Bonsai 2 9B) for patches/code, FAST_MODEL (Bonsai 2 2B) for chat/classification | Keep the slow model off simple jobs; latency matters in the demo |
| 11-14 | Branch per task + PR reviewed by the other person's session; plan.md updates go on main | Avoid stepping on each other |
| — | Vision labeling model: TBD (try FAST first) | Fill in with accuracy notes when the label endpoint is built |
| 11-14 | Serve Bonsai 2 MLX with `mlx_vlm.server` on :1234, not LM Studio | LM Studio not installed; MLX packs need mlx-vlm ≥0.7.8 (custom arch). Same OpenAI API |
| 11-14 | Model defaults in config.py = folder paths under `~/models/prism-ml` (home-relative) | mlx_vlm.server uses the path as model id; works on both Macs without editing code |
| 11-14 | mlx_vlm.server honors `response_format: json_schema` (llguidance) | Verified with a forced-enum test; patches use it |
| 11-14 | 9B patch call takes about 15–22 s (about 1.6k prompt tokens) | Measured on M3 16 GB; under the 20 s budget for a single try |
| 11-14 | Two-person split: Ashwin = backend/, Owen = frontend/ + Argmax | See CLAUDE.md "Ownership" |
| 11-14 | Stub endpoints on main matching the contracts | Owen can build the frontend before the real backend exists |

## Known issues
- One mlx_vlm.server keeps only **one model loaded at a time**. A request for the other model swaps it in (about 4 s). Mixing CODE (9B) and FAST (2B) calls will thrash; if that hurts, run a second server on another port for FAST.
- The 9B sometimes keeps a platform's width when moving it, which pushes it out of bounds ("make the gaps bigger" failed all 3 tries once). Fix on feat/patches: more specific error messages with the allowed range.
- `ARGMAX_URL` default (`http://localhost:50060/v1`) is a placeholder; Owen to confirm the real port.
- Ashwin's Mac has only about 6 GB of disk free after the model downloads.
- Game canvas is fixed 960x480; levels taller than 15 tiles scroll vertically via camera (fine), shorter ones show sky.
- Behavior errors currently only disable that behavior + log; report/rollback is P1 (model-written mechanics).

## Next up
Unclaimed. Owen: pick one.
1. **Argmax speech-to-text offline** (`feat/voice-setup`): get Argmax's local transcription server running with Wi-Fi off, set `ARGMAX_URL`, then push-to-talk with an editable transcript → `POST /api/command` with `source: "voice"`. Build against the stubs.
2. **Canvas drawing with color fallback** (`feat/draw`): new `frontend/draw.js`. Pen, group strokes, snap bounding boxes to tiles, label by pen color, then `POST /api/label` (stubbed). Send the result as `add` ops to the proposed `POST /api/patch`.

## Later
- Multiplayer
