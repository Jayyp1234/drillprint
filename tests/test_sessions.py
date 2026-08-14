"""M4: ingest session contracts (A15)."""

import numpy as np
import pytest

from ingest.sessions import Session


def test_monotonic_violation_dropped():
    s = Session(mode="replay")
    assert s.ingest("TORQUE_SURF", 0.0, [1.0, 2.0], 10.0)["ack"]
    ack = s.ingest("TORQUE_SURF", -1.0, [3.0], 10.0)
    assert ack["ack"] is False
    assert ack["reason"] == "non_monotonic"
    assert s.health.monotonic_violations == 1


def test_small_gap_interpolated():
    s = Session(mode="replay")
    s.ingest("TORQUE_SURF", 0.0, np.ones(10), 10.0)  # covers [0, 1)
    # gap of 0.3 s ≤ LOW hop 6.4 s → interpolate
    ack = s.ingest("TORQUE_SURF", 1.3, np.ones(10) * 2.0, 10.0)
    assert ack["ack"]
    assert s.health.gaps_interpolated == 1


def test_large_gap_skipped():
    s = Session(mode="replay")
    s.ingest("ACC_LAT_X", 0.0, np.zeros(400), 400.0)  # [0, 1)
    # 2 s gap > 0.5 s default hop → skip region
    s.ingest("ACC_LAT_X", 3.0, np.zeros(400), 400.0)
    assert s.health.gaps_skipped == 1
    assert s.overlaps_skip(1.0, 2.5)


def test_live_epoch_latches():
    s = Session(mode="live")
    ack = s.ingest("RPM_SURF", 1_000_000.0, [120.0], 10.0)
    assert ack["ack"]
    assert abs(ack["t"] - 0.0) < 1e-12
    ack2 = s.ingest("RPM_SURF", 1_000_000.5, [121.0], 10.0)
    assert abs(ack2["t"] - 0.5) < 1e-12


def test_get_window_aligns_rpm():
    s = Session(mode="replay")
    s.ingest("ACC_LAT_X", 0.0, np.arange(800, dtype=float), 400.0)
    s.ingest("RPM_SURF", 0.0, np.array([60.0, 120.0]), 1.0)
    win = s.get_window(["ACC_LAT_X", "RPM_SURF"], (0.0, 2.0), align_to="ACC_LAT_X")
    assert win is not None
    assert len(win["ACC_LAT_X"]) == len(win["RPM_SURF"])
    assert win["RPM_SURF"][0] == pytest.approx(60.0, abs=1)
    assert win["RPM_SURF"][-1] == pytest.approx(120.0, abs=1)
