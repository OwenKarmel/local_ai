# plan.md — Callout

**One goal:** make the demo video work and look great end to end on the demo Mac with Wi-Fi off. Stop training, batch evaluation, and model experiments; test features by playing in the browser. Every command still goes to Bonsai. Add general building blocks the model can choose from; hand-designed level content such as the boss is fine.

**Pitch:** Callout is an offline voice copilot that edits a 2D platformer while you play. Hold V → Argmax speech-to-text → Bonsai 2 (4B, escalating to 9B for code) → backend validates and applies changes → the game updates live. Everything runs on-device with Wi-Fi off.

## Final goal: demo video beats

| Beat | What happens | Acceptance check |
|---|---|---|
| 1 | Level 1: “add more enemies” | Bonsai adds enemies; level remains playable |
| 2 | “make it dusk and give me camo” | Dusk scene and animated pixel-camo alien apply live |
| 3 | Enter level 2: boss fight | Boss cannot be stomped, takes several fireball hits, shoots on a timer, and player respawns at the checkpoint before it |
| 4 | “give me fireball powers” | Model-written projectiles look fiery and defeat the boss after several hits |
| 5 | “put us on the moon, low gravity” | Moon scene and lower gravity apply in the same command |
| 6 | Dodge across moving platforms | Horizontal and vertical platforms carry the player without visible sliding or jitter |
| 7 | Hold V to talk | Pixel microphone icon with V lights while listening |
| 8 | Command completes | Subtle gray result box shows latency and model path, then fades; visible in `?demo` |
| 9 | Reach a level goal | Multicolor confetti bursts on every level win |

## Task board

One branch and PR per task. Acceptance is playing the feature in the browser. No batch evals or model experiments.

| # | Task | Beat | Files | Done when | Status |
|---|---|---|---|---|---|
| 1 | General fiery projectile API and visuals | 4 | `frontend/mechanics.js`, `frontend/sprites.js`, `backend/codegen.py` | Glow, flicker, Phaser trail and impact burst support model-written fireballs | browser checked; model call pending |
| 2 | Boss fight and checkpoint respawn | 3–4 | `frontend/game.js`, `frontend/mechanics.js`, `backend/levels/boss.json` | Fireball-only multi-hit boss shoots; a hit respawns before boss | browser checked |
| 3 | General moving platforms | 6 | `frontend/game.js`, `backend/summary.py`, `backend/intents.py`, `backend/levels/boss.json` | Any platform can use horizontal or vertical movement; rider stays stable | browser checked (32 samples, 0.01 px gap range) |
| 4 | Moon and dusk backgrounds; combined moon + gravity | 2, 5 | `backend/looks.py`, `backend/schema.py`, `backend/prompts.py`, `frontend/looks.js` | Model can select themes and combine moon with physics changes | browser checked via live patch; model call pending |
| 5 | Camo player sprite | 2 | `frontend/assets/`, `tools/build_catalog.py` | Animated camo sprite is selectable from the catalog | browser checked |
| 6 | Proportional grow power-up | — | `frontend/game.js` | Width and height scale together and body matches | browser checked (38.4×48 body) |
| 7 | Pixel V microphone icon | 7 | `frontend/game.js`, `frontend/voice.js` | Listening state works in normal and demo modes | browser checked in `?demo` |
| 8 | Fading command result box | 8 | `frontend/game.js`, `frontend/voice.js` | Latency and model path visible in normal and demo modes | browser checked in `?demo` |
| 9 | Generic confetti win effect | 9 | `frontend/sprites.js`, `frontend/game.js` | Multicolor Phaser particles burst on each win | browser checked; 120 particles |

## Later
Not needed for any beat. Don't start these until every beat passes.
- **Full playability checker** (old tasks 10–12: shared physics config, reachability search, checker reads current physics). Cut from the demo 11-14 21:30; task 13's gap check covers the main risk. Its planned interface:
  The checker lives in `backend/checker.py`; the pipeline calls it, so the two can be built in parallel.
  ```python
  def check(level: dict, player: dict | None) -> dict:
      """level = Level.model_dump(); player = {"x", "y", "has_double_jump"} in tiles, or None.
      Returns {"ok": bool, "reason": str | None, "spoken": str | None}.
      reason: specific, e.g. "gap2 is 8 tiles wide; the longest jump with current physics is 5 tiles."
      spoken: one short sentence for the copilot, e.g. "Can't do that: you could only jump 5 tiles."
      Physics numbers come from the shared config (A3), never hardcoded."""
  ```

