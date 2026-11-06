from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import tempfile
import time
import uuid
import wave
from typing import Any, Awaitable, Callable

from fastapi.concurrency import run_in_threadpool
import imageio_ffmpeg

from .config import ROOT, Settings
from .events import EventStore
from .invoice_math import calculate_invoice, decimal_to_paise
from .ledger import Ledger
from .providers.evon import EvonProvider
from .providers.mock import MOCK_REPLY, mock_extraction, mock_speech
from .providers.prisma import PrismaProvider
from .providers.timbre import TimbreProvider
from .providers.types import ProviderPrerequisiteError, ProviderStageError
from .schemas import ConfirmRequest, DraftRequest, Invoice, InvoiceExtraction, ReviewedItem, RunSource
from .speech_text import confirmation_text


@dataclass
class RunRecord:
    run_id: str
    source: RunSource
    scope: str
    status: str = "queued"
    transcript: str | None = None
    detected_language_code: str | None = None
    invoice: Invoice | None = None
    reply_text: str | None = None
    audio: bytes | None = None
    error: str | None = None
    latencies: dict[str, int | str] = field(default_factory=dict)
    confirmed: bool = False
    balance_paise: int | None = None


ReviewResolver = Callable[[list[dict[str, Any]]], list[dict[str, Any]] | Awaitable[list[dict[str, Any]]]]


