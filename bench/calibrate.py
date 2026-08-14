"""Threshold calibration on normal-only validation runs (A2 / A19).

Fit baseline / Tier-1 thresholds to a target FA/data-hour budget, then freeze.
"""

from __future__ import annotations

import numpy as np

from engine.sssi import band_energy_rms, sssi
from synth import normal


def _metric_series(variant: str, seed: int, duration_s: float) -> dict[str, np.ndarray]:
    ep = normal.generate(variant=variant, duration_s=duration_s, seed=seed)
    out: dict[str, np.ndarray] = {}
    # SSSI on torque, stepped every 2 s
    torque = ep.channels["TORQUE_SURF"].samples
    fs_t = ep.channels["TORQUE_SURF"].fs
    f0 = 0.25
    win = int(2.0 / f0 * fs_t)
    step = int(2.0 * fs_t)
    sssi_vals = []
    for i in range(win, len(torque) + 1, step):
        sssi_vals.append(sssi(torque[i - win : i], fs_t, f0))
    out["STICK_SLIP"] = np.asarray(sssi_vals, dtype=np.float64)

    ax = ep.channels["ACC_LAT_X"].samples
    fs_a = ep.channels["ACC_LAT_X"].fs
    w = int(2.0 * fs_a)
    step_a = int(1.0 * fs_a)
    whirl_vals = [
        band_energy_rms(ax[i - w : i], fs_a, (5.0, 50.0))
        for i in range(w, len(ax) + 1, step_a)
    ]
    out["WHIRL_BACKWARD"] = np.asarray(whirl_vals, dtype=np.float64)

    az = ep.channels["ACC_AX"].samples
    fs_z = ep.channels["ACC_AX"].fs
    w = int(2.0 * fs_z)
    bounce_vals = [
        band_energy_rms(az[i - w : i], fs_z, (1.0, 20.0))
        for i in range(w, len(az) + 1, int(1.0 * fs_z))
    ]
    out["BIT_BOUNCE"] = np.asarray(bounce_vals, dtype=np.float64)
    return out


def calibrate(
    budget_fa_per_hour: float,
    duration_s: float = 600.0,
    seeds: tuple[int, ...] = (9001, 9002, 9003),
    variants: tuple[str, ...] = ("quiet", "pump60", "pump110"),
) -> dict:
    """Return frozen thresholds meeting the FA budget on normal-only data.

    Uses the empirical (1 - budget_rate) quantile of the metric on the
    validation pool — conservative and deterministic.
    """
    # eval cadence ~1–2 s → ~1800–3600 evals / hour
    evals_per_hour = 1800.0
    # Allow this many FA per hour → target quantile
    # P(metric >= thr) * evals/hour ≈ budget → survival = budget/evals
    survival = min(0.5, max(1e-6, budget_fa_per_hour / evals_per_hour))
    q = 1.0 - survival

    pooled: dict[str, list[float]] = {
        "STICK_SLIP": [], "WHIRL_BACKWARD": [], "BIT_BOUNCE": [],
    }
    hours = 0.0
    for seed in seeds:
        for variant in variants:
            series = _metric_series(variant, seed, duration_s)
            for k, v in series.items():
                pooled[k].extend(v.tolist())
            hours += duration_s / 3600.0

    thresholds = {
        k: float(np.quantile(np.asarray(v), q)) if v else 1.0
        for k, v in pooled.items()
    }
    return {
        "budget_fa_per_hour": budget_fa_per_hour,
        "validation_hours": round(hours, 3),
        "quantile": q,
        "thresholds": thresholds,
        "seeds": list(seeds),
        "variants": list(variants),
    }