- Second-voice features: SpeakerKit chaos mode, speaker permissions (old O5, A7)
- Companion character
- Canvas drawing and vision labeling of sketches
- Deterministic difficulty ladder (old A10). Removed: it conflicts with the core principle
- Sword, bow and other hand-written abilities. Abilities are model-written
- Fast route on a separate 2B server (only if latency work isn't enough)

## Recording plan
**Length:** 2 minutes max. Show Wi-Fi off, play the starting level, speak each beat naturally, and leave the latency/model result visible long enough to read. Record several browser playthroughs and use the best take. Keep all latency badges honest; trim waits in editing only when appropriate.

**Live finals:** show the same beats in order, then take one open-ended judge command if time allows. Avoid rehearsed command-to-result scripting; each command goes to Bonsai.

## Hardcoding audit (removal is task 4)
Found on main, 11-14 16:40:
- `backend/intents.py`: a pre-written fireball ability. `FIREBALL_DEFAULTS`, `FIREBALL_LIMITS`, `set_ability` restricted to `"fireball"`, and its compiler. Abilities must be model-written code.
- `backend/prompts.py`: the worked example "make this harder and give me fireballs", which matches two demo beats, and the `set_ability` fireball line in the ops list.
- `backend/prompts.py`: the rule "Harder: wider gaps (+1)… Easier: narrower gaps…", which maps one command to fixed levers. To be replaced by generic context (player limits, task 13).
- plan.md: the deterministic ladder (old A10) and the `route: "ladder"` contract value. Removed in this PR.
- Keyword stubs (`backend/stub_commands.py`, `STUB_COMMANDS=1`) removed 11-14. The intent ops (widen_gap, add_enemy, …) and the "ahead of the player" rule are building blocks used by many commands.

## Interface contracts (source of truth)
Exact field names and types. A change needs a decisions-log entry and a heads-up to the other person.

### `POST /api/transcribe`
- Request: multipart form, field `audio` = audio file.
- Response: `{ "text": string, "latency_ms": number, "speaker": string | null }`
- Accepts wav, m4a, mp3, flac and webm/opus (what browsers record); the backend converts and pads short clips. If Argmax is down: HTTP 503 `{ "detail": string }`. With `STUB_SPEECH=1`: fixed text.
- `speaker` is `null` until SpeakerKit chaos mode (O5) exists; then `"player"`, `"friend"`, or an enrolled name.

### `POST /api/command`
- Request: `{ "text": string, "source": "typed" | "voice", "speaker": string | null, "player": { "x": number, "y": number, "has_double_jump": boolean, "is_big": boolean } | null, "cursor": { "x": number, "y": number } | null }`
- `cursor`: the tile under the mouse pointer (tiles, x right, y down), or `null`. Passed to the model as context ("put a block here"). Task 8.
- `player`: the tile containing the player's center (x right, y down), or `null` when not playing. The backend uses it for "near_player", "ahead of me", "the next gap" and "make this harder": while playing, edits land ahead of the player and things fully behind the player are left alone.
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
  "log": [ { "step": string, "model": string | null, "latency_ms": number, "errors": string[], "repairs": string[] } ],
  "stats": {                              // task 15. Only measured numbers; null when not measured
    "model": string, "model_size_gb": number | null, "latency_ms": number, "attempts": number,
    "ops_count": number, "code_lines": number | null, "tokens_in": number | null, "tokens_out": number | null,
    "tokens_per_sec": number | null, "checker": "passed" | "refused" | "not run",
    "sandbox": "passed" | "rolled back" | "not run", "offline": true
  }
}
```
- `log.step` is one of `"route"`, `"model"`, `"convert"`, `"check"`. `model` is `null` for steps with no model call. `convert.repairs` lists automatic fixes; `convert.errors` lists what couldn't be applied.
- `patch` is computed as the difference between the old and new level, so it is exactly what was applied: removes first, then updates, then adds, then physics and abilities.
- Until the playability checker (A5) exists, `"refused"` is used only when the request can't be expressed with the edit operations (e.g. "make me invisible"). `reason` and `spoken` say so.

### `LowLevelOp` (the frontend must apply each of these live)
- `{ "op": "set_physics", "key": "gravity" | "jump_velocity" | "run_speed", "value": number }`
- `{ "op": "set_ability", "ability": string, "settings": object }`. Settings for an ability whose code the model wrote in mechanics.js. There are no pre-written abilities.
- **Proposed (task 6):** an op that delivers new model-written mechanics code to the running game, e.g. `{ "op": "set_mechanics", "version": number, "code": string }`. Task 6 finalizes it and logs the decision.
- `{ "op": "add_entity", "entity": Entity }`. Full entity object with `id`, `type`, `x`, `y`, `w`, `h`, `behaviors`, `props`.
- `{ "op": "remove_entity", "id": string }`
- `{ "op": "update_entity", "id": string, "changes": object }`. `changes` is a partial Entity: any of `x`, `y`, `w`, `h`, `behaviors`, `props`. `props` is merged key by key; the other fields are replaced. Also `sprite`, `tint`, `look` (replaced whole).
- `{ "op": "set_player_look", "look": PlayerLook }`, `{ "op": "set_scene", "scene": SceneLook }`, `{ "op": "set_reactions", "reactions": Reaction[] }`. Visual only; each carries the full new value (models in `backend/schema.py`), applied live by `frontend/looks.js`.

### `GET /api/stage`, `POST /api/stage` (levels in sequence)
- `GET` → `{ "index": number, "count": number, "names": string[] }`. Stage 0 = sample level, stage 1 = Boss Arena.
- `POST { "index": number }` → `{ "ok": boolean, "index", "count", "names", "level": Level }`. `ok` false if the index doesn't exist (then nothing changes).
- Each stage keeps its own version stack. `GET /api/level`, `/api/command`, `/api/undo`, `/api/history` and `/api/level/reset` act on the **active** stage; edits to a stage are kept when you leave it. Reset restores only the active stage.
- `/api/command` response gains `"stage": number` (the stage it edited). The frontend ignores a patch whose `stage` isn't the loaded one.

### Command traces (debugging the harness)
- `/api/command` response gains `"trace_id": string | null`. Every command is saved to `backend/data/traces/<trace_id>.json` (gitignored): input, player, level before, full prompt + schema, each model attempt (raw reply, usage, parsed intent, errors, repairs, patch), outcome. Harness crashes are saved too (`status: "crash"`).
- `GET /api/traces?limit=50&failures=false` → `{ "traces": [summary] }`, newest first. `failures=true` = error/refused/crash or flagged.
- `GET /api/traces/{id}` → the full trace (404 if unknown).
- `POST /api/traces/{id}/flag` `{ "note": string }` → summary. The in-game "👎 Wrong result" button calls it for the last command.
- CLI: `python -m backend.traces [--failures]`, `... show <id|substring> [--prompt]`, `... replay <id|substring> [--model PATH]`.

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
- `/api/command` is always real: it needs the model server. If it's unreachable: `status: "error"` ("Model server not reachable"). The keyword stub was removed.
- `/api/transcribe` returns `"lower the gravity"`, `speaker: null`.
- `/api/speak` returns a 0.25 s beep wav; pitch differs per style.

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
| 11-14 | **Level schema: entities gain optional `sprite` (catalog name) and `tint` (hex color)**, default null (O8) | Lets the copilot say "make the enemies blue" or "use ice balls". Old levels still validate |
| 11-14 | Art is Kenney "New Platformer Pack 1.1", CC0; only used sprites committed (about 200 KB) | One consistent style, public domain, works offline |
| 11-14 | Sprite skins never change physics bodies (player 24×30, enemy 28×24) | The playability checker's numbers must not depend on art |
| 11-14 | Stub `/api/command` applies its canned ops to a real in-memory level | `level`, `version` and undo stay consistent for frontend testing |
| 11-14 15:00 | **`/api/command` request gains `player: {x, y, has_double_jump} \| null`** (tiles) | "near_player", "ahead of me", "the next gap" and "make this harder" need the player's position; the checker will need it too |
| 11-14 15:00 | **One model for everything: the 4B for both routes on one server** (CODE_MODEL and FAST_MODEL default to the 4B). Routing code and FAST_BASE_URL stay, so the fast route can move to the 2B on a second server later | Earlier eval (10 commands): 4B 10/10 applied, 8/8 correct, median 9.5 s; 9B 10/10, 8/8, 15.0 s. Same accuracy at about 1.6× the speed, and no model swapping |
| 11-14 15:00 | **`/api/undo` returns `{ok, version, level}`** | The frontend can apply undo live without a second request |
| 11-14 15:00 | `patch` is a diff of old vs new level, not a log of edit steps | Always exactly what was applied, compact (one update per entity), in contract op names |
| 11-14 15:00 | While playing, edits to things fully behind the player are skipped (logged as a repair) | The 4B sped up an enemy behind the player for "make this harder"; the code enforces "ahead" instead of trusting the prompt |
| 11-14 15:00 | Spoken reply is built from what was actually applied, not from the model's text | It can't claim changes that didn't happen |
| 11-14 15:00 | Model may return at most 6 ops (JSON schema `maxItems`); gap size always via widen_gap | "make the level harder" took 43 s with a long op list; "make the first gap smaller" picked the wrong op |
| 11-14 15:00 | `STUB_COMMANDS=1` env var keeps the keyword stub available | Frontend work without a model server |
| 11-14 17:40 | **Keyword stub removed** (`STUB_COMMANDS`, `backend/stub_commands.py`). `/api/command` always goes to Bonsai | Canned keyword answers masked what the model actually does and drifted from the real pipeline (e.g. "make it shoot slower" errored in stub mode only) |
| 11-14 15:00 | 4B eval with the new contract, 14 commands: 14/14 applied on the first model call, 12/12 intent checks, median 16.2 s (this run: decode 27 tok/s, prefill 219 tok/s, 2,207-token prompt). An earlier run of the same code minus the prompt fixes had a median of 12.0 s (37 and 287 tok/s); the Mac was slower on the second run | Accuracy is good; latency is the problem (see Known issues) |
| 11-14 15:10 | **Task split by machine:** Ashwin takes Mac-only work (O1, O4, A4, A6, J1, and recording J2/J3); Owen takes A3 (shared physics config) and A5 (playability checker) plus O2, O3, O6, O7. IDs kept, owners changed | Owen has no Mac. Argmax and Bonsai MLX only run on Apple silicon, and Ashwin's Mac is the demo machine. A3 and A5 are pure Python/JS and need no models |
| 11-14 15:10 | Checker interface: `check(level, player) -> {ok, reason, spoken}` in `backend/checker.py` | Owen owns the checker, Ashwin owns the pipeline; a function boundary keeps them out of each other's files |
| 11-14 15:20 | **New task A10: precomputed difficulty ladder** (Ashwin, P1). "Make this harder" / "make it easier" are answered from checker-verified steps prepared in the background, with no model call | These are the most common live commands and the demo's centerpiece. A model call takes 9–25 s; a stored step can apply in under 200 ms, and pre-verification means it can never make the level unbeatable |
| 11-14 15:45 | Speech-to-text runs on `argmax-cli serve` (argmax-oss-swift, built from source) on port 50060; `/api/transcribe` forwards to it | Same OpenAI audio API we planned for; `ARGMAX_URL` default already matched |
| 11-14 15:45 | Demo STT model: Whisper large-v3 626MB (about 0.8 s per command through the backend); base.en (about 0.1 s) as fallback | Both got 5/5 test commands right (synthetic `say` voice). large-v3 has better punctuation and should be more robust to real voices and room noise; 0.8 s is small next to the 9–25 s model step. Confirm with real voice |
| 11-14 15:45 | Backend pads audio to 2 s and converts to 16 kHz WAV with ffmpeg | Whisper returned empty text for the 0.9 s "make this harder"; webm from browsers isn't readable by WhisperKit |
| 11-14 15:45 | `STUB_SPEECH=1` keeps the fixed-text transcribe stub | Owen's Acer has no Argmax |
| 11-14 15:45 | TTS: `argmax-cli tts --model 0.6b` can write WAV (24 kHz) or play; warm load 0.5 s, first audio 0.14 s, about real time. For `/api/speak` (O4), keep a long-running TTS process instead of one CLI call per sentence (about 7 s each) | Measured |
| 11-14 15:30 | No loaner Mac for Owen; O5 (SpeakerKit) goes to Ashwin | Owen works on an Acer laptop; SpeakerKit needs Apple silicon |
| 11-14 15:20 | **Contract: `route` gains the value `"ladder"`** in the `/api/command` response | Ladder answers aren't fast-route or level-route model calls; the HUD and eval should show them separately. The frontend should treat unknown route values as display-only. The backend type changes when A10 lands |
| 11-14 16:40 | **One goal: the demo video script, end to end, on the demo Mac with Wi-Fi off.** Board replaced by one numbered list in beat order, no owners; claim by number | Focus. Everything not serving a beat moves to "Later" |
| 11-14 16:40 | **Core principle: nothing about what a command does is hardcoded.** Every command goes to Bonsai; our code provides building blocks, context, guardrails, measurement, and an immediate spoken acknowledgment | Judges may try their own commands at the finals; the system must stay general |
| 11-14 16:40 | Deterministic ladder (old A10) removed; `"ladder"` removed from `route` | Prebuilt difficulty steps are hardcoded behavior |
| 11-14 16:40 | Pre-written fireball ability to be removed (task 4); abilities are model-written in mechanics.js through the sandbox (tasks 5–6) | Same principle. `set_ability` stays as a generic settings op |
| 11-14 16:40 | `/api/command` request gains `cursor: {x, y} \| null`; response gains `stats` (only measured numbers, null otherwise) | Beat 5 needs the cursor tile; Beat 8 and the HUD need honest stats |
| 11-14 16:40 | Prompt examples must not match demo commands | Otherwise the demo shows memorized examples, not generality |
| 11-14 21:30 | **Full playability checker and the refusal beat cut from the demo.** Beat 6 is now "make the platforms move" (model-written behavior through the sandbox) followed by "let me jump higher". The checker tasks (10–12) moved to Later; Owen told (the task was unclaimed) | Not enough time to build and hand-verify a reachability checker before Sunday; model-written behavior is a stronger demo of the core idea |
| 11-14 21:30 | **Lightweight safety layer instead** (task 13, `backend/reach.py`): the backend computes max jump distance and height from the current level's physics and puts them in every prompt; a patch that makes a gap wider than the max jump is rejected with a reason, retried once, then refused. Movement constants (coyote 100 ms, player 24 px, double jump 0.9×) are mirrored from game.js ("keep in sync") since the shared config was cut | Covers the most likely way an edit makes the level unbeatable. Default physics: 5-tile gaps, 4-tile ledges (9 / 7 with double jump), computed and not hand-verified |
| 11-14 21:30 | Prompt: for a vague command every op's `asked` quotes the whole command | The 4B paraphrased ("increase enemy speed"), `drop_unasked` dropped every op, and "make this harder" ended up refused (3/3). After the rule: applied ahead of the player, 2/2 |
| 11-14 16:10 | **Intent reply: `plan` (was `explanation`) is required and comes before `ops`; `ops` needs at least one item** | Constrained decoding writes required fields first, so the optional explanation came after the ops as a justification. Planning first fixed op choice on the 2B, and empty `ops` cost a retry. Old `explanation` replies still parse |
| 11-14 16:10 | Op selection uses a low-temperature sampler (`temperature 0.2`, no presence penalty); chat keeps the Bonsai defaults | Picking from a fixed menu wants the most likely reading; presence penalty punishes the repeated tokens JSON needs |
| 11-14 16:10 | **New intent ops `add_platform` (over a gap, region or platform) and `add_pickup` (`double_jump`)**. Building blocks: code computes placement | With no op for them, the model substituted coins for platforms and fireballs or gravity for double jumps, and reported success |
| 11-14 | **New entity type `grow`** (default sprite `powerup_mushroom_red`); `add_pickup` kind gains `grow`; `/api/command` `player` gains optional `is_big` (default false) | Second powerup: taller player with a different look (catalog `player_big`, body 28×48) that survives one hazard/enemy hit by shrinking. Old levels and requests still validate |
| 11-14 17:20 | **Boss level as stage 2.** Levels play in order (`/api/stage`), one version stack per stage; `/api/command` response gains `stage`. Boss = an `enemy` 2×2 with behavior `boss` in mechanics.js (two phases from props: hp, phase2_at, speeds, jump_every, shoot_every, shot_speed). New building blocks: enemy `props.hp` (multi-hit + HP bar), enemy body scales with `w`/`h`, goal `props.locked_by`, `scene.spawnEnemyShot`, `scene.damageEnemy`, `scene.solidAt`. Behavior prop ranges in `summary.BEHAVIOR_PROPS`: listed in the summary, clamped by `set_property` | Bonsai reconfigures the boss with the same ops as any level (set_property, platforms, hazards, enemies, physics); nothing boss-specific in the pipeline |
| 11-14 17:20 | While playing, a moving enemy (one with behaviors) counts as spanning the platform it walks on for "behind the player" | The boss roams the arena; its JSON x is only its start tile, so edits to it were skipped once the player passed that tile |
| 11-14 18:00 | **Command traces:** every `/api/command` saves a JSON snapshot (backend/data/traces/, gitignored); response gains `trace_id`; new `/api/traces*` endpoints and a "👎 Wrong result" flag button; `python -m backend.traces` lists, shows and replays them | Failures (including applied-but-wrong) need the exact prompt, raw replies and level to fix the harness; replay reruns the same input after a fix. Additive, no client changes required |
| 11-14 18:20 | **Visual-only looks.** Intent ops `set_look` (object id or group), `set_scene` (sky, overlay, weather, filters, zoom), `add_reaction`/`remove_reaction` (event → effect), in `backend/looks.py`. Level gains optional `player_look`, `scene`, `reactions`; Entity gains optional `look`; LowLevelOp gains `set_player_look`, `set_scene`, `set_reactions`. Frontend: `frontend/looks.js` | Players ask for looks as often as gameplay changes. Building blocks (any color, size, effect, theme), never gameplay: no checker needed. Old levels and patches still validate |
| 11-14 18:20 | **Every intent op starts with `asked`**: the command's words it carries out. `drop_unasked` removes ops whose quote isn't from the command (all dropped → retry) | The model added extras nobody asked for ("make me big" also got a tint and faster running) |
| 11-14 16:10 | `set_property` rejects physics keys and unknown props with no runtime reader; known platform motion props (`motion_dx`, `motion_dy`, `motion_period`) are general engine options | Keeps model edits meaningful while allowing any platform to move |
| 11-14 | `SceneLook.background` supports `default`, `dusk`, and `moon`; moon also adds stars and cratered, cool-tinted ground | Makes reusable scene themes selectable by Bonsai; theme setting composes with physics changes |
| 11-14 | Model-written fiery projectiles use `api.projectile(..., {fire:true})` for Kenney art, glow, flicker, trail and impact burst | General visual building block; the model still writes attack timing and behavior |
| 11-14 | Grow body scales uniformly by 1.6× (24×30 → 38.4×48) | Art and collision body grow in both axes |
| 11-14 | Public browser global and page title renamed to `Callout` | Product name is consistent in the game, API and docs |
| 11-14 | Mic HUD uses a recognizable microphone emoji, with a red muted state and green listening state; V remains visible | Makes the push-to-talk state easy to read on video |
| 11-14 | Every level win emits 120 multicolor Phaser confetti particles | A generic visual celebration tied to the reusable win event |


## Dropped
Kept in the repo for now; remove in a cleanup PR.
- **Canvas drawing.** No drawing code was ever written on main or any branch. Leftover: the `POST /api/patch` stub in `backend/main.py` (and a real version on `feat/patches`, which is still useful as a no-model debug endpoint).
- **Vision labeling of sketches.** Leftover: the `POST /api/label` stub and its models in `backend/main.py`.
- **Prototype side panel** on branch `proto/panel` (old contract; reference only).
- **Not on the board:** model-written behaviors in mechanics.js with rollback (the old "feature 3"). The rule that model-written code may only go in mechanics.js stays.

## Known issues
- **Commands take 9 to 25 s on the 4B** (most of it reading a 2,200-token prompt). The player moves a long way in that time. Biggest wins: the fast route with a tiny prompt (A4), a shorter level prompt, prompt prefix caching.
- Until task 11, a command can still make the level unbeatable (e.g. "make this harder" can widen the next gap to 6).
- `add_hazard_near` on a ground platform puts spikes one tile in from the landing edge; after a gap is widened, the spikes can end up on the first tile. Harsh but legal until the checker exists.
- One mlx_vlm.server keeps only one model loaded; alternating fast and level routes swaps models (about 4 s each) unless `FAST_BASE_URL` points at a second server.
- Nothing stops an unbeatable edit until A5 merges.
- game.js hardcodes the jump constants (coyote 100 ms, jump buffer 100 ms, double jump 0.9×, jump cut 0.85, player 24×30, max fall 1200) until A3.
- `Callout.loadLevel()` restarts the scene, losing position and score, until O3.
- Argmax server quirks: `model` form field required but ignored; `temperature=0` returns 500 (`0.0` works). Handled in `backend/speech.py`; worth reporting to Argmax.
- Ashwin's Mac is very low on disk (about 3 GB free after Argmax). The TTS 1.7b model (about 2.5 GB) doesn't fit; use 0.6b.
