"""Constellation gates (spec §7 + A23 determinism pins)."""

import numpy as np

from engine.peaks import find_peaks
from engine.types import Peak


def _base(n_frames=10, n_bins=129, floor=0.0):
    return np.full((n_frames, n_bins), floor)


def test_injected_peaks_recovered_exactly():
    ls = _base()
    planted = [(1, 10), (1, 40), (4, 77), (8, 100)]
    for m, k in planted:
        ls[m, k] = 30.0
    got = [(p.m, p.k) for p in find_peaks(ls)]
    assert got == sorted(planted)


def test_constant_plateau_yields_no_peaks():
    # Dropout plateaus: every cell is a "local max", but the median+β gate
    # rejects them (spec §7 rationale, verified in the study).
    assert find_peaks(_base(floor=-40.0)) == []


def test_density_cap_keeps_strongest_five():
    ls = _base(n_frames=1)
    mags = {k: 20.0 + k / 10 for k in (5, 20, 35, 50, 65, 80, 95, 110)}
    for k, mag in mags.items():
        ls[0, k] = mag
    got = {p.k for p in find_peaks(ls)}
    assert got == {50, 65, 80, 95, 110}  # 5 strongest of 8


def test_tie_break_deterministic_lower_bin_wins():
    ls = _base(n_frames=1)
    ls[0, 30] = 25.0
    ls[0, 90] = 25.0  # exact tie, far apart
    got = find_peaks(ls, max_per_frame=1)
    assert [(p.m, p.k) for p in got] == [(0, 30)]
    # byte-identical across runs
    assert find_peaks(ls.copy(), max_per_frame=1) == got


def test_neighborhood_suppresses_adjacent_lesser_peak():
    ls = _base(n_frames=1)
    ls[0, 60] = 30.0
    ls[0, 62] = 29.0  # inside the (·,3) neighborhood of a stronger peak
    got = [(p.m, p.k) for p in find_peaks(ls)]
    assert got == [(0, 60)]


def test_below_threshold_peak_rejected():
    ls = _base(n_frames=1)
    ls[0, 60] = 5.0  # local max but only median+5 dB < β=8
    assert find_peaks(ls) == []


def test_returns_peak_dataclass_sorted():
    ls = _base()
    ls[3, 50] = 30.0
    ls[1, 80] = 30.0
    got = find_peaks(ls)
    assert got == [Peak(1, 80, 30.0), Peak(3, 50, 30.0)]
