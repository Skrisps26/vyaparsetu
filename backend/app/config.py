from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def _flag(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    use_mocks: bool = _flag("USE_MOCKS", True)
    gnani_api_key: str = os.getenv("GNANI_API_KEY", "")
    gnani_base_url: str = os.getenv("GNANI_BASE_URL", "https://api.vachana.ai")
    stt_model: str = os.getenv("STT_MODEL", "prisma-v3.0")
    stt_format: str = os.getenv("STT_FORMAT", "transcribe")
    stt_languages: str = os.getenv("STT_LANGUAGES", "ml-IN,en-IN")
    tts_model: str = os.getenv("TTS_MODEL", "timbre-v3.0")
    tts_voice: str = os.getenv("TTS_VOICE", "Shivani")
    tts_language: str = os.getenv("TTS_LANGUAGE", "ml-IN")
    tts_speed: float = float(os.getenv("TTS_SPEED", "0.90"))
    evon_base_url: str = os.getenv("EVON_BASE_URL", "")
    evon_api_key: str = os.getenv("EVON_API_KEY", "")
    evon_model: str = os.getenv("EVON_MODEL", "")
    database_path: str = os.getenv("DATABASE_PATH", str(ROOT / "data" / "vyaparsetu.sqlite3"))

    @property
    def stt_configured(self) -> bool:
        return bool(self.gnani_api_key)

    @property
    def tts_configured(self) -> bool:
        return bool(self.gnani_api_key)

    @property
    def evon_configured(self) -> bool:
        return bool(self.evon_base_url and self.evon_model)


settings = Settings()
