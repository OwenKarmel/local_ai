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

Notes if asked: "make this harder" / "make it easier" come off a difficulty ladder (A10). Its steps are prepared in the background and verified by the checker, so they apply instantly. Custom requests go to Bonsai live.

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
- Request: `{ "text": string, "source": "typed" | "voice", "speaker": string | null, "player": { "x": number, "y": number, "has_double_jump": boolean } | null }`
- `player`: the tile containing the player's center (x right, y down), or `null` when not playing. The backend uses it for "near_player", "ahead of me", "the next gap" and "make this harder": while playing, edits land ahead of the player and things fully behind the player are left alone.
- Response:
```
{
  "ok": boolean,                          // true only when status is "applied"
  "status": "applied" | "refused" | "error",
  "version": number,                      // level version after this command (unchanged if refused/error)
  "route": "fast" | "level" | "ladder",   // "ladder" = precomputed difficulty step (A10), no model call
  "model": string,
  "latency_ms": number,                   // total backend time
  "patch": LowLevelOp[],                  // concrete ops for live apply; empty if refused or error
  "level": Level,                         // full level after the change (fallback reload + reconciliation)
  "spoken": string,                       // one short sentence for the copilot to say
  "reason": string | null,                // refusal or error details for the HUD; null when applied
  "log": [ { "step": string, "model": string | null, "latency_ms": number, "errors": string[], "repairs": string[] } ]
}
```
- `log.step` is one of `"route"`, `"model"`, `"convert"`, `"check"`. `model` is `null` for steps with no model call. `convert.repairs` lists automatic fixes; `convert.errors` lists what couldn't be applied.
- `patch` is computed as the difference between the old and new level, so it is exactly what was applied: removes first, then updates, then adds, then physics and abilities.
- Until the playability checker (A5) exists, `"refused"` is used only when the request can't be expressed with the edit operations (e.g. "make me invisible"). `reason` and `spoken` say so.

### `LowLevelOp` (the frontend must apply each of these live)
- `{ "op": "set_physics", "key": "gravity" | "jump_velocity" | "run_speed", "value": number }`
- `{ "op": "set_ability", "ability": string, "settings": object }`. Example: `"fireball"` with `{ "enabled": true, "key": "F", "speed": 420, "cooldown_ms": 400, "bounces": 2, "kills": true }`. A9 finalizes the fireball fields.
- `{ "op": "add_entity", "entity": Entity }`. Full entity object with `id`, `type`, `x`, `y`, `w`, `h`, `behaviors`, `props`.
- `{ "op": "remove_entity", "id": string }`
- `{ "op": "update_entity", "id": string, "changes": object }`. `changes` is a partial Entity: any of `x`, `y`, `w`, `h`, `behaviors`, `props`. `props` is merged key by key; the other fields are replaced.

### `POST /api/speak`
- Request: `{ "text": string, "style": "normal" | "refusal" | "hype" }`
- Response: audio (wav) or `{ "audio_url" }`. **Ashwin decides (O4), then documents it here.** The stub returns `audio/wav` bytes directly; the frontend should handle that shape.
- Argmax's local server serves transcription; TTSKit may need a small Swift wrapper or a CLI call per utterance. Ashwin picks the simplest reliable approach.

### Unchanged
- `GET /api/level` → `Level` (schema in CLAUDE.md; now has an optional `abilities` object).
- `POST /api/undo` → `{ "ok": boolean, "version": number, "level": Level }`. `ok` is false when there is nothing to undo (then `level` is the current level). Apply `level` directly; no re-fetch needed.
- `POST /api/level/reset` → `Level`. `GET /api/history` → `{ "current": number, "versions": [ { "version": number, "label": string, "time": "HH:MM:SS" } ] }`. `GET /api/health` → config info.

### Stubs
Marked `STUB: replaced by <task ID>` in `backend/main.py`. No model calls.
- `/api/command` is real (needs the model server). **With `STUB_COMMANDS=1` it returns canned responses instead** (`backend/stub_commands.py`), by keyword in `text`, checked in this order:

| Text contains | Result |
|---|---|
| "impossible" or "10 tiles" | `refused`, with reason and spoken message |
| "gravity" | `applied`, fast route, `set_physics` gravity lowered by 300 (floor 400) |
| "fireball" | `applied`, fast route, `set_ability` fireball enabled |
| "remove" | `applied`, `remove_entity` of the first enemy (`refused` if none left) |
| "faster" | `applied`, `update_entity` on every enemy (`props.speed` +40) |
| "gap" | `applied`, `update_entity` on `ground2` (first gap one tile wider) |
| "enemy" | `applied`, `add_entity` enemy 3 tiles ahead of `player`, or at x 8, then 19, 26, 36 without a player |
| anything else | `error` |

  The stub really applies its ops to the in-memory level, so `level`, `version`, `GET /api/level` and undo stay consistent. It sleeps 0.6 s (fast) or 2 s (level) so "thinking" UI can be tested. The real command takes 9 to 25 s on the 4B.
