# testbonsai

Local test setup for running Ternary-Bonsai-2-9B with an Open WebUI frontend (WSL2, GTX 1650 4 GB).

## Contents
- `start-llama-server.sh`: llama-server (CUDA build) serving `bonsai-9b`, 16k context, full GPU offload, at `http://127.0.0.1:8080/v1`.
- `start-openwebui.sh`: Open WebUI at `http://localhost:3000`, pointed at the llama-server. Uses `uv` to provide Python 3.11.

Both scripts expect a `~/localAI` directory containing the llama.cpp CUDA/CPU builds (`bin-cuda/`), CUDA libs (`libs/`), `tools/uv/uv`, and `models/Ternary-Bonsai-2-9B-PQ2_0.gguf`. None of those are committed (weights, binaries and chat data stay out of git).

## Run
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
