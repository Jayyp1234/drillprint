"""Hashing gates (spec §21 M0: synthetic constellation → exact hash set)."""

import pytest

from engine.hashing import FANOUT, K_MAX, hash_constellation, pack_hash, unpack_hash
from engine.types import PROFILES, Peak

LOW = PROFILES["LOW"]  # t_max = 12
ORDER = PROFILES["ORDER"]  # t_max = 10


def test_exact_hash_set_hand_computed():
    peaks = [Peak(0, 10, 0.0), Peak(1, 12, 0.0), Peak(2, 50, 0.0)]
    got = hash_constellation(peaks, LOW)
    expected = [
        (pack_hash(10, 2, 1), 0),   # (0,10) -> (1,12)
        (pack_hash(10, 40, 2), 0),  # (0,10) -> (2,50)
        (pack_hash(12, 38, 1), 1),  # (1,12) -> (2,50)
    ]
    assert got == expected


def test_pack_unpack_roundtrip_boundaries():
    for f1 in (0, 511, 1023):
        for dk in (-63, -1, 0, 1, 63):
            for dt in (1, 12, 63):
                h = pack_hash(f1, dk, dt)
                assert 0 <= h < 2**24
                assert unpack_hash(h) == (f1, dk, dt)


def test_pack_rejects_out_of_range():
    with pytest.raises(ValueError):
        pack_hash(1024, 0, 1)
    with pytest.raises(ValueError):
        pack_hash(0, 0, 0)
    with pytest.raises(ValueError):
        pack_hash(0, 0, 64)
    with pytest.raises(ValueError):
        pack_hash(0, 200, 1)


def test_per_profile_t_max_respected():
    # Δt = 13 exceeds LOW's t_max=12 but a Δt=11 pair also exceeds ORDER's 10?
    peaks = [Peak(0, 10, 0.0), Peak(13, 12, 0.0)]
    assert hash_constellation(peaks, LOW) == []
    peaks11 = [Peak(0, 10, 0.0), Peak(11, 12, 0.0)]
    assert hash_constellation(peaks11, LOW) != []  # 11 <= 12: pairs
    assert hash_constellation(peaks11, ORDER) == []  # 11 > 10: no pairs


def test_k_max_rejects_wide_bin_jumps():
    peaks = [Peak(0, 10, 0.0), Peak(1, 10 + K_MAX + 1, 0.0)]
    assert hash_constellation(peaks, LOW) == []
    peaks_ok = [Peak(0, 10, 0.0), Peak(1, 10 + K_MAX, 0.0)]
    assert len(hash_constellation(peaks_ok, LOW)) == 1


def test_fanout_cap_nearest_first():
    # 10 valid targets; only the FANOUT nearest (by Δt, then |Δk|) are paired.
    anchor = Peak(0, 100, 0.0)
    targets = [Peak(dt, 100 + dt, 0.0) for dt in range(1, 11)]
    got = hash_constellation([anchor] + targets, LOW)
    anchored = [h for h, t in got if t == 0]
    assert len(anchored) == FANOUT
    dts = sorted(unpack_hash(h)[2] for h in anchored)
    assert dts == list(range(1, FANOUT + 1))  # Δt 1..8 chosen, 9..10 dropped


def test_display_profile_refuses_hashing():
    with pytest.raises(ValueError):
        hash_constellation([Peak(0, 1, 0.0)], PROFILES["HIGH"])


def test_deterministic_output():
    peaks = [Peak(m, (m * 7) % 120, float(m)) for m in range(30)]
    assert hash_constellation(peaks, LOW) == hash_constellation(list(peaks), LOW)
