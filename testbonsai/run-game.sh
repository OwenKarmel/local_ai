#!/usr/bin/env bash
# Run the game backend on this (non-Mac) machine with every command going to a local Bonsai 2 model.
# Usage: testbonsai/run-game.sh [2b|9b] [--no-think]   (default 2b)
#   --no-think: skip the model's reasoning phase (sets NO_THINKING=1). Much faster, may be less accurate.
# Starts llama-server with that model if it isn't already serving it, waits until it's ready, then starts
# the backend pointed at it. There is no stub mode: /api/command always calls this model.
set -euo pipefail
SIZE=2b
for arg in "$@"; do
  case "$arg" in
    2b|9b) SIZE="$arg" ;;
    --no-think) export NO_THINKING=1 ;;
    *) echo "usage: $0 [2b|9b] [--no-think]" >&2; exit 1 ;;
  esac
done
MODEL="bonsai-$SIZE"
URL="http://127.0.0.1:8080/v1"
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(dirname "$HERE")"

served="$(curl -s -m 2 "$URL/models" | grep -o '"id":"[^"]*"' | cut -d'"' -f4 || true)"
if [ -n "$served" ] && ! grep -qx "$MODEL" <<<"$served"; then
  echo "llama-server on :8080 serves: $(echo $served), not $MODEL. Stop it first (pkill llama-server)." >&2; exit 1
fi
if [ -z "$served" ]; then
  echo "Starting llama-server with $MODEL (log: ~/localAI/llama-server.log)..."
  nohup "$HERE/start-llama-server.sh" "$SIZE" > "$HOME/localAI/llama-server.log" 2>&1 &
  until curl -s -m 2 http://127.0.0.1:8080/health | grep -q '"ok"'; do sleep 1; done
fi
echo "Model server ready: $MODEL at $URL (thinking: $([ -n "${NO_THINKING:-}" ] && echo off || echo on))"

cd "$REPO"
[ -f .venv/bin/activate ] && source .venv/bin/activate
unset STUB_COMMANDS
export BONSAI_BASE_URL="$URL" FAST_BASE_URL="$URL" CODE_MODEL="$MODEL" FAST_MODEL="$MODEL"
exec uvicorn backend.main:app --reload --port 8000
