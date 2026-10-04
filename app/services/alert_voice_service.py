"""Spoken price alerts: Gemini writes a short quip about the triggered alert, then
Gemini TTS voices it. Returns raw PCM for the browser's Web Audio API
(frontend/assets/alert_voice.js)."""
import base64
import logging

from google import genai
from google.genai import types

from app.core.config import settings

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = (
    "Act as a witty, casual crypto tracking assistant. Keep your responses short "
    "(under 15 words) and say something random and conversational about the price milestone hit."
)

_client: genai.Client | None = None


def _get_client() -> genai.Client | None:
    global _client
    if _client is None and settings.gemini_api_key:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def _write_line(client: genai.Client, event: str) -> str:
    resp = client.models.generate_content(
        model=settings.gemini_text_model,
        contents=event,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=1.2,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    return (resp.text or "").strip() or event


def generate_alert_voice(event: str, voice_name: str | None = None) -> dict | None:
    """event e.g. "Bitcoin crossed $100k". Returns {"text", "audio_b64", "sample_rate"}
    (audio is 16-bit little-endian mono PCM), or None if Gemini is unavailable."""
    client = _get_client()
    if client is None:
        return None
    try:
        text = _write_line(client, event)
        resp = client.models.generate_content(
            model=settings.gemini_tts_model,
            contents=f"Say it casually: {text}",
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=voice_name or settings.gemini_voice_name
                        )
                    )
                ),
            ),
        )
        blob = resp.candidates[0].content.parts[0].inline_data
    except Exception:
        logger.exception("Gemini alert voice failed for %r", event)
        return None
    rate = 24000
    for param in (blob.mime_type or "").split(";"):
        if param.strip().startswith("rate="):
            rate = int(param.split("=", 1)[1])
    return {"text": text, "audio_b64": base64.b64encode(blob.data).decode("ascii"), "sample_rate": rate}
