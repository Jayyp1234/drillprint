"""Backward-whirl generator: signal-level synthesis at 400 Hz (spec §12.2, A7/A16).

Content on ACC_LAT_X/Y: order-1 imbalance line, backward-whirl line at order
(N_b+1) with slow AM, an impact train of M = N_b+1 decaying rings per
revolution (ring frequency drawn per-episode from 100–160 Hz — inside the A7
cap of 0.45·f_s = 180 Hz), and band-limited pink noise.

Emits RPM_SURF as a *measured* 10 Hz channel with ±1 RPM noise (A16): the
order-domain resampler (M2) may consume only this channel, never the
generator's internal profile.
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

FS = 400.0
DURATION_S = 60.0  # A11
RAMP_TO = 140.0  # whirl ramp 80→140 (A11; matches gate 3 / §34)
F_NOISE_CUT = 170.0  # noise band limit, under the A7 cap of 180 Hz
RING_TAU_S = 0.02

# amplitudes [g] per severity level
A_IMBALANCE = 0.10
A_WHIRL = 0.20
A_IMPACT = 0.50
A_NOISE = 0.03


def sweep() -> Iterator[dict]:
    """The 27-corner A11 sweep: N_b × severity × RPM profile."""
    for n_blades in (4, 5, 6):
        for severity in (1, 2, 3):
            for profile in ("const", "ramp", "dither"):
                yield {"n_blades": n_blades, "severity": severity, "profile": profile}


def generate(
    n_blades: int = 5,
    severity: int = 2,
    profile: str = "const",
    duration_s: float = DURATION_S,
    seed: int = 0,
) -> SynthEpisode:
    """Synthesize one whirl episode; deterministic for a given seed (A20)."""
    rng = np.random.default_rng(seed + 1000 * n_blades + 100 * severity)
    n = int(round(duration_s * FS))
    rpm = rpm_profile(profile, duration_s, FS, ramp_to=RAMP_TO)
    theta = shaft_phase(rpm, FS)
    t = np.arange(n) / FS

    m_lobes = n_blades + 1  # j = 1 (A11)
    am = 1.0 + 0.3 * np.sin(2.0 * np.pi * 0.2 * t)  # slow amplitude modulation
    a_w = A_WHIRL * severity

    # Sensor-frame whirl content (E4-enriched, physically derived): the
    # contact-force direction rotates at the whirl rate, so in the body frame
    # the (N_b+1) line is modulated at order 1 → sidebands at (N_b+1)±1; the
    # lobe-contact nonlinearity adds the 2(N_b+1) harmonic with its own ±1
    # sidebands. This stable comb {m−1, m, m+1, 2m−1, 2m, 2m+1} is the
    # class's fingerprint geometry. Backward sense is encoded in the X/Y
    # quadrature; imbalance rides at order 1.
    def comb(phase_fn):
        c = a_w * am * phase_fn(m_lobes * theta)
        c += 0.35 * a_w * am * (
            phase_fn((m_lobes - 1) * theta) + phase_fn((m_lobes + 1) * theta)
        )
        c += 0.4 * a_w * phase_fn(2 * m_lobes * theta)
        c += 0.15 * a_w * (
            phase_fn((2 * m_lobes - 1) * theta) + phase_fn((2 * m_lobes + 1) * theta)
        )
        return c

    acc_x = (
        A_IMBALANCE * np.sin(theta)
        + comb(np.sin)
        + A_NOISE * bandlimited_pink_noise(n, FS, F_NOISE_CUT, rng)
    )
    acc_y = (
        A_IMBALANCE * np.cos(theta)
        - comb(np.cos)
        + A_NOISE * bandlimited_pink_noise(n, FS, F_NOISE_CUT, rng)
    )

    # Impact train: M wall contacts per revolution at evenly spaced shaft phases.
    f_ring = float(rng.uniform(100.0, 160.0))
    contact_phases = np.arange(0.0, theta[-1], 2.0 * np.pi / m_lobes)
    impact_times = np.interp(contact_phases, theta, t)
    amp = A_IMPACT * severity
    add_impact_rings(acc_x, FS, impact_times, f_ring, RING_TAU_S, amp)
    add_impact_rings(acc_y, FS, impact_times, f_ring, RING_TAU_S, amp * 0.8)
    # sensor-chain anti-alias: ring onsets are broadband; band-limit the final
    # signal below the A7 cap (0.45·fs = 180 Hz), as a real ADC front-end does
    acc_x = bandlimit(acc_x, FS, F_NOISE_CUT)
    acc_y = bandlimit(acc_y, FS, F_NOISE_CUT)

    params = {"n_blades": n_blades, "severity": severity, "profile": profile,
              "m_lobes": m_lobes, "f_ring_hz": f_ring, "seed": seed}
    return SynthEpisode(
        slug=f"whirl/Nb{n_blades}_sev{severity}_{profile}",
        dysfunction_class="WHIRL_BACKWARD",
        duration_s=duration_s,
        channels={
            "ACC_LAT_X": Channel(FS, acc_x),
            "ACC_LAT_Y": Channel(FS, acc_y),
            "RPM_SURF": measured_rpm_channel(rpm, FS, rng),
        },
        params=params,
        diagnostics={"n_impacts": len(impact_times)},
    )