class Pipeline:
    def __init__(self, settings: Settings, ledger: Ledger, review_resolver: ReviewResolver | None = None) -> None:
        self.settings = settings
        self.ledger = ledger
        self.events = EventStore()
        self.runs: dict[str, RunRecord] = {}
        self.speech_lock = asyncio.Lock()
        self.prisma = PrismaProvider(settings)
        self.evon = EvonProvider(settings)
        self.timbre = TimbreProvider(settings)
        self.review_resolver = review_resolver
        catalog = json.loads((ROOT / "backend" / "config" / "catalog.json").read_text())
        self.catalog_names = {row["id"]: row["name"] for row in catalog}
        self.catalog_aliases = [alias for row in catalog for alias in row["aliases"]]

    def _new(self, source: RunSource) -> RunRecord:
        run_id = uuid.uuid4().hex
        scope = f"demo:{run_id}" if source == "mock" else "live"
        record = RunRecord(run_id=run_id, source=source, scope=scope)
        self.runs[run_id] = record
        self.events.create(run_id, source)
        return record

    async def create_mock(self) -> RunRecord:
        record = self._new("mock")
        asyncio.create_task(self._process_mock(record))
        return record

    async def create_draft(self, draft: DraftRequest) -> RunRecord:
        record = self._new("manual")
        started = time.perf_counter()
        invoice = calculate_invoice(draft.items, draft.customer_name, draft.payment_mode, draft.corrections, self.catalog_names)
        record.invoice = invoice
        record.status = "review" if invoice.needs_review else "ready"
        record.latencies["invoice"] = int((time.perf_counter() - started) * 1000)
        await self.events.publish(record.run_id, "invoice.ready", {"invoice": invoice.model_dump(mode="json")})
        return record

    async def create_audio(self, audio_bytes: bytes, filename: str) -> RunRecord:
        record = self._new("live")
        if self.settings.use_mocks:
            await self._fail(record, "Live voice processing is disabled while USE_MOCKS=true; use the Demo replay")
        else:
            asyncio.create_task(self._process_live(record, audio_bytes, filename))
        return record

    async def _process_mock(self, record: RunRecord) -> None:
        try:
            record.status = "transcribing"
            await self._stage_started(record, "transcription")
            result = mock_speech()
            record.transcript, record.detected_language_code = result.transcript, result.detected_language_code
            record.latencies["transcription"] = "fixture"
            await self.events.publish(record.run_id, "transcript.ready", {"transcript": result.transcript, "detected_language_code": result.detected_language_code})
            await self._stage_finished(record, "transcription", "fixture")
            record.status = "understanding"
            await self._stage_started(record, "understanding")
            items, customer_name, payment_mode, corrections = mock_extraction()
            invoice = calculate_invoice(items, customer_name, payment_mode, corrections, self.catalog_names, allow_fixture=True)
            record.invoice = invoice
            record.status = "ready"
            record.latencies["understanding"] = "fixture"
            await self.events.publish(record.run_id, "invoice.ready", {"invoice": invoice.model_dump(mode="json")})
            await self._stage_finished(record, "understanding", "fixture")
        except Exception as error:
            await self._fail(record, str(error))

    async def _process_live(self, record: RunRecord, audio_bytes: bytes, filename: str) -> None:
        try:
            record.status = "transcribing"
            await self._stage_started(record, "transcription")
            wav_bytes = await run_in_threadpool(self._to_wav, audio_bytes, filename)
            started = time.perf_counter()
            async with self.speech_lock:
                result = await run_in_threadpool(
                    self.prisma.transcribe, wav_bytes, "clip.wav", self.catalog_aliases, request_id=record.run_id,
                )
            elapsed = result.provider_elapsed_ms or int((time.perf_counter() - started) * 1000)
            record.latencies["transcription"] = elapsed
            record.transcript, record.detected_language_code = result.transcript, result.detected_language_code
            if not result.transcript.strip():
                raise ProviderStageError("Speech recognition returned no transcript; no invoice was created")
            await self.events.publish(record.run_id, "transcript.ready", {"transcript": result.transcript, "detected_language_code": result.detected_language_code})
            await self._stage_finished(record, "transcription", elapsed)
            record.status = "understanding"
            await self._stage_started(record, "understanding")
            started = time.perf_counter()
            extraction = await self.evon.extract(result.transcript, self.catalog_aliases)
            elapsed = int((time.perf_counter() - started) * 1000)
            items = [ReviewedItem.model_validate(item.model_dump()) for item in extraction.items]
            record.invoice = calculate_invoice(items, extraction.customer_name, extraction.payment_mode, extraction.corrections, self.catalog_names)
            record.status = "review" if record.invoice.needs_review else "ready"
            record.latencies["understanding"] = elapsed
            await self.events.publish(record.run_id, "invoice.ready", {"invoice": record.invoice.model_dump(mode="json")})
            await self._stage_finished(record, "understanding", elapsed)
        except (ProviderPrerequisiteError, ProviderStageError, ValueError) as error:
            await self._fail(record, str(error))
        except Exception:
            await self._fail(record, "Invoice processing failed")

    @staticmethod
    def _to_wav(audio_bytes: bytes, filename: str) -> bytes:
        if len(audio_bytes) > 10 * 1024 * 1024:
            raise ValueError("Audio upload exceeds the 10 MiB limit")
        suffix = Path(filename).suffix or ".bin"
        with tempfile.TemporaryDirectory(prefix="vyaparsetu-audio-") as directory:
            source = Path(directory) / f"input{suffix}"
            target = Path(directory) / "clip.wav"
            source.write_bytes(audio_bytes)
            executable = imageio_ffmpeg.get_ffmpeg_exe()
            try:
                subprocess.run(
                    [executable, "-nostdin", "-y", "-i", str(source), "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", str(target)],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=15, check=True,
                )
            except (subprocess.SubprocessError, OSError) as error:
                raise ValueError("Audio could not be decoded into WAV") from error
            try:
                with wave.open(str(target), "rb") as wav:
                    duration = wav.getnframes() / wav.getframerate()
                    if duration <= 0:
                        raise ValueError("Decoded audio is empty")
                    if duration > 30:
                        raise ValueError("Decoded audio exceeds the 30 second provider limit")
            except wave.Error as error:
                raise ValueError("Audio conversion did not produce a valid WAV") from error
            return target.read_bytes()

    async def confirm(self, run_id: str, request: ConfirmRequest) -> RunRecord:
        record = self.require(run_id)
        if record.confirmed:
            return record
        if record.invoice is None:
            raise ValueError("No invoice is ready to confirm")
        invoice = record.invoice
        if request.items is not None:
            items = request.items
            if self.review_resolver:
                submitted = []
                for item in items:
                    raw = item.model_dump(mode="json")
                    raw["evidence"] = []
                    raw["price_source"] = None
                    raw["tax_source"] = None
                    submitted.append(raw)
                resolved = self.review_resolver(submitted)
                if asyncio.iscoroutine(resolved):
                    resolved = await resolved
                items = [ReviewedItem.model_validate(item) for item in resolved]
            customer_name = request.customer_name if "customer_name" in request.model_fields_set else invoice.customer_name
            payment_mode = request.payment_mode if request.payment_mode is not None else invoice.payment_mode
            invoice = calculate_invoice(items, customer_name, payment_mode, invoice.corrections, self.catalog_names, allow_fixture=record.source == "mock")
            record.invoice = invoice
        if invoice.needs_review:
            raise ValueError("Review unresolved invoice fields before confirmation")
        saved, balance, already_saved = self.ledger.confirm(run_id, record.scope, invoice)
        record.invoice, record.balance_paise, record.confirmed = saved, balance, True
        record.status = "saved"
        await self.events.publish(run_id, "ledger.updated", {"invoice": saved.model_dump(mode="json"), "balance_paise": balance, "idempotent": already_saved})
        if record.source == "mock":
            record.reply_text = MOCK_REPLY
            audio_path = ROOT / "backend" / "fixtures" / "mock-reply.wav"
            record.audio = audio_path.read_bytes() if audio_path.exists() else None
            record.latencies["speech"] = "fixture"
            await self.events.publish(run_id, "reply.ready", {"reply_text": record.reply_text, "audio_available": record.audio is not None})
            await self.events.publish(run_id, "run.completed", {"status": "saved"})
        else:
            try:
                record.reply_text = confirmation_text(decimal_to_paise(saved.total or Decimal()), saved.payment_mode, balance)
            except ValueError as error:
                record.error = str(error)
                await self.events.publish(run_id, "run.failed", {"stage": "normalization", "message": record.error, "saved": True})
                return record
            asyncio.create_task(self._synthesize_reply(record))
        return record

    async def _synthesize_reply(self, record: RunRecord) -> None:
        try:
            record.status = "synthesizing"
            await self._stage_started(record, "speech")
            async with self.speech_lock:
                audio, elapsed = await run_in_threadpool(
                    self.timbre.synthesize, record.reply_text or "", request_id=record.run_id,
                )
            record.audio = audio
            record.latencies["speech"] = elapsed
            record.status = "complete"
            await self.events.publish(record.run_id, "reply.ready", {"reply_text": record.reply_text, "audio_available": True})
            await self._stage_finished(record, "speech", elapsed)
            await self.events.publish(record.run_id, "run.completed", {"status": "complete"})
        except (ProviderPrerequisiteError, ProviderStageError, ValueError) as error:
            record.status = "saved"
            record.error = str(error)
            await self.events.publish(record.run_id, "run.failed", {"stage": "speech", "message": record.error, "saved": True})

    async def _stage_started(self, record: RunRecord, stage: str) -> None:
        await self.events.publish(record.run_id, "stage.started", {"stage": stage})

    async def _stage_finished(self, record: RunRecord, stage: str, elapsed: int | str) -> None:
        await self.events.publish(record.run_id, "stage.finished", {"stage": stage, "elapsed_ms": elapsed})

    async def _fail(self, record: RunRecord, message: str) -> None:
        record.status, record.error = "error", message
        await self.events.publish(record.run_id, "run.failed", {"message": message})

    def require(self, run_id: str) -> RunRecord:
        try:
            return self.runs[run_id]
        except KeyError as error:
            raise KeyError("Unknown run") from error

    def snapshot(self, record: RunRecord, include_events: bool = True) -> dict[str, object]:
        return {
            "run_id": record.run_id, "source": record.source, "status": record.status,
            "transcript": record.transcript, "detected_language_code": record.detected_language_code,
            "invoice": record.invoice.model_dump(mode="json") if record.invoice else None,
            "reply_text": record.reply_text, "audio_url": f"/api/runs/{record.run_id}/audio" if record.audio else None,
            "events": [event.model_dump(mode="json") for event in self.events.replay(record.run_id)] if include_events else [],
            "latencies": record.latencies, "error": record.error,
        }
