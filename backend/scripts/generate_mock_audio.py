from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

from app.providers.mock import CANONICAL_TRANSCRIPT, MOCK_REPLY

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def synthesize(filename: str, text: str) -> None:
    executable = shutil.which("espeak-ng")
    if not executable:
        raise SystemExit("espeak-ng is required to generate offline mock WAV fixtures")
    subprocess.run([executable, "-v", "ml", "-s", "140", "-w", str(FIXTURES / filename), text], check=True)


def main() -> None:
    FIXTURES.mkdir(exist_ok=True)
    synthesize("mock-input.wav", CANONICAL_TRANSCRIPT)
    synthesize("mock-reply.wav", MOCK_REPLY)


if __name__ == "__main__":
    main()
