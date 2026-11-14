# plan.md — Voice game copilot (name TBD)

## Summary and pitch
Cornell Local AI Hackathon, theme "Recreate": rebuild an existing AI app to run fully on-device. Must use Bonsai (PrismML) and Argmax, and run with Wi-Fi off.

**Pitch:** Rosebud AI lets you edit games by chatting with an AI in the cloud. We recreated that as an offline voice copilot that edits the game live while you play.

You hold V and say "lower the gravity", "make this harder" or "give me fireballs". The running platformer changes without restarting. The copilot answers out loud, and it refuses any change that would make the level impossible, explaining why.

Team: Ashwin (backend, checker) and Owen (frontend, Argmax). Final project name TBD. Never use "Mario" or any Nintendo name in the repo, UI or docs.

## Demo script
1. Start playing the sample level. "Lower the gravity." Jumps get floatier mid-run; the copilot confirms out loud.
2. "Give me fireballs." Shoot the next enemy.
3. "Make this harder." Hazards or enemies appear ahead; the copilot says what it added.
4. "Make the next gap 10 tiles." The copilot refuses and explains why; the HUD shows the reason.
5. (If built) A friend joins in chaos mode and adds enemies by voice; the player still reaches the flag.
6. Show Wi-Fi off and the latency/eval table.

## Milestones
| When | What |
|---|---|
| Midnight Saturday (Nov 14) | All P0 merged; backup demo video recorded (J2) |
| 9:00am Sunday | Feature freeze; tag `demo-v1` |
| 10:30am Sunday | Final 2-minute video (J3) |
| 11:30am Sunday | Submitted (video, GitHub link, one-sentence description). Hard deadline is noon |

## Interface contracts (source of truth)
Exact field names and types. A change needs a decisions-log entry and a heads-up to the other person.

### `POST /api/transcribe`
- Request: multipart form, field `audio` = audio file.
- Response: `{ "text": string, "latency_ms": number, "speaker": string | null }`
- `speaker` is `null` until SpeakerKit chaos mode (O5) exists; then `"player"`, `"friend"`, or an enrolled name.

### `POST /api/command`
- Request: `{ "text": string, "source": "typed" | "voice", "speaker": string | null }`
- Response:
```
{
  "ok": boolean,                          // true only when status is "applied"
  "status": "applied" | "refused" | "error",
  "version": number,                      // level version after this command (unchanged if refused/error)
  "route": "fast" | "level",
  "model": string,
  "latency_ms": number,                   // total backend time
  "patch": LowLevelOp[],                  // concrete ops for live apply; empty if refused or error
  "level": Level,                         // full level after the change (fallback reload + reconciliation)
  "spoken": string,                       // one short sentence for the copilot to say
  "reason": string | null,                // refusal or error details for the HUD; null when applied
  "log": [ { "step": string, "model": string | null, "latency_ms": number, "errors": string[], "repairs": string[] } ]
}
```
- `log.step` is one of `"route"`, `"model"`, `"convert"`, `"check"`. `model` is `null` for steps with no model call.

### `LowLevelOp` (the frontend must apply each of these live)
- `{ "op": "set_physics", "key": "gravity" | "jump_velocity" | "run_speed", "value": number }`
- `{ "op": "set_ability", "ability": string, "settings": object }`. Example: `"fireball"` with `{ "enabled": true, "key": "F", "speed": 420, "cooldown_ms": 400, "bounces": 2, "kills": true }`. A9 finalizes the fireball fields.
- `{ "op": "add_entity", "entity": Entity }`. Full entity object with `id`, `type`, `x`, `y`, `w`, `h`, `behaviors`, `props`.
- `{ "op": "remove_entity", "id": string }`
- `{ "op": "update_entity", "id": string, "changes": object }`. `changes` is a partial Entity: any of `x`, `y`, `w`, `h`, `behaviors`, `props`. `props` is merged key by key; the other fields are replaced.

### `POST /api/speak`
- Request: `{ "text": string, "style": "normal" | "refusal" | "hype" }`
- Response: audio (wav) or `{ "audio_url" }`. **Owen decides, then documents it here.** The stub returns `audio/wav` bytes directly.
- Argmax's local server serves transcription; TTSKit may need a small Swift wrapper or a CLI call per utterance. Owen picks the simplest reliable approach.

