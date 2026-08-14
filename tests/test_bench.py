"""M5: scoring rules, T_tol invariant, report shape (gate 5 / A19)."""

import json

from bench.calibrate import calibrate
from bench.scoring import Alert, Event, score_run, t_tol, tier2_target
from tests.helpers_lib import build_mini_library


def test_t_tol_ge_a2_target():
    for cls in ("STICK_SLIP", "WHIRL_BACKWARD", "BIT_BOUNCE"):
        for rpm in (60.0, 120.0):
            for snr in (0.0, 10.0):
                assert t_tol(cls, rpm, snr) >= tier2_target(cls, rpm, snr)


def test_late_is_fn_not_fp():
    events = [Event("WHIRL_BACKWARD", onset=10.0, offset=70.0, rpm=120.0)]
    alerts = [Alert("WHIRL_BACKWARD", t=35.0, tier=2)]
    cards = score_run(events, alerts)
    c = cards["WHIRL_BACKWARD"]
    assert c.tp == 0 and c.fn == 1 and c.late == 1 and c.fp == 0


def test_tp_within_tol():
    events = [Event("WHIRL_BACKWARD", onset=10.0, offset=70.0)]
    alerts = [Alert("WHIRL_BACKWARD", t=18.0, tier=2)]
    c = score_run(events, alerts)["WHIRL_BACKWARD"]
    assert c.tp == 1 and c.fn == 0 and c.latencies == [8.0]


def test_wrong_class_is_fp():
    events = [Event("WHIRL_BACKWARD", onset=10.0, offset=70.0)]
    alerts = [Alert("BIT_BOUNCE", t=12.0, tier=2)]
    cards = score_run(events, alerts)
    assert cards["WHIRL_BACKWARD"].fn == 1
    assert cards["BIT_BOUNCE"].fp == 1


def test_calibration_records_thresholds():
    rec = calibrate(
        budget_fa_per_hour=2.0, duration_s=30.0, seeds=(1,), variants=("quiet",)
    )
    assert set(rec["thresholds"]) >= {"STICK_SLIP", "WHIRL_BACKWARD", "BIT_BOUNCE"}


def test_bench_smoke_report(tmp_path):
    """One-command reproduction path produces report.json with calibration."""
    from bench.run import run_protocol

    db = build_mini_library(
        tmp_path / "lib.db", n_whirl=6, n_bounce=3, n_stick=2, n_normal=2
    )
    db.close()
    report = run_protocol(
        tmp_path / "lib.db", "v1", snr_levels=[10.0], n_runs=1, segment_s=40.0,
        normal_s=40.0,
    )
    out = tmp_path / "report.json"
    out.write_text(json.dumps(report))
    data = json.loads(out.read_text())
    assert data["protocol"].startswith("A19")
    assert "baseline" in data["calibration"]
    assert "tier1" in data["calibration"]
    assert "thresholds" in data["calibration"]["baseline"]
    assert "10.0" in data["results"]
