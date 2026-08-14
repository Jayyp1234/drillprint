"""Replay / stream player — feeds SynthEpisode channels into a StreamEngine (M4).

Data-time paced: ``feed_episode`` advances the engine synchronously (tests,
bench). ``play`` optionally sleeps for wall-clock pacing at ``speed``×.
"""

from __future__ import annotations

import time
from typing import Iterator

import numpy as np

from config import WellConfig
from ingest.pipeline import StreamEngine
from synth.common import SynthEpisode


def chunk_channel(
    samples: np.ndarray, fs: float, chunk_s: float = 0.5
) -> Iterator[tuple[float, np.ndarray]]:
    """Yield (t0, values) blocks covering the full series from t=0."""
    n = len(samples)
    step = max(1, int(round(chunk_s * fs)))
    for i in range(0, n, step):
        yield i / fs, samples[i : i + step]


def ensure_rig_at(
    engine: StreamEngine,
    t_end: float,
    well: WellConfig | None = None,
) -> None:
    """Emit rig-context samples up through ``t_end`` (1 Hz, A10) — no future peek."""
    well = well or engine.well
    # Track how far we've filled via a private mark on the engine
    filled = getattr(engine, "_rig_filled_to", -1.0)
    t0 = int(filled) + 1 if filled >= 0 else 0
    t1 = int(np.floor(t_end))
    if t1 < t0:
        return
    for t in range(t0, t1 + 1):
        for name, val in (
            ("BIT_DEPTH", well.bit_depth_m),
            ("HOLE_DEPTH", well.hole_depth_m),
            ("BLOCK_POS", well.block_pos_m),
        ):
            engine.session.ingest(name, float(t), np.array([val]), 1.0)
    engine._rig_filled_to = float(t1)


def inject_rig_context(
    engine: StreamEngine,
    duration_s: float,
    well: WellConfig | None = None,
    chunk_s: float = 1.0,
) -> None:
    """Back-compat: fill rig context through ``duration_s`` (prefer ensure_rig_at)."""
    ensure_rig_at(engine, duration_s, well)


def feed_episode(
    engine: StreamEngine,
    episode: SynthEpisode,
    chunk_s: float = 0.5,
    include_rig: bool = True,
) -> StreamEngine:
    """Synchronously ingest an entire episode and run the evaluation schedule."""
    events: list[tuple[float, str, np.ndarray, float]] = []
    for name, ch in episode.channels.items():
        for t0, vals in chunk_channel(ch.samples, ch.fs, chunk_s):
            events.append((t0, name, vals, ch.fs))
    events.sort(key=lambda e: (e[0], e[1]))
    for t0, name, vals, fs in events:
        engine.session.ingest(name, t0, vals, fs)
        t_end = t0 + len(vals) / fs
        if include_rig:
            ensure_rig_at(engine, t_end)
        # Advance on episode data-time — not max(rig, channels), which would
        # skip the schedule if rig context were pre-filled into the future.
        engine.advance_to(t_end)
    return engine


def play(
    engine: StreamEngine,
    episode: SynthEpisode,
    speed: float = 1.0,
    chunk_s: float = 0.25,
) -> None:
    """Wall-clock paced replay at ``speed``× (1× = realtime, 8× = demo)."""
    events: list[tuple[float, str, np.ndarray, float]] = []
    for name, ch in episode.channels.items():
        for t0, vals in chunk_channel(ch.samples, ch.fs, chunk_s):
            events.append((t0, name, vals, ch.fs))
    events.sort(key=lambda e: (e[0], e[1]))
    wall0 = time.perf_counter()
    for t0, name, vals, fs in events:
        target = wall0 + t0 / max(speed, 1e-6)
        delay = target - time.perf_counter()
        if delay > 0:
            time.sleep(delay)
        engine.session.ingest(name, t0, vals, fs)
        t_end = t0 + len(vals) / fs
        ensure_rig_at(engine, t_end)
        engine.advance_to(t_end)