### Unchanged
- `GET /api/level` → `Level` (schema in CLAUDE.md; now has an optional `abilities` object).
- `POST /api/undo` → `{ "ok": boolean, "version": number, "message": string }`. Then re-fetch `GET /api/level`.
- `POST /api/level/reset` → `Level`. `GET /api/history` → `{ "current": number, "versions": [ { "version": number, "label": string, "time": "HH:MM:SS" } ] }`. `GET /api/health` → config info.

### Stubs on main
Every one is marked `STUB: replaced by <task ID>` in `backend/main.py`. No model calls.
- `/api/command` returns canned responses by keyword in `text`, checked in this order:

| Text contains | Result |
|---|---|
| "impossible" or "10 tiles" | `refused`, with reason and spoken message |
| "gravity" | `applied`, fast route, `set_physics` gravity lowered by 300 (floor 400) |
| "fireball" | `applied`, fast route, `set_ability` fireball enabled |
| "remove" | `applied`, `remove_entity` of the first enemy (`refused` if none left) |
| "faster" | `applied`, `update_entity` on every enemy (`props.speed` +40) |
| "gap" | `applied`, `update_entity` on `ground2` (first gap one tile wider) |
| "enemy" | `applied`, `add_entity` enemy at x 8, then 19, 26, 36 on repeat calls |
| anything else | `error` |

  The stub really applies its ops to an in-memory level, so `level`, `version`, `GET /api/level` and undo stay consistent. It sleeps 0.6 s (fast) or 2 s (level) so "thinking" UI can be tested. The real level route currently takes 9 to 15 s.
- `/api/transcribe` returns `"lower the gravity"`, `speaker: null`.
- `/api/speak` returns a 0.25 s beep wav; pitch differs per style.
- `/api/undo` and `/api/history` work against the stub's version stack.

### Open contract questions (not in the contract yet; need a decision)
- **Player position.** "Next gap", "ahead of me", "near_player" and "make this harder" need to know where the player is, and the backend doesn't. Proposal: add `"player": { "x": number, "y": number, "has_double_jump": boolean } | null` (tile units) to the `/api/command` request. The checker also needs it to test reachability from where the player is standing, not only from spawn.
- **Undo while playing.** `/api/undo` returns no level, so the frontend must re-fetch and reconcile live. Could return `level` like `/api/command` does.

## Task board
Status: `todo`, `doing`, `in review`, `done`. Update when a PR opens or merges. Branch = lowercased task ID plus a short name (e.g. `a2-intent-ops`).

### Ashwin (backend)
| ID | Title | Pri | Depends on | Files | Done when | Status |
|---|---|---|---|---|---|---|
| A1 | Finish feat/patches PR 1: new `/api/command` shape, clear errors, deterministic fixes (clamp to bounds, nudge overlaps) before model retry, max 1 model retry | P0 | — | backend/ | "add three enemies near the end" applies and returns the full contract | in review as PR #1 (`feat/patches`); pipeline works, response shape is still the old contract |
| A2 | Intent-level ops: level summary for the model (platforms, gaps, regions with ids and widths); ops like widen_gap, shrink_platform, add_enemy(region or near_player), add_hazard_near, set_physics, set_ability. Backend converts to LowLevelOps and keeps everything in bounds | P0 | A1 | backend/ | "make the gaps bigger" succeeds on first try and stays in bounds | mostly built in PR #1 (passes on 9B, 4B, 2B). Missing: LowLevelOp output names, set_ability, near_player |
| A3 | Shared physics config: one file read by game.js and the checker (player size, double-jump strength, coyote time, jump buffer, jump cut, max fall speed, default gravity/jump/run) | P0 | heads-up to Owen | new shared file, backend/, small game.js change | changing jump velocity in the config changes the game and the checker | todo |
| A4 | Command router: "fast" (settings, abilities) uses FAST_MODEL with a tiny prompt; "level" (geometry, entities) uses CODE_MODEL with the level summary | P0 | A1 | backend/ | "lower the gravity" returns in a few seconds on the fast route | todo |
| A5 | Playability checker and refusals: tile grid, jump arcs matching real game physics (coyote time, variable jump), reachability from spawn with double-jump state, specific failure reasons, refusal through the contract. Runs on every patch, including physics changes. Verified against a test level with gaps 4/5/6/7 and heights 2/3/4 confirmed by hand in the game | P0 | A3 | backend/ | sample level passes, the 10-tile gap fails with a clear reason, checker answers match the hand test | todo |
| A6 | Player abilities in the prompt: current reach (max gap, max height, with and without double jump) computed from the shared config, in every level-route prompt, plus safe ways to make levels harder | P0 | A3, A5 | backend/ | prompt shows correct numbers after a physics change | todo |
| A7 | Speaker permissions for chaos mode: if speaker is "friend", allow only harder-making ops; refuse helpful ones with a spoken reason | P1 | O5, A5 | backend/ | friend's "remove the enemies" is refused out loud | todo |
| A8 | Eval script and table: 20 commands across both routes; valid rate, refusal correctness, latency per model (2B, 4B, 9B); markdown table for the demo | P1 | A4, A5 | backend/ | table generated | started: 10-command version in PR #1 |
| A9 | Fireball ability backend: schema for `abilities.fireball` (enabled, key, speed, cooldown_ms, bounces, kills) and ops support | P2 | A2 | backend/ | "give me fireballs" returns a valid set_ability | todo |

