"""Speech: forwards audio to the local Argmax server (WhisperKit, OpenAI-compatible /audio/transcriptions).

Audio is normalized with ffmpeg first (if installed): 16 kHz mono WAV, padded with silence to at least 2 s.
- Browsers usually record webm/opus, which WhisperKit can't read.
- Whisper returns empty text for clips under about 1 s ("make this harder" at 0.9 s came back empty;
  padded to 2 s it transcribes correctly on base.en and large-v3).
Without ffmpeg, wav/m4a/mp3/flac/aiff/caf are sent as-is and anything else is an error.
"""
import logging
import shutil
import subprocess
import time

import httpx

from . import config

log = logging.getLogger("speech")
DIRECT = {"wav", "m4a", "mp3", "flac", "aiff", "aif", "caf"}


class SpeechError(Exception):
    pass


def _ext(filename: str | None, content_type: str | None) -> str:
    if filename and "." in filename:
        return filename.rsplit(".", 1)[1].lower()
    ct = (content_type or "").split(";")[0].strip().lower()
    return {"audio/wav": "wav", "audio/x-wav": "wav", "audio/wave": "wav", "audio/mpeg": "mp3", "audio/mp4": "m4a",
            "audio/x-m4a": "m4a", "audio/flac": "flac", "audio/webm": "webm", "audio/ogg": "ogg"}.get(ct, "bin")


MIN_SECONDS = 2.0


def to_wav(data: bytes) -> bytes:
    ff = shutil.which("ffmpeg")
    if not ff:
        raise SpeechError("Audio isn't wav/m4a/mp3/flac and ffmpeg isn't installed to convert it. Send WAV, or `brew install ffmpeg`.")
    p = subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-i", "pipe:0", "-ac", "1", "-ar", "16000",
                        "-af", f"apad=whole_dur={MIN_SECONDS}", "-f", "wav", "pipe:1"],
                       input=data, capture_output=True, timeout=30)
    if p.returncode != 0 or not p.stdout:
        raise SpeechError(f"Could not convert audio to WAV: {p.stderr.decode(errors='ignore')[:200]}")
    return p.stdout


def transcribe(data: bytes, filename: str | None, content_type: str | None) -> dict:
    """Returns {"text", "latency_ms"}. latency_ms covers conversion + the Argmax call."""
    t0 = time.perf_counter()
    ext = _ext(filename, content_type)
    if shutil.which("ffmpeg") or ext not in DIRECT:
        data, ext = to_wav(data), "wav"
    files = {"file": (f"audio.{ext}", data, "audio/wav" if ext == "wav" else "application/octet-stream")}
    # `model` is required by argmax-cli serve but ignored (it uses the model it was started with).
    # temperature must be "0.0": the server rejects "0" with a 500 (seen on argmax-oss-swift 9f99b5c).
    form = {"model": "whisper", "response_format": "json", "language": "en", "temperature": "0.0"}
    try:
        r = httpx.post(f"{config.ARGMAX_URL}/audio/transcriptions", files=files, data=form, timeout=60)
    except httpx.HTTPError as e:
        raise SpeechError(f"Argmax server not reachable at {config.ARGMAX_URL} ({type(e).__name__}). Is `argmax-cli serve` running?")
    if r.status_code != 200:
        raise SpeechError(f"Argmax server error {r.status_code}: {r.text[:300]}")
    text = (r.json().get("text") or "").strip()
    ms = int((time.perf_counter() - t0) * 1000)
    log.info("transcribe ext=%s bytes=%d latency_ms=%d text=%r", ext, len(data), ms, text)
    return {"text": text, "latency_ms": ms}
