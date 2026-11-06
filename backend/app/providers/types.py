from __future__ import annotations

from dataclasses import dataclass


class ProviderPrerequisiteError(RuntimeError):
    pass


class ProviderStageError(RuntimeError):
    pass


@dataclass(frozen=True)
class SpeechResult:
    transcript: str
    detected_language_code: str | None
    provider_elapsed_ms: int | None