### Owen (frontend and voice)
| ID | Title | Pri | Depends on | Files | Done when | Status |
|---|---|---|---|---|---|---|
| O1 | Argmax speech-to-text offline: WhisperKit via the Argmax local server; `/api/transcribe` forwards to it (`ARGMAX_URL`). The one small backend/ edit Owen owns; keep it minimal. Time-box 2 hours; escalate blockers to the Argmax team in Discord | P0 | — | backend/main.py (transcribe only) | a recorded clip returns correct text with Wi-Fi off | todo |
| O2 | Hold-to-talk while playing: hold V to record, release to send. Game keeps running (also try brief slow motion or pause; pick what feels better). HUD shows "listening", the transcript, "thinking" | P0 | stubs | frontend/ | voice command reaches `/api/command` mid-run | todo |
| O3 | Live patch application: apply every LowLevelOp to the running scene without restart, keeping player position, velocity, score, power-ups. Never spawn anything overlapping the player; shift it. Fall back to full reload from `level` if live apply throws | P0 | stubs | frontend/game.js | all stubbed commands apply live mid-run | todo |
| O4 | Copilot voice: `/api/speak` using TTSKit; speak every response; `style` for refusals vs normal. Pre-download the TTS model | P0 | — | backend/main.py (speak only), frontend/ | the copilot speaks confirmations and refusals offline | todo |
| O5 | SpeakerKit chaos mode: enroll two voices (player, friend); return `speaker` in `/api/transcribe`; HUD shows who spoke | P1 | O1 | backend/main.py (transcribe), frontend/ | two voices are told apart | todo |
| O6 | Copilot HUD: change log (what changed, model, latency), refusal banner, version number, undo reachable while playing | P1 | O3 | frontend/ | visible during play | todo |
| O7 | Fireball runtime: press the configured key to shoot in the facing direction; cooldown, bounce, kills enemies, removed on wall hit. Reads `abilities.fireball` from the level | P2 | O3, A9 | frontend/ | fireball kills an enemy | todo |
| O8 | Sprites and effects: one CC0 Kenney pack in `frontend/assets/sprites/`, sprite catalog, player animations, tiled platforms, optional per-entity `sprite` and `tint`, particle effects | P1 | touches game.js, so coordinate with O3 | frontend/, schema (optional fields) | sample level renders and plays with sprites, offline | in review as PR #2 (branch `o8-sprites`, done from Ashwin's session at Ashwin's request) |

### Both
| ID | Title | Pri | Done when | Status |
|---|---|---|---|---|
| J1 | Offline test: full flow with Wi-Fi off on the demo Mac; fix anything that needs network | P0 | demo script runs offline | todo |
| J2 | Backup demo video | P1 | recorded by midnight Saturday | todo |
| J3 | Final video and submission | P0 | video by 10:30am Sunday, submitted by 11:30am | todo |

**Parallel work:** A1, A2, A4, A5, A6 touch only backend/. O1 to O4 can be built entirely against the stubs. Coordination points: A3 (shared config; game.js reads it), A7/O5 (`speaker`), O8/O3 (both edit game.js), and the open player-position question above.

