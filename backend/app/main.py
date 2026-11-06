from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, ValidationError

from .config import settings
from .ledger import Ledger
from .pipeline import Pipeline
from .schemas import ConfirmRequest, DraftRequest

from .lookup import resolve_review_items, router as lookup_router

class ScenarioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario_id: Literal["correction-credit"]


app = FastAPI(title="VyaparSetu API")
pipeline = Pipeline(settings, Ledger(settings.database_path), review_resolver=resolve_review_items)
app.include_router(lookup_router)


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Unknown run")


@app.get("/api/config")
async def config() -> dict[str, object]:
    return {
        "use_mocks": settings.use_mocks,
        "models": {"stt": settings.stt_model, "evon": settings.evon_model, "tts": settings.tts_model},
        "stages": {
            "stt": {"configured": settings.stt_configured, "reason": None if settings.stt_configured else "GNANI_API_KEY is not configured"},
            "evon": {"configured": settings.evon_configured, "reason": None if settings.evon_configured else "EVON_BASE_URL and EVON_MODEL are not configured"},
            "tts": {"configured": settings.tts_configured, "reason": None if settings.tts_configured else "GNANI_API_KEY is not configured"},
        },
    }


@app.post("/api/runs", status_code=202)
async def create_run(request: Request) -> dict[str, str]:
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        try:
            scenario = ScenarioRequest.model_validate(await request.json())
        except ValidationError as error:
            raise HTTPException(status_code=422, detail=error.errors()) from error
        record = await pipeline.create_mock()
        return {"run_id": record.run_id}
    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        upload = form.get("audio_file")
        if upload is None or not hasattr(upload, "read"):
            raise HTTPException(status_code=422, detail="audio_file multipart field is required")
        audio = await upload.read()
        if len(audio) > 10 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Audio upload exceeds the 10 MiB limit")
        record = await pipeline.create_audio(audio, getattr(upload, "filename", "clip.bin") or "clip.bin")
        return {"run_id": record.run_id}
    raise HTTPException(status_code=415, detail="Use JSON demo scenario or multipart audio_file")


@app.post("/api/drafts", status_code=202)
async def create_draft(draft: DraftRequest) -> dict[str, str]:
    record = await pipeline.create_draft(draft)
    return {"run_id": record.run_id}


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str) -> dict[str, object]:
    try:
        return pipeline.snapshot(pipeline.require(run_id))
    except KeyError:
        raise _not_found()


@app.post("/api/runs/{run_id}/confirm")
async def confirm_run(run_id: str, request: ConfirmRequest) -> dict[str, object]:
    try:
        record = await pipeline.confirm(run_id, request)
    except KeyError:
        raise _not_found()
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return pipeline.snapshot(record)


@app.post("/api/runs/{run_id}/synthesize")
async def synthesize_reply(run_id: str) -> dict[str, object]:
    try:
        record = pipeline.require(run_id)
    except KeyError:
        raise _not_found()
    if not record.confirmed or not record.reply_text:
        raise HTTPException(status_code=409, detail="Save an invoice before requesting voice confirmation")
    if record.source == "mock":
        return pipeline.snapshot(record)
    if record.status == "synthesizing":
        raise HTTPException(status_code=409, detail="Voice confirmation is already being prepared")
    record.error = None
    asyncio.create_task(pipeline._synthesize_reply(record))
    return pipeline.snapshot(record)


@app.get("/api/runs/{run_id}/audio")
async def get_audio(run_id: str) -> Response:
    try:
        record = pipeline.require(run_id)
    except KeyError:
        raise _not_found()
    if record.audio is None:
        raise HTTPException(status_code=404, detail="No reply WAV is available for this run")
    return Response(record.audio, media_type="audio/wav")


@app.get("/api/ledger")
async def get_ledger() -> dict[str, object]:
    return pipeline.ledger.snapshot()


@app.websocket("/api/runs/{run_id}/events")
async def run_events(websocket: WebSocket, run_id: str, after: int = 0) -> None:
    if not pipeline.events.exists(run_id):
        await websocket.close(code=4404, reason="Unknown run")
        return
    await websocket.accept()
    sequence = after
    terminal = {"run.completed", "run.failed"}
    try:
        while True:
            events = pipeline.events.replay(run_id, sequence)
            if not events:
                events = await pipeline.events.wait_after(run_id, sequence)
            for event in events:
                await websocket.send_json(event.model_dump(mode="json"))
                sequence = event.seq
                if event.type in terminal:
                    await websocket.close()
                    return
    except WebSocketDisconnect:
        return
