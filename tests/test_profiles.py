"""Profile registry invariants (spec A1)."""

import pytest

from engine.types import PROFILES, frames_per_window


def test_window_invariant_every_hashed_profile():
    # A1: frames_per_window(W, profile) >= T_max + 3 for every hashed profile.
    for p in PROFILES.values():
        if p.hashed:
            assert frames_per_window(p) >= p.t_max + 3, p.name


def test_expected_frame_counts():
    assert frames_per_window(PROFILES["LOW"]) == 15
    assert frames_per_window(PROFILES["LOW_DEEP"]) == 15
    assert frames_per_window(PROFILES["MID"]) == 20
    assert frames_per_window(PROFILES["HIGH"]) == 12
    assert frames_per_window(PROFILES["ORDER"]) == 13


def test_bin_widths():
    assert PROFILES["LOW"].delta_f == pytest.approx(0.0390625)
    assert PROFILES["LOW_DEEP"].delta_f == pytest.approx(0.01953125)
    assert PROFILES["MID"].delta_f == pytest.approx(0.1953125)
    assert PROFILES["HIGH"].delta_f == pytest.approx(0.390625)
    assert PROFILES["ORDER"].delta_f == pytest.approx(0.25)  # orders/bin


def test_t_max_fits_hash_field():
    for p in PROFILES.values():
        if p.hashed:
            assert 1 <= p.t_max <= 63  # 6-bit Δt field


def test_f1_field_covers_all_bin_counts():
    for p in PROFILES.values():
        assert p.n_bins <= 1024  # 10-bit f1 field


def test_display_only_profiles_are_not_hashed():
    for name in ("MID", "HIGH", "LOW_DECIM"):
        assert not PROFILES[name].hashed
        assert PROFILES[name].t_max is None