## Decisions log
| Time | Decision | Reason |
|---|---|---|
| 11-14 | Level in tile units, entities as a flat list with ids | Easy for a small model to refer to by id |
| 11-14 | Patches, never full levels | Smaller outputs, fewer model errors, easy undo |
| 11-14 | Level state lives on backend, in memory | One source of truth for version history |
| 11-14 | Enemy patrol lives in mechanics.js | Behavior registry in one file |
| 11-14 | Phaser 3.80.1 vendored, no build step | Offline + zero tooling |
| 11-14 | Hazard hitboxes are inset zones, not full tiles | Forgiving feel |
| 11-14 | Sample level is 40 wide with 4 coins | Faster manual testing; still has every entity type |
| 11-14 | Two models: CODE_MODEL (Bonsai 2 9B), FAST_MODEL (Bonsai 2 2B) | Keep the slow model off simple jobs |
| 11-14 | Serve Bonsai 2 MLX with `mlx_vlm.server` on :1234, not LM Studio | MLX packs need mlx-vlm ≥0.7.8. Same OpenAI API |
| 11-14 | Model defaults are folder paths under `~/models/prism-ml` | mlx_vlm.server uses the path as model id; works on both Macs |
| 11-14 | mlx_vlm.server honors `response_format: json_schema` | Verified with a forced-enum test |
| 11-14 | Two-person split: Ashwin = backend/, Owen = frontend/ + Argmax | See CLAUDE.md "Ownership" |
| 11-14 | **Pivot to a voice copilot that edits the game live while you play** | One clear idea; voice at the center (strong use of Argmax); the guardrail is the technical centerpiece |
| 11-14 | **Canvas drawing and vision labeling dropped** | Not needed for the new direction |
| 11-14 | **The model chooses intent; deterministic code does geometry.** Model sees a level summary and emits ops like widen_gap / add_enemy; backend computes coordinates | 9B kept breaking bounds with raw coordinates ("make the gaps bigger" failed 3/3). With intents: 10/10 applied on first call on 9B, 4B and 2B |
| 11-14 | **Jump physics in ONE shared config file** read by game.js and the checker (A3) | No "keep in sync" rule to forget |
| 11-14 | **Routing by model size:** fast route (FAST_MODEL, tiny prompt) for settings and abilities; level route (CODE_MODEL, level summary) for geometry and entities | Latency. Reading the 1,760-token level prompt is most of a level command's time |
| 11-14 | **Playability checker required on every change**, including physics changes. Refusals come back through the contract with a spoken reason | The copilot can change anything but can never make the level unbeatable |
| 11-14 | New `/api/command` contract: status, route, model, latency, `LowLevelOp[]` patch, full `level`, `spoken`, `reason`, step log. New `/api/speak`. `speaker` on transcribe and command | Live apply, voice out, chaos mode |
| 11-14 | Level schema gains optional `abilities: {name: settings}` (default `{}`) | `set_ability` needs somewhere to live; old levels still validate |
| 11-14 | New optional `FAST_BASE_URL` (defaults to `BONSAI_BASE_URL`) | One mlx_vlm.server holds one model; swapping costs about 4 s. A second server for the fast model avoids that |
| 11-14 | Intent-format eval, 10 commands (from PR #1): 9B 10/10 applied, 8/8 correct, median 15.0 s. 4B 10/10, 8/8, 9.5 s. 2B 10/10, 6/8, 4.1 s | 4B matched 9B's accuracy at about 1.6× the speed. Open decision: make 4B the level-route model |
| 11-14 | Stub `/api/command` applies its canned ops to a real in-memory level | `level`, `version` and undo stay consistent for frontend testing |

## Dropped
Kept in the repo for now; remove in a cleanup PR.
- **Canvas drawing.** No drawing code was ever written on main or any branch. Leftover: the `POST /api/patch` stub in `backend/main.py` (and a real version on `feat/patches`, which is still useful as a no-model debug endpoint).
- **Vision labeling of sketches.** Leftover: the `POST /api/label` stub and its models in `backend/main.py`.
- **Prototype side panel** on branch `proto/panel` (old contract; reference only).
- **Not on the board:** model-written behaviors in mechanics.js with rollback (the old "feature 3"). The rule that model-written code may only go in mechanics.js stays.

## Known issues
- **Level-route latency is 9 to 15 s** with the game running. The player moves a long way in that time.
- One mlx_vlm.server keeps only one model loaded; alternating fast and level routes swaps models (about 4 s each) unless `FAST_BASE_URL` points at a second server.
- Nothing stops an unbeatable edit until A5 merges.
- game.js hardcodes the jump constants (coyote 100 ms, jump buffer 100 ms, double jump 0.9×, jump cut 0.85, player 24×30, max fall 1200) until A3.
- `Sketch2Game.loadLevel()` restarts the scene, losing position and score, until O3.
- `ARGMAX_URL` default (`http://localhost:50060/v1`) is a placeholder; Owen to confirm.
- Ashwin's Mac has about 6 GB of disk free.
- The code still uses the working name `Sketch2Game` (page title, `window.Sketch2Game`). Rename once the final name is picked.
