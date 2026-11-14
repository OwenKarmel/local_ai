# plan.md — Sketch2Game

## Goal & demo story
Offline AI platformer maker. Demo (Wi-Fi off): draw a rough level → it becomes a playable Mario-style level → play it → type "make the gaps bigger" / "add three enemies near the end" → level updates → "make enemies jump toward the player" → model writes a new behavior into mechanics.js and enemies start hopping → undo if anything breaks.

## Scope
**In:** Phaser runtime + sample level; NL command → validated patch with retries + undo; model-written behaviors in mechanics.js with syntax check + runtime rollback; drawing canvas → grouped strokes → labeled (vision or pen color) → patch.
**Out (Later):** voice input (Argmax transcription), text-to-speech, playability/reachability checker, multiplayer.

## Milestones
- [x] 1. Game runtime: sample level, platforms/hazards/enemies/coins/double jump/goal, coyote time, camera, restart, win
- [ ] 2. Level editing with model: command box, patch ops (CODE_MODEL), structured output, Pydantic validation + 2 retries, side-panel log, version history + undo, model name + latency per request
- [ ] 3. Engine edits: model writes behaviors in mechanics.js, versioned, `node --check`, runtime error → report → auto-rollback (+ optional 1 repair)
- [ ] 4. Canvas drawing: pen, stroke grouping, bbox → tile snap, vision labeling (try FAST_MODEL first, CODE_MODEL only if accuracy is poor; log choice in decisions) + pen-color fallback, apply as patch

## In progress
| Task | Owner | Branch | Files touched |
|---|---|---|---|
| 2. Level editing with model | Ashwin | `feat/patches` | backend/llm.py, backend/main.py, backend/patcher.py, backend/prompts.py, frontend/index.html, frontend/game.js, frontend/panel.js |

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
| 11-14 | Branch per task + PR reviewed by the other person's session; plan.md updates go on main | Avoid stepping on each other; this rule change itself was committed straight to main |
| — | Vision labeling model: TBD (try FAST first) | Fill in during feature 4 with accuracy notes |
| 11-14 | Serve Bonsai 2 MLX with `mlx_vlm.server` on :1234, not LM Studio | LM Studio not installed; MLX packs need mlx-vlm ≥0.7.8 (custom arch). Same OpenAI API, so backend is unaffected |
| 11-14 | Model defaults in config.py = absolute folder paths under ~/models/prism-ml | mlx_vlm.server uses the path as model id |

## Known issues
- Untested: whether one mlx_vlm.server process can serve CODE_MODEL and FAST_MODEL by switching on the request's `model` field, or whether we need two servers on two ports. Check at the start of feature 2.
- Ashwin's Mac has only about 6 GB of disk free after the model downloads.
- Game canvas is fixed 960x480; levels taller than 15 tiles scroll vertically via camera (fine), shorter ones show sky.
- Behavior errors currently only disable that behavior + log; report/rollback is feature 3.

## Next up
Unclaimed. Teammate: pick one.
1. **Argmax speech setup** (`feat/voice-setup`): install and run Argmax's local transcription server and confirm it transcribes a mic clip offline. Then wire a mic button that sends audio to it and passes the transcript to `POST /api/command` with `source: "voice"`. Moved up from Later.
2. **Feature 4: canvas drawing** (`feat/draw`): new `frontend/draw.js`. Pen, group strokes, snap bounding boxes to tiles, label by pen color first, vision labeling after. Output goes in as an `add` patch through the feature 2 pipeline.

(Feature 2 is in progress on `feat/patches`. Feature 3 depends on it.)

## Later
- Voice input via Argmax local transcription → same command pipeline (`source: "voice"`)
- Text-to-speech
- Playability / reachability checker
- Multiplayer
