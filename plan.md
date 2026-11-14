# plan.md — Voice game copilot (name TBD)

**One goal:** run the demo video script below end to end, reliably, on the demo Mac (Ashwin's) with Wi-Fi off. Everything on the board serves a beat. Core principle (CLAUDE.md): nothing about what a command does is hardcoded; every command goes to Bonsai.

**Pitch:** An offline voice copilot that edits your game while you play. Rosebud AI lets you edit games by chatting with a cloud AI; we recreated that fully on-device with Bonsai (PrismML) and Argmax.

Cornell Local AI Hackathon, theme "Recreate". Submissions due noon Sunday: 2-minute video, GitHub link, one-sentence description. Top 10 do a 4-minute live demo for the PrismML and Argmax founders. Never use "Mario" or any Nintendo name in code, UI, docs, narration or captions.

## Final goal: the demo script
Acceptance checks test properties, not exact outputs, since model output varies. **The level must stay beatable after every beat.** `scripts/demo_check.py` (task 17) automates Beats 3–6.

| Beat | What happens | Acceptance check |
|---|---|---|
| 1 | Wi-Fi off shown on screen; title and pitch: "An offline voice copilot that edits your game while you play." | Wi-Fi visibly off; every later beat runs with it off |
| 2 | Play the starting level: a few obstacles, coins, stompable enemies, a flag | Level loads; it's beatable by hand; it has a gap ahead of the player for Beat 6 and open room for Beat 3 |
| 3 | "Make this harder." Bonsai decides how | `status` applied; every new or changed object is ahead of the player; the checker passes (level still beatable) |
| 4 | "Give me fireballs." Bonsai writes the ability in mechanics.js using the mechanics API | Code passes the sandbox on attempt 1 or 2; pressing its key spawns a projectile; a projectile defeats an enemy |
| 5 | Cursor visible with its tile highlighted. Hover and say "put a block here" | A new solid block occupies the cursor tile (or the nearest free tile if the cursor is on something) |
| 6 | "Make the next gap 10 tiles" is refused and explained out loud. "Let me jump higher." Then a wider-gap request that was impossible before goes through | First: `refused` with a reason naming the jump limit, and spoken. Second: jump physics increased. Third: applied, the gap is wider than the old limit and within the new one, and the checker passes |
| 7 | Reach the flag | Win screen |
| 8 | Closing stats: model size, latencies, attempts, lines of code written, evaluation results | Stats HUD and demo-check success rates on screen; all numbers measured |

## Task board
Status: `todo`, `doing (<name>)`, `in review (PR #n)`, `done`. **Claim a task by number in plan.md before starting** (status `doing (<name>)`), one branch and PR per task, keep the review workflow. Tasks marked 🍎 need the demo Mac (MLX models, Argmax, recording).

| # | Task | Beat | Depends on | Files | Done when | Status |
|---|---|---|---|---|---|---|
| 1 | Demo starting level: beatable, a few obstacles, coins, stompable enemies, a flag; a gap ahead of the start suitable for Beat 6; open room ahead for Beat 3 | 2 | — | `backend/levels/` | Beaten by hand; demo check Beats 3 and 6 have room to work | todo |
| 2 | 🍎 Argmax speech-to-text | 3–6 | — | `backend/speech.py`, `backend/main.py` | Real voice transcribes correctly with Wi-Fi off | done (PR #6). Real voice and Wi-Fi-off not verified yet |
| 3 | Hold-to-talk (button + V key, listening indicator, typed fallback) | 3–6 | 2 | `frontend/voice.js`, `frontend/index.html` | Hold V mid-run, speak, command runs | done (PR #7). Real voice through the browser not verified yet |
| 4 | Remove hardcoded command handling (see "Hardcoding audit") | all | — | `backend/intents.py`, `backend/prompts.py` | Nothing on the audit list remains | in review (PR #9) |
| 5 | Mechanics API + compact reference (one line per function) for the prompt: spawn entities and projectiles, physics bodies, velocity, collisions, input keys, timers, entity properties, tint and sprite | 4 | — | `frontend/mechanics.js` (API section), reference text for the prompt | A hand-written test ability of 10–30 lines (not shipped) works using only the API | todo |
| 6 | Model-written abilities through the sandbox: code only in mechanics.js, syntax check, runtime error capture, automatic rollback, one repair attempt with the error message | 4 | 5, 7 | `backend/` (code route, versions), `frontend/` (load, error capture, rollback) | "Give me fireballs" works on attempt 1 or 2 in at least 4 of 5 demo-check runs | todo |
| 7 | Live patch application: apply every LowLevelOp to the running scene, keeping player position, velocity, score, power-ups; never spawn on the player; fall back to reload | 3–6 | — | `frontend/game.js` | All op types apply mid-run without restart | in review |
| 8 | Cursor context: `/api/command` accepts `cursor: {x, y}` in tiles or null, passed to the model as context | 5 | — | `backend/` | "Put a block here" lands on the cursor tile in the demo check | todo |
| 9 | Cursor overlay: visible pointer plus highlighted tile, sent with every command | 5 | 8 | `frontend/` | Highlight follows the mouse; requests carry `cursor` | todo |
| 10 | Shared physics config read by game.js and the checker (gravity, jump velocity, run speed, player size, double-jump strength, coyote time, jump buffer, jump cut, max fall speed) | 6 | — | new shared file, `frontend/game.js` | Changing jump velocity in the config changes the game and the checker | todo |
| 11 | Playability checker and refusals: tile grid, jump arcs matching the game, reachability from spawn and the player position with double-jump state, specific reasons. Interface below. Test level with gaps 4/5/6/7 and heights 2/3/4 verified by hand | 3, 6 | 10 | `backend/checker.py`, `backend/levels/jump_test.json` | Sample passes; a 10-tile gap fails with a clear reason; checker matches the hand test | todo |
| 12 | Checker reads physics from the current level, so "let me jump higher" immediately changes what's allowed | 6 | 11 | `backend/checker.py` | Beat 6 passes in the demo check | todo |
| 13 | Player abilities and limits in the prompt: current reach (max gap, max height, with and without double jump) from the current physics, plus the abilities in mechanics.js | 3, 6 | 10 | `backend/prompts.py`, `backend/summary.py` | Prompt numbers change after a physics change | todo |
| 14 | 🍎 Copilot voice: `/api/speak` with TTSKit (long-running process), refusal vs normal style; immediate spoken acknowledgment ("On it") while the model works | 3–6 | 2 | `backend/`, `frontend/voice.js` | Confirmations and refusals are spoken offline; "On it" plays within 1 s of releasing V | todo |
| 15 | Stats in the `/api/command` response (contract above) | 8 | — | `backend/pipeline.py`, `backend/main.py` | Every response has `stats`; unmeasured fields are null | todo |
| 16 | Stats HUD (spec below) | 8, all | 15 | `frontend/` | Readable on video; refusal and rollback banners match what the copilot says | todo |
| 17 | Demo check script `scripts/demo_check.py` (spec below) | all | 1 | `scripts/` | `--quick`, `--full`, `--beat N --runs K` work; Beat 6 shows "waiting on checker" until 11–12 merge | todo |
| 18 | Latency work that doesn't hardcode behavior: shorter prompts, compact level summary, prompt caching if the model server supports it, keeping the model loaded and warm | all | — | `backend/prompts.py`, `backend/summary.py`, server flags | Median command latency measured before and after | todo |
| 19 | 🍎 Offline run of the full flow on the demo Mac | 1 | 2, 3, 14 | — | Every beat runs with Wi-Fi off | todo |
| 20 | 🍎 Backup take, as soon as Beats 2–5 work (before the checker is done) | all | 3, 6, 7, 9 | — | Rough take recorded | todo |
| 21 | 🍎 Final video (best of several takes) and submission | all | everything above | — | Video by 10:30am Sunday, submitted by 11:30am | todo |

### Stats HUD spec (task 16)
In a corner of the game, large and readable on video:
- **Latest change:** transcript, what changed in plain words, model, latency (big, colored: green under 5 s, yellow under 15 s, red above), attempt number, ops count, code lines, checker and sandbox results.
- **History:** the last few changes with their latencies.
- **Persistent badge:** "Offline · Bonsai 2 4B · 1.9 GB".
- **On refusal or rollback:** a clear red banner with the reason, matching what the copilot says.
- **"Show code" toggle:** displays the code the model just wrote.

### Demo check spec (task 17)
`scripts/demo_check.py` runs Beats 3–6 in order against the live backend, with realistic player and cursor positions, and checks each beat's acceptance properties. Prints progress as it goes, so it can run in the background.
- `--quick`: one pass. Run after every merge.
- `--full`: 5 passes with a success rate per beat. Run before recording and after prompt or API changes.
- `--beat N --runs K`: repeat one beat while working on it.

Testing only: during the demo each command runs once, with a retry only if the first attempt fails. **If a beat fails more than 1 time in 5, fix the API, the prompt context or the examples, never by hardcoding. If it still fails Sunday morning, cut the beat rather than fake it.**

### Checker interface (task 11 → pipeline)
The checker lives in `backend/checker.py`; the pipeline calls it, so the two can be built in parallel.
```python
def check(level: dict, player: dict | None) -> dict:
    """level = Level.model_dump(); player = {"x", "y", "has_double_jump"} in tiles, or None.
    Returns {"ok": bool, "reason": str | None, "spoken": str | None}.
    reason: specific, e.g. "gap2 is 8 tiles wide; the longest jump with current physics is 5 tiles."
    spoken: one short sentence for the copilot, e.g. "Can't do that: you could only jump 5 tiles."
    Physics numbers come from the shared config (A3), never hardcoded."""
```

**Parallel work:** tasks 5, 7, 9, 10, 11 and 16 run on any machine (`STUB_SPEECH=1`; commands need a model server, e.g. Ashwin's over the local network). Coordination points: the shared physics config (10 → 11, 12, 13), the checker interface above, the mechanics-code op (5 ↔ 6 ↔ 7), and `cursor` (8 ↔ 9).


## Later
Not needed for any beat. Don't start these until every beat passes.
- Second-voice features: SpeakerKit chaos mode, speaker permissions (old O5, A7)
- Companion character
- Canvas drawing and vision labeling of sketches
- Deterministic difficulty ladder (old A10). Removed: it conflicts with the core principle
- Sword, bow and other hand-written abilities. Abilities are model-written
- Fast route on a separate 2B server (only if latency work isn't enough)

## Recording plan
**Length:** 2 minutes max. Record on the demo Mac at the venue; background noise shows the speech works in a real room.

| Time | Shot |
|---|---|
| 0:00–0:10 | Wi-Fi off on screen. Title and one-line pitch |
| 0:10–0:25 | Play the starting level: stomp an enemy, grab a coin |
| 0:25–0:40 | "Make this harder." Changes appear ahead; copilot says what it added; HUD shows model and latency |
| 0:40–0:55 | "Give me fireballs." Toggle "show code" briefly to show the lines Bonsai wrote; blast the new enemies |
| 0:55–1:10 | Hover over a spot: "put a block here." Block appears on the highlighted tile |
| 1:10–1:30 | "Make the next gap 10 tiles": refused out loud with the reason. "Let me jump higher." The wider gap now goes through within the new limit |
| 1:30–1:45 | Reach the flag |
| 1:45–2:00 | Stats: model size, latency history, attempts, code lines, demo-check success rates, "all on-device" |

**Rules:**
- Every result comes from a real model run. Record several full takes and use the best one.
- Cut waiting time in editing, but keep latency badges visible so the cuts are honest. Optionally a small "sped up" or "trimmed" note during cuts.
- Never use "Mario" or Nintendo names in narration, titles or captions.
- Short narration or captions explaining each beat in one line.
- **For PrismML:** show model size, latency, first-try success rate, and why we chose the 4B (matched the 9B's accuracy at about 1.6× the speed).
- **For Argmax:** show the transcript appearing with its latency, and the copilot speaking back, with a different tone for refusals.
- Record a rough backup take (task 20) as soon as Beats 2–5 work, before the checker is done.

**Live finals (4–5 minutes):** same beats in the same order, plus one command from the judges if time allows. Talk over waits ("it's writing the fireball code now").

## Milestones
| When | What |
|---|---|
| Midnight Saturday | Beats 1–5 pass the demo check; backup take recorded |
| 9:00am Sunday | Feature freeze; tag `demo-v1`; `demo_check.py --full` |
| 10:30am Sunday | Final video |
| 11:30am Sunday | Submitted (hard deadline noon) |

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
- Request: `{ "text": string, "source": "typed" | "voice", "speaker": string | null, "player": { "x": number, "y": number, "has_double_jump": boolean } | null, "cursor": { "x": number, "y": number } | null }`
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
| 11-14 17:40 | **Keyword stub removed** (`STUB_COMMANDS`, `backend/stub_commands.py`). `/api/command` always goes to Bonsai | Canned keyword answers masked what the model actually does and drifted from the real pipeline (e.g. "make it shoot slower" errored in stub mode only) |
| 11-14 16:40 | Deterministic ladder (old A10) removed; `"ladder"` removed from `route` | Prebuilt difficulty steps are hardcoded behavior |
| 11-14 16:40 | Pre-written fireball ability to be removed (task 4); abilities are model-written in mechanics.js through the sandbox (tasks 5–6) | Same principle. `set_ability` stays as a generic settings op |
| 11-14 16:40 | `/api/command` request gains `cursor: {x, y} \| null`; response gains `stats` (only measured numbers, null otherwise) | Beat 5 needs the cursor tile; Beat 8 and the HUD need honest stats |
| 11-14 16:40 | Prompt examples must not match demo commands | Otherwise the demo shows memorized examples, not generality |
| 11-14 16:10 | **Intent reply: `plan` (was `explanation`) is required and comes before `ops`; `ops` needs at least one item** | Constrained decoding writes required fields first, so the optional explanation came after the ops as a justification. Planning first fixed op choice on the 2B, and empty `ops` cost a retry. Old `explanation` replies still parse |
| 11-14 16:10 | Op selection uses a low-temperature sampler (`temperature 0.2`, no presence penalty); chat keeps the Bonsai defaults | Picking from a fixed menu wants the most likely reading; presence penalty punishes the repeated tokens JSON needs |
| 11-14 16:10 | **New intent ops `add_platform` (over a gap, region or platform) and `add_pickup` (`double_jump`)**. Building blocks: code computes placement | With no op for them, the model substituted coins for platforms and fireballs or gravity for double jumps, and reported success |
| 11-14 16:10 | `set_property` rejects physics keys, and props on objects with no behaviors (props are only read by behaviors) | "lower the gravity" wrote `props.gravity` onto a platform and reported success |


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
- `Sketch2Game.loadLevel()` restarts the scene, losing position and score, until O3.
- Argmax server quirks: `model` form field required but ignored; `temperature=0` returns 500 (`0.0` works). Handled in `backend/speech.py`; worth reporting to Argmax.
- Ashwin's Mac is very low on disk (about 3 GB free after Argmax). The TTS 1.7b model (about 2.5 GB) doesn't fit; use 0.6b.
- The code still uses the working name `Sketch2Game` (page title, `window.Sketch2Game`). Rename once the final name is picked.
