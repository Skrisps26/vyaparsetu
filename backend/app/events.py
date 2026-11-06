from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .schemas import EventEnvelope, RunSource


@dataclass
class RunEvents:
    source: RunSource
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    events: list[EventEnvelope] = field(default_factory=list)
    signal: asyncio.Condition = field(default_factory=asyncio.Condition)


class EventStore:
    def __init__(self, max_runs: int = 100, retention_minutes: int = 30) -> None:
        self.max_runs = max_runs
        self.retention = timedelta(minutes=retention_minutes)
        self._runs: OrderedDict[str, RunEvents] = OrderedDict()

    def create(self, run_id: str, source: RunSource) -> None:
        self._purge()
        self._runs[run_id] = RunEvents(source=source)
        while len(self._runs) > self.max_runs:
            self._runs.popitem(last=False)

    def exists(self, run_id: str) -> bool:
        self._purge()
        return run_id in self._runs

    def replay(self, run_id: str, after: int = 0) -> list[EventEnvelope]:
        return [event for event in self._runs[run_id].events if event.seq > after]

    async def publish(self, run_id: str, event_type: EventEnvelope.__annotations__["type"], payload: dict[str, object]) -> EventEnvelope:
        run = self._runs[run_id]
        event = EventEnvelope(run_id=run_id, seq=len(run.events) + 1, type=event_type,
                              source=run.source, payload=payload)
        async with run.signal:
            run.events.append(event)
            run.signal.notify_all()
        return event

    async def wait_after(self, run_id: str, sequence: int) -> list[EventEnvelope]:
        run = self._runs[run_id]
        async with run.signal:
            await run.signal.wait_for(lambda: bool(run.events and run.events[-1].seq > sequence))
            return [event for event in run.events if event.seq > sequence]

    def _purge(self) -> None:
        cutoff = datetime.now(timezone.utc) - self.retention
        for run_id in [key for key, run in self._runs.items() if run.created_at < cutoff]:
            self._runs.pop(run_id, None)
