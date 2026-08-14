"""M3 gates: schema, state machine, filtered postings, and the store-backed
end-to-end match (§21 M3, A12, §31)."""

import numpy as np
import pytest

from engine.hashing import effective_hash_space
from engine.matcher import match_hashes
from engine.types import PROFILES
from store.fingerprint_db import PIPELINES, FingerprintDB, StateError
from synth import whirl
from synth.build_library import build, fingerprint_channel, fingerprint_episode


@pytest.fixture()
def db(tmp_path):
    d = FingerprintDB(tmp_path / "t.db")
    yield d
    d.close()


def _add_tiny_episode(db, version="v1", slug="ep/one", cls="WHIRL_BACKWARD"):
    db.add_episode(
        version, slug, cls, 60.0, {"p": 1},
        [("ACC_LAT_X", 400.0)],
        [(111, "ACC_LAT_X", "ORDER", "order", 3),
         (222, "ACC_LAT_X", "ORDER", "order", 7)],
        [("ORDER", 117, 2, 2)],
    )


# ---- state machine (§31) ----

def test_state_machine_happy_path(db):
    db.create_library("v1")
    assert db.status("v1") == "built"
    db.set_status("v1", "validated")
    db.set_status("v1", "approved", approved_by="jp")
    db.activate("v1")
    assert db.active_version() == "v1"


def test_activate_rejects_unapproved(db):
    db.create_library("v1")
    with pytest.raises(StateError):
        db.activate("v1")
    db.set_status("v1", "validated")
    with pytest.raises(StateError):
        db.activate("v1")


def test_no_status_skipping(db):
    db.create_library("v1")
    with pytest.raises(StateError):
        db.set_status("v1", "approved", approved_by="jp")  # skips 'validated'


def test_approval_requires_name(db):
    db.create_library("v1")
    db.set_status("v1", "validated")
    with pytest.raises(StateError):
        db.set_status("v1", "approved")


def test_rollback_by_activating_earlier_version(db):
    for v in ("v1", "v2"):
        db.create_library(v)
        db.set_status(v, "validated")
        db.set_status(v, "approved", approved_by="jp")
    db.activate("v2")
    db.activate("v1")  # rollback (§20 Library screen)
    assert db.active_version() == "v1"


# ---- postings filters (A12/§11) ----

def test_postings_filtered_by_profile_domain_channel_and_version(db):
    db.create_library("v1")
    _add_tiny_episode(db)
    db.set_status("v1", "validated")
    db.set_status("v1", "approved", approved_by="jp")
    db.activate("v1")

    hit = db.postings([111, 222, 333], "ORDER", "order", ("ACC_LAT_X",))
    assert set(hit) == {111, 222}
    assert hit[111] == [("v1/ep/one", 3)]
    # wrong profile / domain / channel: silence
    assert db.postings([111], "LOW", "time", ("ACC_LAT_X",)) == {}
    assert db.postings([111], "ORDER", "order", ("ACC_AX",)) == {}


def test_postings_require_active_library(db):
    db.create_library("v1")
    _add_tiny_episode(db)
    with pytest.raises(StateError):
        db.postings([111], "ORDER", "order", ("ACC_LAT_X",))


def test_duplicate_slug_rejected_within_a_version(db):
    db.create_library("v1")
    _add_tiny_episode(db)
    with pytest.raises(Exception):
        _add_tiny_episode(db)


def test_same_slug_allowed_across_versions(db):
    # Regression (user-hit): building v2 into the same DB re-generates the
    # same sweep corners with the same canonical slugs — episode identity is
    # (library_version, slug), never slug alone.
    db.create_library("v1")
    db.create_library("v2")
    _add_tiny_episode(db, version="v1")
    _add_tiny_episode(db, version="v2")
    ids = [r[0] for r in db.conn.execute("SELECT id FROM episodes ORDER BY id")]
    assert ids == ["v1/ep/one", "v2/ep/one"]
    # postings stay version-scoped
    db.set_status("v2", "validated")
    db.set_status("v2", "approved", approved_by="jp")
    db.activate("v2")
    hit = db.postings([111], "ORDER", "order", ("ACC_LAT_X",))
    assert hit[111] == [("v2/ep/one", 3)]


def test_old_schema_db_rejected_with_clear_error(tmp_path):
    import sqlite3 as sq

    p = tmp_path / "old.db"
    c = sq.connect(p)
    c.execute("CREATE TABLE episodes (id TEXT PRIMARY KEY)")  # pre-v2 relic
    c.commit(); c.close()
    with pytest.raises(StateError, match="schema"):
        FingerprintDB(p)


def test_reference_tables_seeded(db):
    profiles = dict(db.conn.execute("SELECT name, hashed FROM profiles").fetchall())
    assert profiles["ORDER"] == 1 and profiles["HIGH"] == 0
    rows = db.conn.execute(
        "SELECT role FROM class_bindings WHERE class='BIT_BOUNCE' AND channel='WOB'"
    ).fetchall()
    assert rows == [("display",)]  # A9: WOB display-only


