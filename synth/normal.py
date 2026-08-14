"""Normal-drilling generator: the negative class (spec §12.4, A10/A11).

Emits the full surface set — TORQUE_SURF, RPM_SURF, WOB (10 Hz), ACC_AX
(100 Hz), ACC_LAT_X/Y (400 Hz) — as colored noise shaped to typical drilling
PSDs, a weak order-1 line, and slow trends. Two of the five variants carry
mud-pump combs (SPM 60 / 110) on TORQUE_SURF and WOB, so the matcher's
false-positive immunity is tested against comb structure on a
stick-slip-bound channel (gate 2).

Pump comb note (v1.3 erratum, fold into v1.3.1): A11's "triplex fundamentals
3.0 / 5.5 Hz" cannot be emitted literally on a 10 Hz channel — 5.5 Hz exceeds
both Nyquist (5 Hz) and the A7 cap (4.5 Hz). Implemented physically instead:
a stroke-rate comb at n × SPM/60 Hz capped at 4.5 Hz, with the 3×-piston
harmonic emphasized (SPM 60 → lines at 1, 2, 3, 4 Hz, strongest at 3.0;
SPM 110 → lines at 1.83, 3.67 Hz).
"""

from __future__ import annotations

from collections.abc import Iterator

import numpy as np

from .common import (
    Channel,
    SynthEpisode,
    bandlimited_pink_noise,
    measured_rpm_channel,
    rpm_profile,
    shaft_phase,
)

DURATION_S = 120.0  # A11
TORQUE_MEAN_KNM = 12.0
WOB_MEAN_KN = 80.0
A7_CAP_10HZ = 4.5

VARIANTS = ("quiet", "pump60", "pump110", "rough", "dither")


def sweep() -> Iterator[dict]:
    """The 5 A11 normal variants."""
    for variant in VARIANTS:
        yield {"variant": variant}


def _pump_comb(n: int, fs: float, spm: float, rng: np.random.Generator) -> np.ndarray:
    """Stroke-rate comb at k × SPM/60 Hz up to the A7 cap; 3×-piston line boosted."""
    t = np.arange(n) / fs
    f_stroke = spm / 60.0
    comb = np.zeros(n)
    k = 1
    while k * f_stroke <= A7_CAP_10HZ:
        amp = 0.35 if k == 3 else 0.15 / k
        comb += amp * np.sin(2.0 * np.pi * k * f_stroke * t + rng.uniform(0, 2 * np.pi))
        k += 1
    return comb


def generate(variant: str = "quiet", duration_s: float = DURATION_S, seed: int = 0) -> SynthEpisode:
    """Synthesize one normal-drilling episode; deterministic for a given seed."""
    if variant not in VARIANTS:
        raise ValueError(f"unknown normal variant: {variant}")
    # NB: not Python's hash() — that is per-process randomized and would break
    # A20's byte-identical determinism guarantee.
    rng = np.random.default_rng(seed + 100 * VARIANTS.index(variant))
    rough = 2.0 if variant == "rough" else 1.0
    rpm_kind = "dither" if variant == "dither" else "const"

    n10 = int(round(duration_s * 10.0))
    t10 = np.arange(n10) / 10.0
    trend = 1.0 + 0.1 * np.sin(2.0 * np.pi * t10 / duration_s)  # slow mean drift

    torque = TORQUE_MEAN_KNM * trend + 0.4 * rough * bandlimited_pink_noise(n10, 10.0, A7_CAP_10HZ, rng)
    wob = WOB_MEAN_KN * trend + 2.0 * rough * bandlimited_pink_noise(n10, 10.0, A7_CAP_10HZ, rng)
    if variant in ("pump60", "pump110"):
        spm = 60.0 if variant == "pump60" else 110.0
        torque = torque + _pump_comb(n10, 10.0, spm, rng)
        wob = wob + 4.0 * _pump_comb(n10, 10.0, spm, rng)

    # High-rate channels: weak order-1 line + noise, all A7-band-limited.
    rpm400 = rpm_profile(rpm_kind, duration_s, 400.0)
    theta400 = shaft_phase(rpm400, 400.0)
    n400 = len(theta400)
    acc_lat_x = 0.02 * np.sin(theta400) + 0.02 * rough * bandlimited_pink_noise(n400, 400.0, 170.0, rng)
    acc_lat_y = 0.02 * np.cos(theta400) + 0.02 * rough * bandlimited_pink_noise(n400, 400.0, 170.0, rng)
    n100 = int(round(duration_s * 100.0))
    acc_ax = 0.02 * rough * bandlimited_pink_noise(n100, 100.0, 42.0, rng)

    return SynthEpisode(
        slug=f"normal/{variant}",
        dysfunction_class="NORMAL_DRILLING",
        duration_s=duration_s,
        channels={
            "TORQUE_SURF": Channel(10.0, torque),
            "RPM_SURF": measured_rpm_channel(rpm400, 400.0, rng),
            "WOB": Channel(10.0, wob),
            "ACC_AX": Channel(100.0, acc_ax),
            "ACC_LAT_X": Channel(400.0, acc_lat_x),
            "ACC_LAT_Y": Channel(400.0, acc_lat_y),
        },
        params={"variant": variant, "seed": seed},
    )
