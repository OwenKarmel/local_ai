#!/usr/bin/env bash
# llama-server backend: Ternary-Bonsai-2 (2B or 9B), 16k context, full GPU offload.
# Usage: start-llama-server.sh [2b|9b] [extra llama-server args]   (default 2b)
# OpenAI-compatible API at http://127.0.0.1:8080/v1, model alias bonsai-<size>.
set -euo pipefail
ROOT="$HOME/localAI"
SIZE="${1:-2b}"
case "$SIZE" in 2b|9b) shift || true ;; *) SIZE=2b ;; esac
FILE="Ternary-Bonsai-2-${SIZE^^}-PQ2_0.gguf"
export LD_LIBRARY_PATH="$ROOT/libs/gomp/usr/lib/x86_64-linux-gnu:$ROOT/libs/cuda/lib:/usr/lib/wsl/lib:${LD_LIBRARY_PATH:-}"
exec "$ROOT"/bin-cuda/llama-prism-*/llama-server \
  -m "$ROOT/models/$FILE" \
  -c 16384 -ngl 99 \
  --alias "bonsai-$SIZE" \
  --host 127.0.0.1 --port 8080 \
  "$@"
