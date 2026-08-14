"""Matcher gates (spec §21 M0: planted offset → histogram spike at δ*;
corrected Poisson significance sanity — A3)."""

import numpy as np

from engine.matcher import match_hashes
from engine.types import PROFILES, Peak
from engine.hashing import hash_constellation
from engine.stft import log_magnitude

LOW = PROFILES["LOW"]
QUERY_FRAMES = 15  # frames_per_window(LOW)


def _random_constellation(rng, n_frames, n_bins=129, per_frame=5):
    peaks = []
    for m in range(n_frames):
        for k in sorted(rng.choice(n_bins, size=per_frame, replace=False)):
            peaks.append(Peak(m, int(k), 0.0))
    return peaks


def _postings_from(episodes):
    postings = {}
    for ep_id, hashes in episodes.items():
        for h, t in hashes:
            postings.setdefault(h, []).append((ep_id, t))
    return postings


def test_planted_offset_produces_spike_and_alert():
    rng = np.random.default_rng(42)
    lib_peaks = _random_constellation(rng, n_frames=60)
    lib_hashes = hash_constellation(lib_peaks, LOW)
    episodes = {"SS-001": lib_hashes}
    # Query = the episode's frames [30, 45), re-clocked to query time 0.
    offset = 30
    query = [
        (h, t - offset) for h, t in lib_hashes if offset <= t < offset + QUERY_FRAMES
    ]
    assert len(query) >= 8, "planted query must carry enough hashes"
    results = match_hashes(
        query, _postings_from(episodes), {"SS-001": 60}, QUERY_FRAMES
    )
    top = results[0]
    assert top.episode_id == "SS-001"
    assert top.alert
    assert top.score >= 8
    assert top.p_corr < 1e-10
    assert top.confidence > 0.9999
    # δ* bin corresponds to the planted offset.
    assert top.delta_star == offset // 3


def test_random_noise_never_alerts():
    # Uniform random query hashes vs a realistic library: no Tier-2 alert.
    rng = np.random.default_rng(7)
    episodes = {
        f"EP-{i:03d}": [
            (int(h), int(t))
            for h, t in zip(
                rng.integers(0, 2**24, size=300), rng.integers(0, 60, size=300)
            )
        ]
        for i in range(50)
    }
    episode_frames = {ep: 60 for ep in episodes}
    query = [
        (int(h), int(t))
        for h, t in zip(
            rng.integers(0, 2**24, size=600), rng.integers(0, QUERY_FRAMES, size=600)
        )
    ]
    results = match_hashes(query, _postings_from(episodes), episode_frames, QUERY_FRAMES)
    assert all(not r.alert for r in results)


def test_s_min_blocks_small_scores_even_when_significant():
    # 7 perfectly aligned hashes in an otherwise silent library: p_corr is tiny
    # but score < 8 must not alert (A3.3).
    hashes = [(1000 + i, 20 + i) for i in range(7)]
    episodes = {"EP-A": hashes}
    query = [(1000 + i, i) for i in range(7)]  # all land in δ-bin 20//3
    results = match_hashes(query, _postings_from(episodes), {"EP-A": 60}, QUERY_FRAMES)
    top = results[0]
    assert top.score == 7
    assert top.p_corr < 1e-4  # significant...
    assert not top.alert  # ...but blocked by s_min


def test_p_corr_monotone_in_score():
    def p_at(n_aligned):
        hashes = [(5000 + i, 30 + i) for i in range(n_aligned)]
        query = [(5000 + i, i) for i in range(n_aligned)]
        res = match_hashes(
            query, _postings_from({"EP": hashes}), {"EP": 60}, QUERY_FRAMES
        )
        return res[0].p_corr

    assert p_at(20) < p_at(10) < p_at(8)


def test_lambda_excludes_max_bin():
    # 20 aligned pairs at one offset + 5 scattered: λ must reflect only the
    # scattered background (floored at 0.05), not the true-match spike.
    aligned = [(9000 + i, 30 + i) for i in range(20)]
    scattered = [(9500 + i, (7 * i) % 55) for i in range(5)]
    episodes = {"EP": aligned + scattered}
    query = [(9000 + i, i) for i in range(20)] + [(9500 + i, 3 * i % 11) for i in range(5)]
    results = match_hashes(query, _postings_from(episodes), {"EP": 60}, QUERY_FRAMES)
    top = results[0]
    assert top.score >= 20
    assert top.lam <= 0.3  # background-scale, not (pairs/n_bins) with the spike in


def test_no_collisions_returns_empty():
    assert match_hashes([(1, 0)], {}, {"EP": 60}, QUERY_FRAMES) == []


def test_end_to_end_signal_to_alert():
    """Integration: sinusoid comb -> STFT -> peaks -> hashes -> planted-offset match."""
    from engine.peaks import find_peaks
    from engine.stft import stft_mag

    rng = np.random.default_rng(3)
    fs, dur = LOW.rate, 600.0
    t = np.arange(int(dur * fs)) / fs
    f0 = 0.26  # Hz — typical stick-slip fundamental at 3 km (spec §2)
    x = sum(np.sin(2 * np.pi * n * f0 * t) / n for n in (1, 2, 3, 5))
    x = x + 0.05 * rng.normal(size=len(t))

    lib_peaks = find_peaks(log_magnitude(stft_mag(x, LOW)))
    lib_hashes = hash_constellation(lib_peaks, LOW)
    assert len(lib_hashes) > 100

    # Query: a 120 s slice starting at 192 s = frame offset 30.
    offset_frames = 30
    start = offset_frames * LOW.hop
    xq = x[start : start + int(120 * fs)]
    q_peaks = find_peaks(log_magnitude(stft_mag(xq, LOW)))
    q_hashes = hash_constellation(q_peaks, LOW)
    n_lib_frames = (len(x) - LOW.n) // LOW.hop + 1

    results = match_hashes(
        q_hashes, _postings_from({"SS-INT": lib_hashes}), {"SS-INT": n_lib_frames}, 15
    )
    top = results[0]
    assert top.episode_id == "SS-INT"
    assert top.alert
    assert abs(top.delta_star * 3 - offset_frames) <= 3
