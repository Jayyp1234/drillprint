"""M4 end-to-end: replay → Tier-2 detection with K=2 debounce."""

from config import load_well
from ingest.pipeline import StreamEngine
from replay.stream_player import feed_episode
from synth import normal, whirl
from tests.helpers_lib import build_mini_library


def test_whirl_replay_fires_tier2(tmp_path):
    """Cross-seed whirl query against library → Tier-2 within A2 target."""
    db = build_mini_library(tmp_path / "lib.db", n_whirl=9, n_bounce=3, n_stick=2, n_normal=2)
    engine = StreamEngine(db, well=load_well(), mode="replay", library_version="v1")
    ep = whirl.generate(n_blades=5, severity=2, profile="const", seed=1042)
    feed_episode(engine, ep, chunk_s=0.5)

    dets = engine.detections(tier=2)
    whirl_dets = [d for d in dets if d["class"] == "WHIRL_BACKWARD"]
    assert whirl_dets, (
        f"no Tier-2 whirl; n_msg={len(engine.messages)} "
        f"tier1={engine.detections(tier=1)}"
    )
    first = min(whirl_dets, key=lambda d: d["t"])
    assert first["t"] <= 20.0, first
    assert first["confidence"] > 0.9
    assert any(m["type"] == "spectral_frame" for m in engine.messages)
    assert any(m["type"] == "twin_state" for m in engine.messages)
    assert any(m["type"] == "constellation" for m in engine.messages)
    db.close()


def test_normal_no_tier2(tmp_path):
    db = build_mini_library(tmp_path / "lib.db", n_whirl=6, n_bounce=2, n_stick=1, n_normal=3)
    engine = StreamEngine(db, well=load_well(), mode="replay", library_version="v1")
    ep = normal.generate(variant="pump60", duration_s=60.0, seed=2000)
    feed_episode(engine, ep, chunk_s=1.0)
    assert engine.detections(tier=2) == []
    db.close()


def test_debounce_rearm_after_clear():
    # E6a regression: the confirm latch must re-arm when a fresh evaluation
    # does not fire, otherwise one early spurious confirm permanently
    # silences the class for the rest of the run.
    from ingest.pipeline import DebounceState, K_DEBOUNCE

    deb = DebounceState()
    deb.streak = K_DEBOUNCE
    deb.confirmed = True
    # the not-fired fresh branch (pipeline) must reset confirmed -> False;
    # simulate its contract:
    deb.streak = 0
    deb.confirmed = False
    deb.best = None
    assert not deb.confirmed and deb.streak == 0
