# testbonsai

Local setup for running Ternary-Bonsai-2 (2B or 9B) on a non-Mac machine (WSL2, GTX 1650 4 GB): drives the game's `/api/command`, plus an optional Open WebUI chat frontend.

## Contents
- `run-game.sh [2b|9b] [--no-think]` (default 2b; `--no-think` sets `NO_THINKING=1` so the model skips its reasoning phase): starts llama-server with that model (unless one already serves it) and the game backend pointed at it. Every command goes to the model; there is no stub mode.
- `start-llama-server.sh [2b|9b]`: llama-server (CUDA build) serving `bonsai-2b` (default) or `bonsai-9b`, 16k context, full GPU offload, at `http://127.0.0.1:8080/v1`.
- `start-openwebui.sh`: Open WebUI at `http://localhost:3000`, pointed at the llama-server. Uses `uv` to provide Python 3.11.

Both scripts expect a `~/localAI` directory containing the llama.cpp CUDA/CPU builds (`bin-cuda/`), CUDA libs (`libs/`), `tools/uv/uv`, and `models/Ternary-Bonsai-2-{2B,9B}-PQ2_0.gguf`. None of those are committed (weights, binaries and chat data stay out of git).

## Run
Game (then open http://localhost:8000):
```
testbonsai/run-game.sh         # 2B (default); pass 9b for the slower, more accurate model
testbonsai/run-game.sh --no-think   # skip model reasoning: "add two enemies near the end" took 5-6 s vs 13-17 s
```
Chat UI only:
```
~/localAI/start-llama-server.sh &
~/localAI/start-openwebui.sh &
```
Check the model server with `curl http://127.0.0.1:8080/health` (expect `{"status":"ok"}`).

## Notes from testing
- Open WebUI's first launch failed with `Invalid Wheel-Version in WHEEL file: None` (corrupted cached `nvidia-nccl-cu13` / `nvidia-cusolver` wheels from an interrupted download). Fix: `uv cache clean`, then relaunch (re-downloads about 9 GB).
- Replies were slow on the 4 GB GPU (about 98 tokens/s prompt processing). Open WebUI's background requests (title, tags, follow-ups, autocomplete, query generation) compete with the reply, so `start-openwebui.sh` disables them via `ENABLE_*_GENERATION=false`.
- Long chats resend the whole history each turn; start a new chat when it slows down.
- Stale queued requests after restarting the UI can stall the model for a while; they clear on their own.
- Do not use `pkill -f "open-webui serve"` from a shell whose own command line contains that string; it kills the calling shell.
