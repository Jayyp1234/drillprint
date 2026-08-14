"""M4: twin kinematics + gate-6 backend half (§29 / A5 / A8)."""

import math

from config import load_well
from engine.twin_kinematics import TwinKinematics, torsional_stiffness_at, twist_rad
from ingest.pipeline import StreamEngine
from replay.stream_player import feed_episode
from synth import whirl
from tests.helpers_lib import build_mini_library


def test_a8_twist_exact():
    """Normative §24 example: 14.8 kN·m at 3014.1 m → 47.16 rad."""
    assert abs(torsional_stiffness_at(3014.1) - 313.85) < 0.01
    assert abs(twist_rad(14.8, 3014.1) - 47.16) < 0.01


def test_whirl_phase_integrates_at_minus_nb_omega():
    kin = TwinKinematics(n_blades=5)
    rpm = 120.0
    omega = rpm * 2 * math.pi / 60.0
    dt = 0.04
    for _ in range(25):
        kin.step(dt, rpm, whirl_active=True)
    expected = -5 * omega * 1.0
    assert abs(kin.whirl_phase_rad - expected) < 1e-9


def test_gate6_twin_state_log(tmp_path):
    """Gate 6 backend: twist=T/k, whirl phase continuous, tier semantics, rig channels."""
    db = build_mini_library(tmp_path / "lib.db", n_whirl=6, n_bounce=1, n_stick=1, n_normal=1)
    well = load_well()
    engine = StreamEngine(db, well=well, mode="replay", library_version="v1")
    ep = whirl.generate(n_blades=5, severity=2, profile="const", seed=1042)
    feed_episode(engine, ep, chunk_s=1.0)

    twins = engine.twin_log()
    assert len(twins) > 10
    for tw in twins[10:20]:
        assert tw["bit_depth_m"] == well.bit_depth_m
        assert tw["hole_depth_m"] == well.hole_depth_m
        assert "block_pos_m" in tw
        if tw["torque_knm"] != 0 and tw["bit_depth_m"] > 0:
            assert abs(
                tw["twist_rad"] - twist_rad(tw["torque_knm"], tw["bit_depth_m"])
            ) < 1e-9
        if not tw["whirl"]["active"]:
            assert tw["whirl"]["order"] is None
            assert tw["whirl"]["eccentricity"] == 0.0

    # Gate 6: phase never advances WHILE inactive (it freezes, not resets —
    # comparing across an active interval was asserting the old scheduler
    # bug where whirl never confirmed at all).
    for a, b in zip(twins, twins[1:]):
        if not a["whirl"]["active"] and not b["whirl"]["active"]:
            assert abs(a["whirl"]["phase_rad"] - b["whirl"]["phase_rad"]) < 1e-12

    active = [tw for tw in twins if tw["whirl"]["active"]]
    if len(active) >= 3:
        dt = active[1]["t"] - active[0]["t"]
        omega = active[0]["rpm_surface"] * 2 * math.pi / 60.0
        dphi = active[1]["whirl"]["phase_rad"] - active[0]["whirl"]["phase_rad"]
        assert abs(dphi - (-well.n_blades * omega * dt)) < 1e-6

    db.close()
