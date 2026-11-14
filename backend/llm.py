"""Minimal client for the local OpenAI-compatible server (mlx_vlm.server / LM Studio / llama.cpp)."""
import logging
import time

import httpx

from . import config

log = logging.getLogger("llm")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

# Bonsai 2 recommended non-thinking sampler (see model card). Tuned for chat and open-ended text.
SAMPLER = {"temperature": 0.7, "top_p": 0.8, "top_k": 20, "presence_penalty": 1.5}
# For picking ops from a fixed menu (JSON schema). Low temperature: the model should take its most likely reading
# of the command. No presence penalty: JSON repeats the same tokens ("op", quotes, braces) by design.
STRUCTURED_SAMPLER = {"temperature": 0.2, "top_p": 0.8, "top_k": 20, "presence_penalty": 0.0}


class LLMError(Exception):
    pass


def short_name(model: str) -> str:
    return model.rstrip("/").split("/")[-1]


def chat(model: str, messages: list[dict], schema: dict | None = None, max_tokens: int = 1024, timeout: float = 120,
         sampler: dict | None = None) -> dict:
    """Returns {"text", "model", "latency_ms", "usage"}. Raises LLMError if the server is unreachable/errs."""
    body = {"model": model, "messages": messages, "max_tokens": max_tokens, **(sampler or SAMPLER)}
    if schema is not None:
        body["response_format"] = {"type": "json_schema", "json_schema": {"name": "patch", "schema": schema, "strict": True}}
    t0 = time.perf_counter()
    try:
        r = httpx.post(f"{config.BONSAI_BASE_URL}/chat/completions", json=body, timeout=timeout)
    except httpx.HTTPError as e:
        raise LLMError(f"Model server not reachable at {config.BONSAI_BASE_URL} ({type(e).__name__}). Is mlx_vlm.server running?")
    latency_ms = int((time.perf_counter() - t0) * 1000)
    if r.status_code != 200:
        raise LLMError(f"Model server error {r.status_code}: {r.text[:300]}")
    d = r.json()
    text = d["choices"][0]["message"].get("content") or ""
    usage = d.get("usage") or {}
    log.info("model=%s latency_ms=%d in=%s out=%s", short_name(model), latency_ms, usage.get("prompt_tokens"), usage.get("completion_tokens"))
    return {"text": text, "model": short_name(model), "latency_ms": latency_ms, "usage": usage}
