from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import time

from app.config import settings
from app.pipeline import Pipeline
from app.providers.evon import EvonProvider
from app.providers.prisma import PrismaProvider
from app.providers.timbre import TimbreProvider
from app.speech_text import confirmation_text


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description="Explicit live-provider smoke command; never runs on startup.")
    command.add_argument("--stage", choices=("stt", "stt-compare", "evon", "tts"), required=True)
    command.add_argument("--input", type=Path)
    command.add_argument("--inputs", nargs=3, type=Path)
    command.add_argument("--transcript", type=Path)
    command.add_argument("--amount-paise", type=int, default=14960)
    command.add_argument("--balance-paise", type=int, default=24960)
    return command


def stt_once(path: Path, format_name: str) -> dict[str, object]:
    wav = Pipeline._to_wav(path.read_bytes(), path.name)
    started = time.perf_counter()
    result = PrismaProvider(settings).transcribe(wav, "clip.wav", [], format_name)  # type: ignore[arg-type]
    return {"input": str(path), "format": format_name, "transcript": result.transcript,
            "detected_language_code": result.detected_language_code,
            "provider_elapsed_ms": result.provider_elapsed_ms,
            "wall_elapsed_ms": int((time.perf_counter() - started) * 1000)}


async def evon_once(path: Path) -> dict[str, object]:
    extraction = await EvonProvider(settings).extract(path.read_text(), [])
    return extraction.model_dump(mode="json")


def main() -> None:
    args = parser().parse_args()
    if settings.use_mocks:
        raise SystemExit("Set USE_MOCKS=false for an explicit live smoke call")
    if args.stage == "stt":
        if not args.input:
            raise SystemExit("--input is required for --stage stt")
        print(json.dumps(stt_once(args.input, settings.stt_format), ensure_ascii=False, indent=2))
    elif args.stage == "stt-compare":
        if not args.inputs:
            raise SystemExit("--inputs requires exactly three synthetic recordings")
        results = [stt_once(path, format_name) for path in args.inputs for format_name in ("transcribe", "codemix")]
        output = Path("fixtures/stt-comparison.json")
        output.write_text(json.dumps(results, ensure_ascii=False, indent=2))
        print(json.dumps({"saved": str(output), "results": results}, ensure_ascii=False, indent=2))
    elif args.stage == "evon":
        if not args.transcript:
            raise SystemExit("--transcript is required for --stage evon")
        print(json.dumps(asyncio.run(evon_once(args.transcript)), ensure_ascii=False, indent=2))
    else:
        text = confirmation_text(args.amount_paise, "credit", args.balance_paise)
        audio, elapsed = TimbreProvider(settings).synthesize(text)
        if not audio.startswith(b"RIFF"):
            raise SystemExit("Timbre did not return a WAV")
        print(json.dumps({"text": text, "bytes": len(audio), "elapsed_ms": elapsed}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
