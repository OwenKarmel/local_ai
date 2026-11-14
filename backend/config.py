"""All runtime config comes from env vars; defaults work on any Mac that followed CLAUDE.md setup."""
import os

_MODELS = os.path.expanduser(os.environ.get("BONSAI_MODELS_DIR", "~/models/prism-ml"))

# Local OpenAI-compatible model server (mlx_vlm.server). mlx_vlm uses the model folder path as the model id.
BONSAI_BASE_URL = os.environ.get("BONSAI_BASE_URL", "http://localhost:1234/v1")
CODE_MODEL = os.environ.get("CODE_MODEL", f"{_MODELS}/Ternary-Bonsai-2-9B-mlx-2bit")  # patches, mechanics code
FAST_MODEL = os.environ.get("FAST_MODEL", f"{_MODELS}/Ternary-Bonsai-2-2B-mlx-2bit")  # routing + simple setting changes
# One mlx_vlm.server holds one model at a time (swapping costs about 4 s). To keep both loaded, run a
# second server for FAST_MODEL on another port and point FAST_BASE_URL at it.
FAST_BASE_URL = os.environ.get("FAST_BASE_URL", BONSAI_BASE_URL)

# Argmax local speech server (WhisperKit transcription; OpenAI-compatible /audio/transcriptions). Port is a placeholder until
# Owen's Argmax setup confirms it; override with ARGMAX_URL.
ARGMAX_URL = os.environ.get("ARGMAX_URL", "http://localhost:50060/v1")
