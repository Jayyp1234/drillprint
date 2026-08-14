"""Benchmark protocol runner (M5 / A19 / §14).

    python -m bench.run --smoke          # CI-friendly short run
    python -m bench.run --full           # ≥10 runs × ≥30 min / SNR (slow)
    python -m bench.run --db PATH --library v1
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from bench.baseline import BandEnergyBaseline
from bench.calibrate import calibrate
from bench.scoring import Alert, Event, ScoreCard, score_run, t_tol, tier2_target
from config import load_well
from ingest.pipeline import StreamEngine
from replay.stream_player import feed_episode
from store.fingerprint_db import FingerprintDB
from synth import bit_bounce, normal, stick_slip, treatments, whirl
from synth.common import Channel, SynthEpisode


QUERY_SEED_BASE = 1000  # A19.3: disjoint from library 0-series


def _merge_cards(into: dict[str, ScoreCard], new: dict[str, ScoreCard]) -> None:
    """Pool per-run cards into per-SNR totals (H4 fix: micro-averaged from
    summed counts, never a mean of per-run ratios)."""
    for cls, card in new.items():
        agg = into.setdefault(cls, ScoreCard())
        agg.tp += card.tp
        agg.fp += card.fp
        agg.fn += card.fn
        agg.late += card.late
        agg.latencies.extend(card.latencies)


def _card_dict(card: ScoreCard, normal_hours: float) -> dict:
    d = card.as_dict()
    lat = sorted(card.latencies)
    d["median_latency_s"] = round(lat[len(lat) // 2], 3) if lat else None
    d["false_alerts_per_normal_hour"] = (
        round(card.fp / normal_hours, 3) if normal_hours > 0 else None
    )
    return d


# Channels whose VALUES feed control/kinematics, not dysfunction observation.
# RPM_SURF is the order-tracking reference (drive-side, A16 sensor noise is
# already inside the generators): SNR noise or gain error here rescales the
# order axis itself and corrupts every rotation-clocked match — harness bug
# H3 of the 2026-08-11 forensics. Treatments never touch it.
UNTREATED_CHANNELS = frozenset({"RPM_SURF"})


def _treat_composite(
    channels: dict[str, Channel],
    events: list[Event],
    snr_db: float,
    seed: int,
) -> dict[str, Channel]:
    """§12.5 treatments over the WHOLE run (H2 fix): constant sensor noise
    floor scaled so that the dysfunction segments sit at the target SNR,
    plus per-channel gain error — identically on normal and event spans."""
    rng = np.random.default_rng(seed)
    out: dict[str, Channel] = {}
    for name, ch in sorted(channels.items()):
        if name in UNTREATED_CHANNELS:
            out[name] = ch
            continue
        x = ch.samples
        # SNR reference = strongest event-span AC power on this channel
        p_ref = 0.0
        for ev in events:
            i0, i1 = int(ev.onset * ch.fs), int(ev.offset * ch.fs)
            if i1 > i0:
                p_ref = max(p_ref, float(np.var(x[i0:i1])))
        if p_ref == 0.0:
            p_ref = float(np.var(x))
        x = treatments.add_noise_snr(x, ch.fs, snr_db, rng, p_signal=p_ref)
        x, _ = treatments.apply_gain(x, rng)
        out[name] = Channel(ch.fs, x)
    return out


ALL_CHANNELS = {
    "TORQUE_SURF": 10.0, "RPM_SURF": 10.0, "RPM_DH": 10.0, "WOB": 10.0,
    "HOOKLOAD": 10.0, "ACC_AX": 100.0, "ACC_LAT_X": 400.0, "ACC_LAT_Y": 400.0,
}


def make_composite(
    seed: int,
    snr_db: float,
    dys_s: float = 300.0,
    normal_s: float = 240.0,
    include_stick_slip: bool = True,
) -> tuple[SynthEpisode, list[Event], float]:
    """One benchmark run: normal → dys → normal → dys → normal → dys → normal.

    All three classes appear once per run in seed-shuffled order (H6 fix:
    10 events/class/SNR at 10 runs instead of ~3). Separators are ≥ 2×W_LOW
    so every window fully recovers between events. Returns (episode, events,
    normal_hours) — normal_hours feeds the FA/data-hour denominator.
    """
    rng = np.random.default_rng(seed)
    order = ["WHIRL_BACKWARD", "BIT_BOUNCE"]
    if include_stick_slip:
        order.append("STICK_SLIP")
    rng.shuffle(order)
    variants = ["quiet", "pump60", "rough", "pump110"]

    segments: list[SynthEpisode] = []
    events: list[Event] = []
    t_cursor = 0.0

    def add_normal(i: int, dur: float) -> None:
        nonlocal t_cursor
        segments.append(normal.generate(
            variant=variants[i % len(variants)], duration_s=dur, seed=seed + 50 + i))
        t_cursor += dur

    add_normal(0, normal_s)
    for k, dys in enumerate(order):
        if dys == "WHIRL_BACKWARD":
            seg = whirl.generate(n_blades=5, severity=2, profile="const",
                                 duration_s=dys_s, seed=seed + k)
        elif dys == "BIT_BOUNCE":
            seg = bit_bounce.generate(severity=2, profile="const",
                                      duration_s=dys_s, seed=seed + k)
        else:
            seg = stick_slip.generate(length_m=3000.0, rpm_set=120.0,
                                      ts_ratio=1.6, j_b=200.0, duration_s=dys_s)
        segments.append(seg)
        events.append(Event(dys, t_cursor, t_cursor + seg.duration_s,
                            rpm=120.0, snr_db=snr_db))
        t_cursor += seg.duration_s
        add_normal(k + 1, normal_s)

    # merge on the canonical channel set; a segment missing a channel
    # contributes that channel's quiescent baseline, never zeros (H-fix:
    # zero-fill fakes dropouts and poisons plateau statistics)
    merged: dict[str, Channel] = {}
    for name, fs in ALL_CHANNELS.items():
        parts = []
        for seg_i, seg in enumerate(segments):
            if name in seg.channels:
                parts.append(seg.channels[name].samples)
            else:
                filler = normal.generate(
                    variant="quiet", duration_s=seg.duration_s,
                    seed=seed + 90 + seg_i)
                if name in filler.channels:
                    parts.append(filler.channels[name].samples)
                else:  # RPM_DH exists only in stick-slip segments: hold 120 RPM
                    n = int(round(seg.duration_s * fs))
                    parts.append(np.full(n, 120.0))
        merged[name] = Channel(fs, np.concatenate(parts))

    merged = _treat_composite(merged, events, snr_db, seed + 10)
    total = sum(s.duration_s for s in segments)
    normal_hours = (total - sum(e.offset - e.onset for e in events)) / 3600.0
    ep = SynthEpisode(
        slug=f"composite_{seed}_snr{int(snr_db)}",
        dysfunction_class="COMPOSITE",
        duration_s=total,
        channels=merged,
        params={"order": order, "snr_db": snr_db, "seed": seed},
    )
    return ep, events, normal_hours


def run_protocol(
    db_path: str | Path,
    library_version: str,
    snr_levels: list[float],
    n_runs: int,
    segment_s: float,
    include_stick_slip: bool = False,
    normal_s: float = 240.0,
) -> dict:
    t0 = time.perf_counter()
    db = FingerprintDB(db_path)
    st = db.status(library_version)
    if st == "built":
        db.set_status(library_version, "validated")
        st = "validated"
    if st == "validated":
        db.set_status(library_version, "approved", approved_by="bench")
    if db.active_version() != library_version:
        db.activate(library_version)

    well = load_well()
    baseline_cal = calibrate(
        budget_fa_per_hour=1.0, duration_s=min(300.0, max(60.0, segment_s))
    )
    tier1_cal = calibrate(
        budget_fa_per_hour=2.0, duration_s=min(300.0, max(60.0, segment_s))
    )
    baseline = BandEnergyBaseline(baseline_cal["thresholds"])

    per_snr: dict[str, dict] = {}
    for snr in snr_levels:
        cards_dp: dict[str, ScoreCard] = {}
        cards_bl: dict[str, ScoreCard] = {}
        data_hours = 0.0
        normal_hours = 0.0
        for run_i in range(n_runs):
            seed = QUERY_SEED_BASE + run_i + int(snr * 17)
            ep, events, n_hours = make_composite(
                seed, snr, dys_s=segment_s, normal_s=normal_s,
                include_stick_slip=include_stick_slip,
            )
            engine = StreamEngine(
                db, well=well, mode="replay",
                library_version=library_version,
                tier1_thresholds=tier1_cal["thresholds"],
            )
            feed_episode(engine, ep, chunk_s=1.0)
            alerts = [
                Alert(m["class"], float(m["t"]), int(m["tier"]))
                for m in engine.detections(tier=2)
            ]
            _merge_cards(cards_dp, score_run(events, alerts, tier=2))

            # H1 fix: baseline scored on the identical alert-stream contract
            bl_alerts = [
                Alert(cls, t, 2)
                for cls, t in baseline.scan(ep.channels, ep.duration_s)
            ]
            _merge_cards(cards_bl, score_run(events, bl_alerts, tier=2))

            data_hours += ep.duration_s / 3600.0
            normal_hours += n_hours

        per_snr[str(snr)] = {
            "drillprint": {c: _card_dict(v, normal_hours) for c, v in cards_dp.items()},
            "baseline": {c: _card_dict(v, normal_hours) for c, v in cards_bl.items()},
            "n_runs": n_runs,
            "data_hours": round(data_hours, 4),
            "normal_hours": round(normal_hours, 4),
        }

    for cls in ("STICK_SLIP", "WHIRL_BACKWARD", "BIT_BOUNCE"):
        for rpm in (60.0, 120.0):
            for snr in (0.0, 10.0):
                assert t_tol(cls, rpm, snr) >= tier2_target(cls, rpm, snr)

    report = {
        "protocol": "A19/§14",
        "harness": 2,  # 2026-08-11 forensics fixes H1–H6
        "normal_s": normal_s,
        "library_version": library_version,
        "snr_levels_db": snr_levels,
        "n_runs_per_snr": n_runs,
        "segment_s": segment_s,
        "calibration": {"baseline": baseline_cal, "tier1": tier1_cal},
        "results": per_snr,
        "elapsed_s": round(time.perf_counter() - t0, 2),
        "t_tol": {
            "STICK_SLIP": t_tol("STICK_SLIP"),
            "WHIRL_BACKWARD": t_tol("WHIRL_BACKWARD"),
            "BIT_BOUNCE": t_tol("BIT_BOUNCE"),
        },
    }
    db.close()
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="data/library.db")
    ap.add_argument("--library", default="v1")
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--out", default="bench/report.json")
    ap.add_argument("--snr", type=float, action="append", default=None,
                    help="restrict to specific SNR level(s) — enables one-process-per-SNR parallel runs")
    args = ap.parse_args()
    if args.full:
        snr_levels = args.snr or [20.0, 10.0, 3.0, 0.0]
        n_runs, segment_s, normal_s = 10, 300.0, 240.0
        include_ss = True
    else:
        snr_levels = [10.0]
        n_runs, segment_s, normal_s = 1, 180.0, 150.0
        include_ss = True
    report = run_protocol(
        args.db, args.library, snr_levels, n_runs, segment_s,
        include_stick_slip=include_ss, normal_s=normal_s,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps({
        k: report[k] for k in (
            "library_version", "snr_levels_db", "n_runs_per_snr",
            "elapsed_s", "t_tol",
        )
    }, indent=2))
    print(f"report -> {out}")


if __name__ == "__main__":
    main()
