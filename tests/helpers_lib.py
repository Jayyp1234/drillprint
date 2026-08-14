"""Helpers to build small class-balanced libraries for M4/M5 tests."""

from __future__ import annotations

from pathlib import Path

from store.fingerprint_db import FingerprintDB
from synth import bit_bounce, normal, stick_slip, whirl
from synth.build_library import fingerprint_episode


def build_mini_library(
    db_path: str | Path,
    version: str = "v1",
    n_whirl: int = 6,
    n_bounce: int = 3,
    n_stick: int = 3,
    n_normal: int = 3,
) -> FingerprintDB:
    """Fingerprint a balanced mini-sweep and activate it."""
    db = FingerprintDB(db_path)
    db.create_library(version, notes="mini test library")
    episodes = []
    # Stride the whirl sweep so the mini library spans ALL blade counts —
    # sweep order is N_b-major, so the first 9 entries are all N_b=4 and an
    # N_b=5 query would have no matching corner. Pre-E7 noise-dense
    # fingerprints masked this coverage hole (cross-blade-count "matches"
    # rode on shared noise types); honest landmarks exposed it.
    whirl_params = list(whirl.sweep())[::3]
    for p in whirl_params[:n_whirl]:
        episodes.append(whirl.generate(**p, seed=0))
    for i, p in enumerate(bit_bounce.sweep()):
        if i >= n_bounce:
            break
        episodes.append(bit_bounce.generate(**p, seed=0))
    for i, p in enumerate(stick_slip.sweep()):
        if i >= n_stick:
            break
        episodes.append(stick_slip.generate(**p))
    for i, p in enumerate(normal.sweep()):
        if i >= n_normal:
            break
        episodes.append(normal.generate(**p, seed=0))

    for ep in episodes:
        fps, stats = fingerprint_episode(ep)
        db.add_episode(
            version, ep.slug, ep.dysfunction_class, ep.duration_s, ep.params,
            [(name, ch.fs) for name, ch in ep.channels.items()],
            fps, stats,
        )
    db.set_status(version, "validated")
    db.set_status(version, "approved", approved_by="test")
    db.activate(version)
    return db
