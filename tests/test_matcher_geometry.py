"""Unit gates for the E4 geometry statistic in the matcher."""

import numpy as np

from engine.matcher import match_hashes


def _postings(hashes):
    out = {}
    for h, t in hashes:
        out.setdefault(h, []).append(("EP", t))
    return out


S_EFF = 62_230  # ORDER whirl band (see hashing.effective_hash_space doctest)


def test_geometry_fields_inert_without_params():
    lib = [(100 + i, i) for i in range(20)]
    res = match_hashes([(100, 0)], _postings(lib), {"EP": 60}, 13)
    assert res[0].p_geom_corr is None
    assert not res[0].geom_alert


def test_stationary_overlap_fires_geometry_not_offset():
    # A stationary comb: 30 hash types, each present at EVERY library frame.
    # A cross-realization query shares 20 types at arbitrary offsets: the
    # offset histogram is flat (no alert) but geometry must fire — this IS
    # the E4 scenario.
    types = list(range(1000, 1030))
    lib = [(h, t) for h in types for t in range(100)]
    rng = np.random.default_rng(0)
    query = [(h, int(rng.integers(0, 13))) for h in types[:20]]
    res = match_hashes(
        query, _postings(lib), {"EP": 100}, 13,
        s_eff=S_EFF, episode_distinct={"EP": len(types)},
    )
    top = res[0]
    assert not top.alert  # flat histogram: max bin ≈ uniform level
    assert top.distinct_matched == 20
    assert top.geom_alert and top.p_geom_corr < 1e-4


def test_random_types_do_not_fire_geometry():
    rng = np.random.default_rng(1)
    lib = [(int(h), int(t)) for h, t in zip(
        rng.integers(0, 2**24, 500), rng.integers(0, 100, 500))]
    query = [(int(h), int(t)) for h, t in zip(
        rng.integers(0, 2**24, 300), rng.integers(0, 13, 300))]
    res = match_hashes(
        query, _postings(lib), {"EP": 100}, 13,
        s_eff=S_EFF, episode_distinct={"EP": 500},
    )
    assert all(not r.geom_alert for r in res)


def test_d_min_blocks_small_overlaps():
    # 11 shared types < d_min = 12: significant or not, no geometry alert.
    types = list(range(500, 511))
    lib = [(h, t) for h in types for t in range(50)]
    query = [(h, 3) for h in types]
    res = match_hashes(
        query, _postings(lib), {"EP": 50}, 13,
        s_eff=S_EFF, episode_distinct={"EP": len(types)},
    )
    top = res[0]
    assert top.distinct_matched == 11
    assert not top.geom_alert


def test_geometry_counts_override_and_stationary_only_episode():
    # Two-stage path (E4): geometry counts come from the SQL screen; an
    # episode whose matches are all stationary types has NO postings but must
    # still surface with empty offset statistics and a live geometry alert.
    geo = {"EP": 25}
    res = match_hashes(
        [(1, 0)], {}, {"EP": 100}, 13,
        s_eff=S_EFF, episode_distinct={"EP": 300}, geometry_counts=geo,
    )
    top = res[0]
    assert top.score == 0 and top.p_corr == 1.0 and not top.alert
    assert top.distinct_matched == 25
    assert top.geom_alert


def test_confidence_uses_best_statistic():
    types = list(range(2000, 2040))
    lib = [(h, t) for h in types for t in range(100)]
    query = [(h, 5) for h in types[:30]]
    res = match_hashes(
        query, _postings(lib), {"EP": 100}, 13,
        s_eff=S_EFF, episode_distinct={"EP": len(types)},
    )
    top = res[0]
    assert top.geom_alert
    assert top.confidence > 0.9999  # driven by p_geom_corr, not the flat offset stat


def test_corroboration_gate_blocks_flat_histogram_geometry():
    # E6c regression: on TIME-domain pipelines a geometry alert requires
    # offset corroboration — structured noise overlapping the comb type-region
    # produces high distinct counts with a FLAT offset histogram (p_off ~ 1)
    # and must not alert; a genuine deterministic-library match carries
    # diagonal alignment and passes.
    from engine.matcher import match_hashes

    s_eff = 152_400
    episode_frames = {"v/ss/noise-like": 25, "v/ss/genuine": 25}
    episode_distinct = {"v/ss/noise-like": 800, "v/ss/genuine": 800}

    # noise-like: 24 distinct types matched, offsets scattered uniformly
    postings = {}
    q = []
    for i in range(24):
        h = 1000 + i
        postings[h] = [("v/ss/noise-like", (i * 7) % 90)]
        q.append((h, (i * 13) % 15))
    res = match_hashes(
        q, postings, episode_frames, 15,
        s_eff=s_eff, episode_distinct=episode_distinct,
        require_offset_corroboration=True,
    )
    top = res[0]
    assert top.distinct_matched == 24 and top.p_geom_corr < 1e-4
    assert not top.geom_alert            # flat histogram: corroboration fails

    # genuine: same distinct count but offset-consistent (all delta = 30)
    postings = {}
    q = []
    for i in range(24):
        h = 2000 + i
        t_q = (i * 13) % 15
        postings[h] = [("v/ss/genuine", t_q + 30)]
        q.append((h, t_q))
    res = match_hashes(
        q, postings, episode_frames, 15,
        s_eff=s_eff, episode_distinct=episode_distinct,
        require_offset_corroboration=True,
    )
    top = res[0]
    assert top.episode_id == "v/ss/genuine"
    assert top.geom_alert                # aligned: corroboration passes