- `/api/transcribe` returns `"lower the gravity"`, `speaker: null`.
- `/api/speak` returns a 0.25 s beep wav; pitch differs per style.

## Task board
Status: `todo`, `doing`, `in review`, `done`. Update when a PR opens or merges. Branch = lowercased task ID plus a short name (e.g. `a4-router`).

**Why the split:** Owen doesn't have a Mac. Argmax (speech-to-text, TTS) and our Bonsai MLX models only run on Apple silicon, and Ashwin's Mac is the demo machine. So Mac-only work is Ashwin's and Owen takes work that runs on any machine. IDs are unchanged so old references still work; moved tasks say where they came from.

Owen has no Mac and no loaner. He is working on an Acer laptop. All Mac-only work (MLX models, Argmax, demo recording) is Ashwin's.

### Ashwin (Mac required)
| ID | Title | Pri | Depends on | Files | Done when | Status |
|---|---|---|---|---|---|---|
| A1 | Finish PR #1 contract conversion: new `/api/command` shape, clear errors, deterministic fixes before model retry, max 1 model retry | P0 | — | backend/ | "add three enemies near the end" applies and returns the full contract | done (PR #1 merged) |
| A2 | Intent-level ops: level summary for the model; widen_gap, shrink_platform, add_enemy(region / near_player), add_hazard_near, set_physics, set_ability. Backend converts to LowLevelOps and keeps everything in bounds | P0 | A1 | backend/ | "make the gaps bigger" succeeds on first try and stays in bounds | done (PR #1 merged) |
| O1 (was Owen's) | Argmax speech-to-text offline: WhisperKit via the Argmax local server; `/api/transcribe` forwards to it (`ARGMAX_URL`). Time-box 2 hours; escalate blockers to the Argmax team in Discord | P0 | — | backend/main.py, CLAUDE.md setup | a recorded clip returns correct text with Wi-Fi off | todo |
| O4 (was Owen's) | Copilot voice: `/api/speak` using TTSKit; `style` for refusals vs normal; pre-download the TTS model. Owen's frontend plays whatever `/api/speak` returns (the stub already returns wav) | P0 | — | backend/main.py, CLAUDE.md setup | the copilot speaks confirmations and refusals offline | todo |
| A4 | Command router: "fast" (settings, abilities) gets a tiny prompt; "level" (geometry, entities) gets the level summary. Both use the 4B for now | P0 | A1 | backend/ | "lower the gravity" returns in a few seconds on the fast route | todo |
| A6 | Player abilities in the prompt: current reach (max gap, max height, with and without double jump) computed from the shared config, in every level-route prompt, plus safe ways to make levels harder | P0 | A3, A5 | backend/ | prompt shows correct numbers after a physics change | todo |
| A7 | Speaker permissions for chaos mode: if speaker is "friend", allow only harder-making ops; refuse helpful ones with a spoken reason | P1 | O5, A5 | backend/ | friend's "remove the enemies" is refused out loud | todo |
| A8 | Eval script and table: 20 commands across both routes; valid rate, refusal correctness, latency per model; markdown table for the demo | P1 | A4, A5 | backend/ | table generated | started: 14-command version merged with PR #1 |
| A9 | Fireball ability backend: schema for `abilities.fireball` and ops support | P2 | A2 | backend/ | "give me fireballs" returns a valid set_ability | mostly done in PR #1 (set_ability with fireball defaults) |
| O5 | SpeakerKit chaos mode: enroll two voices (player, friend); return `speaker` in `/api/transcribe`; HUD shows who spoke. Needs a Mac, so Ashwin | P1 | O1 | backend/main.py (transcribe), frontend/ | two voices are told apart | todo |
| A10 | Precomputed difficulty ladder. Keep a short ladder of relative difficulty steps ready at all times (e.g. harder 1–3, easier 1–2). Steps are relative ops resolved against the player's position at apply time ("next gap +1 tile", "one enemy 6 tiles ahead", "enemies 20% faster", "remove nearest enemy ahead"), not finished levels. Generated deterministically from difficulty knobs (gap width, enemy count and speed, hazards); no model calls by default (later, optionally, Bonsai picks or orders steps from the generated options). Each step is verified with the checker before it's stored; only beatable steps go on the ladder. Rebuilt in the background after every applied change and discarded whenever the level changes. The router sends "make this harder", "make it easier" and close variants to the ladder; everything else goes to Bonsai as before. Logs route `"ladder"` with latency; `spoken` says what changed, like any edit | P1 | A5 (checker) for verification; fits inside A4's routing | `backend/ladder.py` (new), hook in the command router; adds `"ladder"` to `route` in `backend/main.py` | "make this harder" and "make it easier" apply in under 200 ms, the result passes the checker, and changes land ahead of the player | todo |
| J1 | Offline test: full flow with Wi-Fi off on the demo Mac (Ashwin's); fix anything that needs network | P0 | everything P0 | — | demo script runs offline | todo |

### Owen (any machine)
| ID | Title | Pri | Depends on | Files | Done when | Status |
|---|---|---|---|---|---|---|
| O2 | Hold-to-talk while playing: hold V to record, release to send. Build against the `/api/transcribe` stub. Game keeps running (also try brief slow motion or pause). HUD shows "listening", the transcript, "thinking" | P0 | stubs | frontend/ | voice command reaches `/api/command` mid-run | todo |
| O3 | Live patch application: apply every LowLevelOp to the running scene without restart, keeping player position, velocity, score, power-ups. Never spawn anything overlapping the player; shift it. Fall back to full reload from `level` if live apply throws. Biggest frontend task | P0 | stubs (`STUB_COMMANDS=1`) | frontend/game.js | all stubbed commands apply live mid-run | todo |
| O6 | Copilot HUD: change log (what changed, model, latency), refusal banner, version number, undo reachable while playing | P1 | O3 | frontend/ | visible during play | todo |
| A3 (was Ashwin's) | Shared physics config: ONE file read by game.js and the checker (gravity, jump velocity, run speed, player size, double-jump strength, coyote time, jump buffer, jump cut, max fall speed). Owen picks the location (e.g. `shared/physics.json`); if the backend must serve it, describe the one-line `main.py` change in the PR | P0 | heads-up to Ashwin | new shared file, frontend/game.js | changing jump velocity in the config changes the game and the checker | todo |
| A5 (was Ashwin's) | Playability checker and refusals (pure Python, no models): tile grid, jump arcs matching the real game physics (coyote time, variable jump), reachability from spawn and from the player's position with double-jump state, specific failure reasons. Verified against a test level with gaps 4/5/6/7 and heights 2/3/4 confirmed by hand in the game. Interface below; Ashwin wires it into the pipeline | P0 | A3 | `backend/checker.py` (new), `backend/levels/jump_test.json`, tests | sample level passes, the 10-tile gap fails with a clear reason, checker answers match the hand test | todo |
| O7 | Fireball runtime: press the configured key to shoot in the facing direction; cooldown, bounce, kills enemies, removed on wall hit. Reads `abilities.fireball` | P2 | O3, A9 | frontend/ | fireball kills an enemy | todo |
| O8 | Sprites and effects (done from Ashwin's session at Ashwin's request) | P1 | coordinate with O3 (both edit game.js) | frontend/, schema (optional fields) | sample level renders and plays with sprites, offline | in review as PR #2, waiting on Owen's review |

### Both
| ID | Title | Pri | Done when | Status |
|---|---|---|---|---|
| J2 | Backup demo video, recorded on Ashwin's Mac | P1 | recorded by midnight Saturday | todo |
| J3 | Final video (recorded on Ashwin's Mac) and submission | P0 | video by 10:30am Sunday, submitted by 11:30am | todo |

### Checker interface (A5 → pipeline)
Owen writes `backend/checker.py`; Ashwin calls it from `backend/pipeline.py`, so neither edits the other's file.
```python
def check(level: dict, player: dict | None) -> dict:
    """level = Level.model_dump(); player = {"x", "y", "has_double_jump"} in tiles, or None.
    Returns {"ok": bool, "reason": str | None, "spoken": str | None}.
    reason: specific, e.g. "gap2 is 8 tiles wide; the longest jump with current physics is 5 tiles."
    spoken: one short sentence for the copilot, e.g. "Can't do that: you could only jump 5 tiles."
    Physics numbers come from the shared config (A3), never hardcoded."""
```

**Parallel work:** Ashwin's tasks and Owen's tasks touch different files. Coordination points: A3 (shared config: game.js and the checker read it), the checker interface above, A7/O5 (`speaker`), O8/O3 (both edit game.js).

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
| 11-14 15:00 | **`/api/command` request gains `player: {x, y, has_double_jump} \| null`** (tiles) | "near_player", "ahead of me", "the next gap" and "make this harder" need the player's position; the checker will need it too |
| 11-14 15:00 | **One model for everything: the 4B for both routes on one server** (CODE_MODEL and FAST_MODEL default to the 4B). Routing code and FAST_BASE_URL stay, so the fast route can move to the 2B on a second server later | Earlier eval (10 commands): 4B 10/10 applied, 8/8 correct, median 9.5 s; 9B 10/10, 8/8, 15.0 s. Same accuracy at about 1.6× the speed, and no model swapping |
| 11-14 15:00 | **`/api/undo` returns `{ok, version, level}`** | The frontend can apply undo live without a second request |
| 11-14 15:00 | `patch` is a diff of old vs new level, not a log of edit steps | Always exactly what was applied, compact (one update per entity), in contract op names |
| 11-14 15:00 | While playing, edits to things fully behind the player are skipped (logged as a repair) | The 4B sped up an enemy behind the player for "make this harder"; the code enforces "ahead" instead of trusting the prompt |
| 11-14 15:00 | Spoken reply is built from what was actually applied, not from the model's text | It can't claim changes that didn't happen |
| 11-14 15:00 | Model may return at most 6 ops (JSON schema `maxItems`); gap size always via widen_gap | "make the level harder" took 43 s with a long op list; "make the first gap smaller" picked the wrong op |
| 11-14 15:00 | `STUB_COMMANDS=1` env var keeps the keyword stub available | Frontend work without a model server |
| 11-14 15:00 | 4B eval with the new contract, 14 commands: 14/14 applied on the first model call, 12/12 intent checks, median 16.2 s (this run: decode 27 tok/s, prefill 219 tok/s, 2,207-token prompt). An earlier run of the same code minus the prompt fixes had a median of 12.0 s (37 and 287 tok/s); the Mac was slower on the second run | Accuracy is good; latency is the problem (see Known issues) |
| 11-14 15:10 | **Task split by machine:** Ashwin takes Mac-only work (O1, O4, A4, A6, J1, and recording J2/J3); Owen takes A3 (shared physics config) and A5 (playability checker) plus O2, O3, O6, O7. IDs kept, owners changed | Owen has no Mac. Argmax and Bonsai MLX only run on Apple silicon, and Ashwin's Mac is the demo machine. A3 and A5 are pure Python/JS and need no models |
| 11-14 15:10 | Checker interface: `check(level, player) -> {ok, reason, spoken}` in `backend/checker.py` | Owen owns the checker, Ashwin owns the pipeline; a function boundary keeps them out of each other's files |
| 11-14 15:20 | **New task A10: precomputed difficulty ladder** (Ashwin, P1). "Make this harder" / "make it easier" are answered from checker-verified steps prepared in the background, with no model call | These are the most common live commands and the demo's centerpiece. A model call takes 9–25 s; a stored step can apply in under 200 ms, and pre-verification means it can never make the level unbeatable |
| 11-14 15:30 | No loaner Mac for Owen; O5 (SpeakerKit) goes to Ashwin | Owen works on an Acer laptop; SpeakerKit needs Apple silicon |
| 11-14 15:20 | **Contract: `route` gains the value `"ladder"`** in the `/api/command` response | Ladder answers aren't fast-route or level-route model calls; the HUD and eval should show them separately. The frontend should treat unknown route values as display-only. The backend type changes when A10 lands |

## Dropped
Kept in the repo for now; remove in a cleanup PR.
- **Canvas drawing.** No drawing code was ever written on main or any branch. Leftover: the `POST /api/patch` stub in `backend/main.py` (and a real version on `feat/patches`, which is still useful as a no-model debug endpoint).
- **Vision labeling of sketches.** Leftover: the `POST /api/label` stub and its models in `backend/main.py`.
- **Prototype side panel** on branch `proto/panel` (old contract; reference only).
- **Not on the board:** model-written behaviors in mechanics.js with rollback (the old "feature 3"). The rule that model-written code may only go in mechanics.js stays.

## Known issues
- **Commands take 9 to 25 s on the 4B** (most of it reading a 2,200-token prompt). The player moves a long way in that time. Biggest wins: the fast route with a tiny prompt (A4), a shorter level prompt, prompt prefix caching.
- Until A5, a command can still make the level unbeatable (e.g. "make this harder" can widen the next gap to 6).
- `add_hazard_near` on a ground platform puts spikes one tile in from the landing edge; after a gap is widened, the spikes can end up on the first tile. Harsh but legal until the checker exists.
- One mlx_vlm.server keeps only one model loaded; alternating fast and level routes swaps models (about 4 s each) unless `FAST_BASE_URL` points at a second server.
- Nothing stops an unbeatable edit until A5 merges.
- game.js hardcodes the jump constants (coyote 100 ms, jump buffer 100 ms, double jump 0.9×, jump cut 0.85, player 24×30, max fall 1200) until A3.
- `Sketch2Game.loadLevel()` restarts the scene, losing position and score, until O3.
- `ARGMAX_URL` default (`http://localhost:50060/v1`) is a placeholder; Ashwin confirms in O1.
- Ashwin's Mac has about 6 GB of disk free.
- The code still uses the working name `Sketch2Game` (page title, `window.Sketch2Game`). Rename once the final name is picked.
