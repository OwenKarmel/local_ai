import os

_MODELS = os.path.expanduser("~/models/prism-ml")

BONSAI_BASE_URL = os.environ.get("BONSAI_BASE_URL", "http://localhost:1234/v1")
# mlx_vlm.server uses the model folder path as the model id (see CLAUDE.md "Model setup").
CODE_MODEL = os.environ.get("CODE_MODEL", f"{_MODELS}/Ternary-Bonsai-2-9B-mlx-2bit")  # patches, mechanics code
FAST_MODEL = os.environ.get("FAST_MODEL", f"{_MODELS}/Ternary-Bonsai-2-2B-mlx-2bit")  # chat, classification
