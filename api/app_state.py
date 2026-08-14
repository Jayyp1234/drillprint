"""Shared process state for the FastAPI app."""

from __future__ import annotations

import asyncio
from pathlib import Path

from config import load_well
from ingest.pipeline import StreamEngine
from store.fingerprint_db import FingerprintDB


class AppState:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db = FingerprintDB(self.db_path) if self.db_path.exists() else None
        self.well = load_well()
        self.engine: StreamEngine | None = None
        self.subscribers: list[asyncio.Queue] = []
        self.bench_report: dict | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        if self.db and self.db.active_version():
            self.reset_engine()

    def reset_engine(self, mode: str = "live") -> StreamEngine:
        if self.db is None:
            raise RuntimeError("no fingerprint database")
        self.engine = StreamEngine(
            self.db, well=self.well, mode=mode, emit=self._broadcast
        )
        return self.engine

    def _broadcast(self, msg: dict) -> None:
        """Fan-out to monitor subscribers (safe from worker threads)."""
        loop = self.loop
        for q in list(self.subscribers):
            try:
                if loop is not None and loop.is_running():
                    loop.call_soon_threadsafe(self._put, q, msg)
                else:
                    self._put(q, msg)
            except RuntimeError:
                pass

    @staticmethod
    def _put(q: asyncio.Queue, msg: dict) -> None:
        try:
            q.put_nowait(msg)
        except asyncio.QueueFull:
            try:
                q.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass

    def close(self) -> None:
        if self.db:
            self.db.close()
