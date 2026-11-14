#!/usr/bin/env bash
# Open WebUI frontend pointed at the local llama-server. UI at http://localhost:3000
set -euo pipefail
ROOT="$HOME/localAI"
export OPENAI_API_BASE_URL="http://127.0.0.1:8080/v1"
export OPENAI_API_KEY="none"
export ENABLE_OLLAMA_API=false
export DATA_DIR="$ROOT/openwebui-data"
export WEBUI_AUTH=false
# Skip background LLM tasks so they do not compete with replies on the small GPU
export ENABLE_TITLE_GENERATION=false ENABLE_TAGS_GENERATION=false ENABLE_FOLLOW_UP_GENERATION=false ENABLE_AUTOCOMPLETE_GENERATION=false ENABLE_RETRIEVAL_QUERY_GENERATION=false ENABLE_SEARCH_QUERY_GENERATION=false
export HOST=127.0.0.1 PORT=3000
# Open WebUI needs Python 3.11/3.12; uv provides it in an isolated environment.
exec "$ROOT/tools/uv/uv" run --python 3.11 --with open-webui open-webui serve --host 127.0.0.1 --port 3000
