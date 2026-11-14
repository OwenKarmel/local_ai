"""All runtime config comes from env vars; defaults work on any Mac that followed CLAUDE.md setup."""
import os

_MODELS = os.path.expanduser(os.environ.get("BONSAI_MODELS_DIR", "~/models/prism-ml"))

# Local OpenAI-compatible model server (mlx_vlm.server). mlx_vlm uses the model folder path as the model id.
BONSAI_BASE_URL = os.environ.get("BONSAI_BASE_URL", "http://localhost:1234/v1")
# Both routes default to the 4B on one server: it matched the 9B's accuracy at about 1.6x the speed (plan.md).
# To make the fast route snappier later, run a second server with the 2B and set FAST_MODEL + FAST_BASE_URL.
CODE_MODEL = os.environ.get("CODE_MODEL", f"{_MODELS}/Ternary-Bonsai-2-4B-mlx-2bit")  # level route
FAST_MODEL = os.environ.get("FAST_MODEL", f"{_MODELS}/Ternary-Bonsai-2-4B-mlx-2bit")  # fast route (A4)
# One mlx_vlm.server holds one model at a time (swapping costs about 4 s). To keep both loaded, run a
# second server for FAST_MODEL on another port and point FAST_BASE_URL at it.
FAST_BASE_URL = os.environ.get("FAST_BASE_URL", BONSAI_BASE_URL)

# Argmax local speech server: `argmax-cli serve` (WhisperKit, OpenAI-compatible /audio/transcriptions). 50060 is its
# default port. See CLAUDE.md "Argmax setup".
ARGMAX_URL = os.environ.get("ARGMAX_URL", "http://localhost:50060/v1")

# NO_THINKING=1: ask the model server to skip the model's reasoning (<think>) phase on every request, via
# chat_template_kwargs.enable_thinking=false. Faster commands; llama-server's Bonsai template thinks by default.
NO_THINKING = os.environ.get("NO_THINKING", "").strip().lower() in ("1", "true", "yes")

# STUB_SPEECH=1: /api/transcribe returns fixed text (no Argmax server needed; any machine).
STUB_SPEECH = os.environ.get("STUB_SPEECH", "").strip().lower() in ("1", "true", "yes")
