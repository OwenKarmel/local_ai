"""All runtime config comes from env vars; defaults work on any Mac that followed CLAUDE.md setup."""
import os

_MODELS = os.path.expanduser(os.environ.get("BONSAI_MODELS_DIR", "~/models/prism-ml"))

# Local OpenAI-compatible model server (mlx_vlm.server). mlx_vlm uses the model folder path as the model id.
BONSAI_BASE_URL = os.environ.get("BONSAI_BASE_URL", "http://localhost:1234/v1")
CODE_MODEL = os.environ.get("CODE_MODEL", f"{_MODELS}/Ternary-Bonsai-2-9B-mlx-2bit")  # patches, mechanics code
FAST_MODEL = os.environ.get("FAST_MODEL", f"{_MODELS}/Ternary-Bonsai-2-2B-mlx-2bit")  # chat, classification, labels

# Argmax local speech server (OpenAI-compatible /audio/transcriptions). Port is a placeholder until
# Owen's Argmax setup confirms it; override with ARGMAX_URL.
ARGMAX_URL = os.environ.get("ARGMAX_URL", "http://localhost:50060/v1")
