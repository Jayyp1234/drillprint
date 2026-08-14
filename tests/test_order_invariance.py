"""M2: the A16 four-cell invariance suite — the §9 contribution as tests.

Library episodes are constant-RPM whirl (library seed); queries are freshly
seeded episodes (different noise, ring frequency, phases — the §14 split in
miniature). The resampler consumes ONLY the measured RPM_SURF channel (A16.2).

Cross-realization matching rides the GEOMETRY statistic (erratum E4): a
steady-state signature's offset histogram is flat by construction, so the
invariance claim — spectral geometry surviving RPM change — is tested on
distinct-matched-hash-types with its Poisson collision null. The offset
statistic keeps its role for evolving content and same-instance replay
(validated in test_matcher.py / test_order_domain.py).

Cells:                      time-domain (test-only set)   ORDER library
  constant-RPM query    →   MATCH                          MATCH
  ramp-RPM query        →   FAIL (smeared)                 MATCH (invariant)
"""

import numpy as np
import pytest

from engine.hashing import effective_hash_space, hash_constellation
from engine.matcher import match_hashes
from engine.order_domain import align_rpm, resample_to_order_domain
from engine.peaks import find_peaks
from engine.stft import frame_count, log_magnitude, stft_mag
from engine.types import PROFILES, Profile
from synth.whirl import FS as WHIRL_FS
from synth.whirl import generate

ORDER = PROFILES["ORDER"]
# Test-only hashed clone of HIGH (A16.2) — never in the production registry.
HIGH_TEST = Profile("HIGH_TEST", "time", 400.0, 1024, 256, 10.0, 1.0, 8, True)

# Hashing bands (A9): whirl ORDER band orders 2–14 → bins 8–56 at Δorder 0.25;
# time-domain test band 5–50 Hz → bins 13–128 at Δf 0.39.
ORDER_BAND = (8, 56)
TIME_BAND = (13, 128)

LIB_SEED, QUERY_SEED = 0, 7


def _order_pipeline(ep, sl=None):
    acc = ep.channels["ACC_LAT_X"]
    rpm = ep.channels["RPM_SURF"]
    aligned = align_rpm(rpm.samples, rpm.fs, len(acc.samples), acc.fs)
    od = resample_to_order_domain(acc.samples, acc.fs, aligned)
    if sl is not None:
        od = od[sl]
    peaks = find_peaks(
        log_magnitude(stft_mag(od, ORDER)),
        neighborhood=ORDER.peak_neighborhood,
        band=ORDER_BAND,
    )
    return hash_constellation(peaks, ORDER), frame_count(len(od), ORDER)


def _time_pipeline(ep, sl=None):
    x = ep.channels["ACC_LAT_X"].samples
    if sl is not None:
        x = x[sl]
    peaks = find_peaks(log_magnitude(stft_mag(x, HIGH_TEST)), band=TIME_BAND)
    return hash_constellation(peaks, HIGH_TEST), frame_count(len(x), HIGH_TEST)


def _match(query, lib_hashes, lib_frames, q_frames, profile, band):
    postings, types = {}, set()
    for h, t in lib_hashes:
        postings.setdefault(h, []).append(("LIB", t))
        types.add(h)
    res = match_hashes(
        query, postings, {"LIB": lib_frames}, q_frames,
        s_eff=effective_hash_space(profile, band),
        episode_distinct={"LIB": len(types)},
    )
    return res[0] if res else None


@pytest.fixture(scope="module")
def lib_const():
    return generate(n_blades=5, severity=2, profile="const", seed=LIB_SEED)


@pytest.fixture(scope="module")
def order_library(lib_const):
    return _order_pipeline(lib_const)


@pytest.fixture(scope="module")
def time_library(lib_const):
    return _time_pipeline(lib_const)


def _query_slice(domain):
    """A mid-episode query window: 16 rev (ORDER) / 10 s (time)."""
    if domain == "order":
        start = 40 * 64  # 40 revolutions in
        return slice(start, start + 16 * 64)
    start = int(20.0 * WHIRL_FS)  # 20 s in
    return slice(start, start + int(10.0 * WHIRL_FS))


# ---- the four cells (geometry statistic, cross-realization) ----

def test_cell_1_const_query_matches_time_domain_set(time_library):
    q_ep = generate(n_blades=5, severity=2, profile="const", seed=QUERY_SEED)
    q, qf = _time_pipeline(q_ep, _query_slice("time"))
    lib, lf = time_library
    top = _match(q, lib, lf, qf, HIGH_TEST, TIME_BAND)
    assert top is not None and top.geom_alert, top


def test_cell_2_ramp_query_fails_time_domain_set(time_library):
    q_ep = generate(n_blades=5, severity=2, profile="ramp", seed=QUERY_SEED)
    q, qf = _time_pipeline(q_ep, _query_slice("time"))
    lib, lf = time_library
    top = _match(q, lib, lf, qf, HIGH_TEST, TIME_BAND)
    assert top is None or not top.geom_alert, (
        "ramp smears time-domain fingerprints — a match here would refute §9's premise: "
        f"{top}"
    )
    assert top is None or not top.alert


def test_cell_3_const_query_matches_order_library(order_library):
    q_ep = generate(n_blades=5, severity=2, profile="const", seed=QUERY_SEED)
    q, qf = _order_pipeline(q_ep, _query_slice("order"))
    lib, lf = order_library
    top = _match(q, lib, lf, qf, ORDER, ORDER_BAND)
    assert top is not None and top.geom_alert, top


def test_cell_4_ramp_query_matches_order_library_THE_CONTRIBUTION(order_library):
    # RPM ramps 80→140 through the query window; the order-domain fingerprint
    # geometry must hold anyway. This is gate 3's core and the paper's spine.
    q_ep = generate(n_blades=5, severity=2, profile="ramp", seed=QUERY_SEED)
    q, qf = _order_pipeline(q_ep, _query_slice("order"))
    lib, lf = order_library
    top = _match(q, lib, lf, qf, ORDER, ORDER_BAND)
    assert top is not None and top.geom_alert, f"order-domain invariance failed: {top}"
    assert top.distinct_matched >= 12 and top.p_geom_corr < 1e-4


def test_dither_also_holds_in_order_domain(order_library):
    q_ep = generate(n_blades=5, severity=2, profile="dither", seed=QUERY_SEED)
    q, qf = _order_pipeline(q_ep, _query_slice("order"))
    lib, lf = order_library
    top = _match(q, lib, lf, qf, ORDER, ORDER_BAND)
    assert top is not None and top.geom_alert, top


def test_wrong_blade_count_scores_lower(order_library):
    # Specificity: an N_b=4 whirl (comb {4,5,6,9,10,11}) against the N_b=5
    # library (comb {5,6,7,11,12,13}) shares some bins but must score
    # measurably worse than the true class.
    lib, lf = order_library
    qf = frame_count(16 * 64, ORDER)
    true_q, _ = _order_pipeline(
        generate(n_blades=5, severity=2, profile="const", seed=QUERY_SEED),
        _query_slice("order"),
    )
    wrong_q, _ = _order_pipeline(
        generate(n_blades=4, severity=2, profile="const", seed=QUERY_SEED),
        _query_slice("order"),
    )
    true_top = _match(true_q, lib, lf, qf, ORDER, ORDER_BAND)
    wrong_top = _match(wrong_q, lib, lf, qf, ORDER, ORDER_BAND)
    assert true_top is not None and true_top.geom_alert
    assert wrong_top is None or wrong_top.distinct_matched < true_top.distinct_matched