# ---- store-backed end-to-end match (the real M3 proof) ----

def test_small_build_and_store_backed_geometry_match(tmp_path):
    # Two-episode library built through the real pipeline, then a fresh-seed
    # ramp query matched through the store's postings path — the M3 proof.
    db = FingerprintDB(tmp_path / "lib.db")
    db.create_library("v1")
    for params in ({"n_blades": 5, "severity": 2, "profile": "const"},
                   {"n_blades": 4, "severity": 2, "profile": "const"}):
        ep = whirl.generate(**params, seed=0)
        fps, stats = fingerprint_episode(ep)
        db.add_episode("v1", ep.slug, ep.dysfunction_class, ep.duration_s,
                       ep.params, [(n, c.fs) for n, c in ep.channels.items()],
                       fps, stats)
    db.set_status("v1", "validated")
    db.set_status("v1", "approved", approved_by="jp")
    db.activate("v1")

    # Fresh-seed query (cross-realization), through the store's postings path.
    cfg = PIPELINES["WHIRL_BACKWARD"]
    q_ep = whirl.generate(n_blades=5, severity=2, profile="ramp", seed=1007)
    q_hashes, _ = fingerprint_channel(q_ep, "ACC_LAT_X", "ORDER", "order", cfg["band"])
    start = 40 * 64
    window = [(h, t - 40) for h, t in q_hashes if 40 <= t < 53]
    postings = db.postings([h for h, _ in window], "ORDER", "order", cfg["channels"])
    results = match_hashes(
        window, postings,
        db.episode_frames("ORDER"), 13,
        s_eff=effective_hash_space(PROFILES["ORDER"], cfg["band"]),
        episode_distinct=db.episode_distinct("ORDER"),
    )
    assert results, "no candidates from store postings"
    top = results[0]
    assert top.episode_id == "v1/whirl/Nb5_sev2_const"  # right episode wins
    assert top.geom_alert
    others = [r for r in results if r.episode_id != top.episode_id]
    assert all(r.distinct_matched < top.distinct_matched for r in others)
    db.close()


def test_class_matcher_two_stage_path(tmp_path):
    # The production query path (geometry screen -> evolving postings ->
    # dual-statistic matcher) must agree with the direct path on the winner
    # and stay under the §18 latency gate.
    import time

    from store.query import ClassMatcher

    db = FingerprintDB(tmp_path / "cm.db")
    db.create_library("v1")
    for nb in (4, 5, 6):
        ep = whirl.generate(n_blades=nb, severity=2, profile="const", seed=0)
        fps, stats = fingerprint_episode(ep)
        db.add_episode("v1", ep.slug, ep.dysfunction_class, ep.duration_s,
                       ep.params, [(n, c.fs) for n, c in ep.channels.items()],
                       fps, stats)
    db.set_status("v1", "validated")
    db.set_status("v1", "approved", approved_by="jp")
    db.activate("v1")

    cfg = PIPELINES["WHIRL_BACKWARD"]
    q_ep = whirl.generate(n_blades=5, severity=2, profile="ramp", seed=1007)
    q_hashes, _ = fingerprint_channel(q_ep, "ACC_LAT_X", "ORDER", "order", cfg["band"])
    window = [(h, t - 40) for h, t in q_hashes if 40 <= t < 53]

    matcher = ClassMatcher(db, "WHIRL_BACKWARD")
    results = matcher.evaluate(window, 13)
    assert results and results[0].episode_id == "v1/whirl/Nb5_sev2_const"
    assert results[0].geom_alert

    t0 = time.perf_counter()
    for _ in range(10):
        matcher.evaluate(window, 13)
    assert (time.perf_counter() - t0) / 10 < 0.010, "§18 gate: eval > 10 ms"
    db.close()


def test_stats_counts(tmp_path):
    db = FingerprintDB(tmp_path / "s.db")
    db.create_library("v1")
    ep = whirl.generate(n_blades=5, severity=1, profile="const", seed=0)
    fps, stats = fingerprint_episode(ep)
    db.add_episode("v1", ep.slug, ep.dysfunction_class, ep.duration_s, ep.params,
                   [(n, c.fs) for n, c in ep.channels.items()], fps, stats)
    s = db.stats("v1")
    assert s["episodes_by_class"] == {"WHIRL_BACKWARD": 1}
    assert s["n_hashes"] == len(fps) > 0
    # episode_profiles stats agree with the fingerprint table
    n_distinct = db.conn.execute(
        "SELECT n_distinct FROM episode_profiles WHERE profile='ORDER'"
    ).fetchone()[0]
    assert n_distinct == len({h for h, *_ in fps})
    db.close()
