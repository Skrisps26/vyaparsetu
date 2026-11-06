from __future__ import annotations

import time

from .types import ProviderPrerequisiteError, ProviderStageError
from ..config import Settings


class TimbreProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def synthesize(self, text: str, request_id: str | None = None) -> tuple[bytes, int]:
        if not self.settings.tts_configured:
            raise ProviderPrerequisiteError("GNANI_API_KEY is required for live voice confirmation")
        if any(char.isdecimal() for char in text) or "₹" in text:
            raise ProviderStageError("Voice confirmation was not normalized safely")
        try:
            from gnani import AudioConfig, GnaniTTSClient
            client = GnaniTTSClient(api_key=self.settings.gnani_api_key, base_url=self.settings.gnani_base_url)
            started = time.perf_counter()
            response = client.synthesize(
                text, model=self.settings.tts_model, voice=self.settings.tts_voice,
                language=self.settings.tts_language, speed=self.settings.tts_speed,
                audio_config=AudioConfig(sample_rate=48000, num_channels=1, sample_width=2,
                                         encoding="linear_pcm", container="wav"),
                request_id=request_id,
            )
            elapsed = int((time.perf_counter() - started) * 1000)
        except ProviderPrerequisiteError:
            raise
        except Exception as error:
            message = str(error).lower()
            if any(word in message for word in ("401", "403", "auth", "scope", "key")):
                raise ProviderStageError("Voice confirmation authentication or scope was rejected") from error
            if any(word in message for word in ("429", "rate", "credit", "quota")):
                raise ProviderStageError("Voice confirmation is unavailable because the provider rate or credit limit was reached") from error
            if any(word in message for word in ("timeout", "timed out", "connect")):
                raise ProviderStageError("Voice confirmation provider timed out") from error
            raise ProviderStageError("Voice confirmation provider failed") from error
        audio = response if isinstance(response, bytes) else getattr(response, "content", response)
        if not isinstance(audio, bytes) or not audio.startswith(b"RIFF"):
            raise ProviderStageError("Voice confirmation provider returned invalid WAV audio")
        return audio, elapsed
