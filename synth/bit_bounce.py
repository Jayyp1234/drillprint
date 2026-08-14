"""Bit-bounce generator: signal-level synthesis at 100 Hz (spec §12.3, A9/A10/A11).

ACC_AX carries the real order lines (3, 6, 9 — the tri-lobe pattern and its
harmonics) plus a lift-off impact train (rings 30–40 Hz, under the A7 cap of
0.45·f_s = 45 Hz) and band-limited noise. The bounce ramp is 80→130 RPM (A11),
keeping order 9 ≤ 19.5 Hz inside the 1–20 Hz display band.

WOB is a 10 Hz channel and therefore CANNOT carry the 6 Hz order-3 line at
120 RPM (0.45·f_s = 4.5 Hz — the reason A9 demotes WOB to display-only): it
carries the mean load plus the slow lift-off severity envelope, which is what
a band-limited 10 Hz sensor genuinely reports. HOOKLOAD = buoyed string
weight − WOB (A10).

Emits measured RPM_SURF at 10 Hz (A16) — the ORDER-domain path needs it for
bounce exactly as for whirl.
"""

from __future__ import annotations

from collections.abc import Iterator

import numpy as np

from .common import (
    Channel,
    SynthEpisode,
    add_impact_rings,
    bandlimit,
    bandlimited_pink_noise,
    measured_rpm_channel,
    rpm_profile,
    shaft_phase,
)

FS = 100.0
FS_SLOW = 10.0
DURATION_S = 60.0  # A11
RAMP_TO = 130.0  # bounce ramp 80→130 (A11)
F_NOISE_CUT = 42.0  # under the A7 cap of 45 Hz
RING_TAU_S = 0.05
N_LOBES = 3  # tricone tri-lobe bottom pattern (§4)

WOB_MEAN_KN = 80.0
STRING_WEIGHT_KN = 1022.0  # buoyed string weight; HOOKLOAD = weight − WOB (§24-consistent)

A_ORDER3 = 0.15  # g per severity, harmonics at 1/2 and 1/4
A_IMPACT = 0.30
A_NOISE = 0.02
ENVELOPE_HZ = 0.2  # slow bounce-intensity envelope, visible on the 10 Hz WOB


def sweep() -> Iterator[dict]:
    """The 9-corner A11 sweep: severity × RPM profile."""
    for severity in (1, 2, 3):
        for profile in ("const", "ramp", "dither"):
            yield {"severity": severity, "profile": profile}


def generate(
    severity: int = 2,
    profile: str = "const",
    duration_s: float = DURATION_S,
    seed: int = 0,
) -> SynthEpisode:
    """Synthesize one bit-bounce episode; deterministic for a given seed (A20)."""
    rng = np.random.default_rng(seed + 7000 + 100 * severity)
    n = int(round(duration_s * FS))
    rpm = rpm_profile(profile, duration_s, FS, ramp_to=RAMP_TO)
    theta = shaft_phase(rpm, FS)
    t = np.arange(n) / FS

    a3 = A_ORDER3 * severity
    envelope = 1.0 + 0.4 * np.sin(2.0 * np.pi * ENVELOPE_HZ * t)
    acc_ax = (
        a3 * envelope * np.sin(N_LOBES * theta)
        + 0.5 * a3 * np.sin(2 * N_LOBES * theta)
        + 0.25 * a3 * np.sin(3 * N_LOBES * theta)
        + A_NOISE * bandlimited_pink_noise(n, FS, F_NOISE_CUT, rng)
    )

    # Lift-off impacts: one per lobe contact at high severity, thinned below.
    f_ring = float(rng.uniform(30.0, 40.0))
    contact_phases = np.arange(0.0, theta[-1], 2.0 * np.pi / N_LOBES)
    keep = rng.random(len(contact_phases)) < (0.2 * severity)
    impact_times = np.interp(contact_phases[keep], theta, t)
    add_impact_rings(acc_ax, FS, impact_times, f_ring, RING_TAU_S, A_IMPACT * severity)
    # sensor-chain anti-alias below the A7 cap (0.45·fs = 45 Hz)
    acc_ax = bandlimit(acc_ax, FS, F_NOISE_CUT)

    # 10 Hz channels: mean + slow envelope only (band-limited sensor honesty, A9).
    n_slow = int(round(duration_s * FS_SLOW))
    t_slow = np.arange(n_slow) / FS_SLOW
    dip = 5.0 * severity * (1.0 + np.sin(2.0 * np.pi * ENVELOPE_HZ * t_slow)) / 2.0
    wob = (
        WOB_MEAN_KN
        - dip
        + 1.0 * bandlimited_pink_noise(n_slow, FS_SLOW, 4.0, rng)
    )
    hookload = STRING_WEIGHT_KN - wob + 0.5 * bandlimited_pink_noise(
        n_slow, FS_SLOW, 4.0, rng
    )

    params = {"severity": severity, "profile": profile, "n_lobes": N_LOBES,
              "f_ring_hz": f_ring, "seed": seed}
    return SynthEpisode(
        slug=f"bit_bounce/sev{severity}_{profile}",
        dysfunction_class="BIT_BOUNCE",
        duration_s=duration_s,
        channels={
            "ACC_AX": Channel(FS, acc_ax),
            "WOB": Channel(FS_SLOW, wob),
            "HOOKLOAD": Channel(FS_SLOW, hookload),
            "RPM_SURF": measured_rpm_channel(rpm, FS, rng),
        },
        params=params,
        diagnostics={"n_impacts": int(keep.sum())},
    )
