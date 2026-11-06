from __future__ import annotations

import time
from typing import Literal

from .types import ProviderPrerequisiteError, ProviderStageError, SpeechResult
from ..config import Settings

TOPIC = "Kerala kirana billing in Malayalam and English: groceries, brands, quantities, pack sizes, unit prices, corrections, cash, UPI and synthetic credit accounts."


def _provider_message(error: Exception) -> str:
    text = str(error).lower()
    if any(word in text for word in ("401", "403", "auth", "scope", "key")):
        return "Speech recognition authentication or scope was rejected"
    if any(word in text for word in ("429", "rate", "credit", "quota")):
        return "Speech recognition is unavailable because the provider rate or credit limit was reached"
    if any(word in text for word in ("timeout", "timed out", "connect")):
        return "Speech recognition provider timed out"
    return "Speech recognition provider failed"


class PrismaProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def transcribe(
        self, audio_bytes: bytes, filename: str, keywords: list[str],
        format: Literal["transcribe", "codemix"] | None = None, request_id: str | None = None,
    ) -> SpeechResult:
        if not self.settings.stt_configured:
            raise ProviderPrerequisiteError("GNANI_API_KEY is required for live speech recognition")
        try:
            from gnani import GnaniSTTClient
            client = GnaniSTTClient(api_key=self.settings.gnani_api_key, base_url=self.settings.gnani_base_url)
            started = time.perf_counter()
            response = client.transcribe_bytes(
                audio_bytes, filename=filename, language_code=self.settings.stt_languages,
                model=self.settings.stt_model, format=format or self.settings.stt_format,
                keywords=",".join(keywords[:200]), topic=TOPIC, request_id=request_id,
            )
            elapsed = int((time.perf_counter() - started) * 1000)
        except ProviderPrerequisiteError:
            raise
        except Exception as error:
            raise ProviderStageError(_provider_message(error)) from error
        transcript = str(getattr(response, "transcript", "") or "")
        language = getattr(response, "detected_language_code", None)
        return SpeechResult(transcript=transcript, detected_language_code=language, provider_elapsed_ms=elapsed)
