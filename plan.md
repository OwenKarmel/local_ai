# plan.md — Sketch2Game

## Goal & demo story
Offline AI platformer maker. Demo (Wi-Fi off): draw a rough level → it becomes a playable Mario-style level → play it → type "make the gaps bigger" / "add three enemies near the end" → level updates → "make enemies jump toward the player" → model writes a new behavior into mechanics.js and enemies start hopping → undo if anything breaks.

## Scope
**In:** Phaser runtime + sample level; NL command → validated patch with retries + undo; model-written behaviors in mechanics.js with syntax check + runtime rollback; drawing canvas → grouped strokes → labeled (vision or pen color) → patch.
**Out (Later):** voice input (Argmax transcription), text-to-speech, playability/reachability checker, multiplayer.

## Milestones
- [ ] 1. Game runtime: sample level, platforms/hazards/enemies/coins/double jump/goal, coyote time, camera, restart, win
- [ ] 2. Level editing with model: command box, patch ops, structured output, Pydantic validation + 2 retries, side-panel log, version history + undo, latency display
- [ ] 3. Engine edits: model writes behaviors in mechanics.js, versioned, `node --check`, runtime error → report → auto-rollback (+ optional 1 repair)
- [ ] 4. Canvas drawing: pen, stroke grouping, bbox → tile snap, vision labeling + pen-color fallback, apply as patch

## In progress
| Task | Owner | Files touched |
|---|---|---|
| 1. Game runtime | Ashwin | backend/*, frontend/index.html, frontend/game.js, frontend/mechanics.js, frontend/vendor/ |

## Decisions log
| Time | Decision | Reason |
|---|---|---|
| 11-14 | Level in tile units, entities as a flat list with ids | Easy for a 9B model to patch by id |
| 11-14 | Patches (add/remove/move/set/set_physics), never full levels | Smaller outputs, fewer model errors, easy undo |
| 11-14 | Level state lives on backend, in memory | One source of truth for version history |
| 11-14 | Enemy patrol lives in mechanics.js from day one | Feature 3 needs the registry anyway; avoids a refactor |
| 11-14 | Phaser 3.80.1 vendored, no build step | Offline + zero tooling |

## Known issues
- (none yet)

## Next up
1. Feature 1: game runtime (claimed)
2. Feature 2: command box + `/api/command` + patch apply + undo
3. Feature 2b: LLM client (`backend/llm.py`) with JSON-schema response format + retry loop

## Later
- Voice input via Argmax local transcription → same command pipeline (`source: "voice"`)
- Text-to-speech
- Playability / reachability checker
- Multiplayer
