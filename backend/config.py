import os

BONSAI_BASE_URL = os.environ.get("BONSAI_BASE_URL", "http://localhost:1234/v1")
CODE_MODEL = os.environ.get("CODE_MODEL", "bonsai-2-9b")  # level patches, mechanics code
FAST_MODEL = os.environ.get("FAST_MODEL", "bonsai-2-2b")  # chat replies, simple classification
