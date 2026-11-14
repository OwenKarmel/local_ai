#!/usr/bin/env bash
# llama-server backend: Ternary-Bonsai-2-9B, 16k context, full GPU offload.
# OpenAI-compatible API at http://127.0.0.1:8080/v1
set -euo pipefail
ROOT="$HOME/localAI"
export LD_LIBRARY_PATH="$ROOT/libs/gomp/usr/lib/x86_64-linux-gnu:$ROOT/libs/cuda/lib:/usr/lib/wsl/lib:${LD_LIBRARY_PATH:-}"
exec "$ROOT"/bin-cuda/llama-prism-*/llama-server \
  -m "$ROOT/models/Ternary-Bonsai-2-9B-PQ2_0.gguf" \
  -c 16384 -ngl 99 \
  --alias bonsai-9b \
  --host 127.0.0.1 --port 8080 \
  "$@"
