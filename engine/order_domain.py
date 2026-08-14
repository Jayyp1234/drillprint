"""Order-domain (angular) resampling — the §9 RPM-invariance core (A7/A9/A15).

Pipeline: Ω_min guard → anti-alias low-pass (cutoff clamped to the channel's
own Nyquist; skipped entirely when angular resampling is pure upsampling) →
shaft-phase integration φ(t) = ∫Ω dt → interpolation onto a uniform
samples-per-revolution grid. The result feeds the ORDER STFT profile, where
rotation-clocked content (whirl at order N_b+1, bounce at order 3) sits at
constant order regardless of RPM.

Alignment contract (A15): callers pass RPM already interpolated onto the
vibration channel's sample grid — `ingest/sessions.py` owns that alignment in
the streaming service (M4); `align_rpm` is the pure function it will use.
"""

from __future__ import annotations

import numpy as np

SAMPLES_PER_REV = 64
ORDER_NYQUIST = SAMPLES_PER_REV / 2.0  # 32 orders
OMEGA_MIN_RPM = 10.0  # below this a window is order-invalid (A15.4)
AA_FRACTION = 0.8  # anti-alias cutoff = 0.8 × order-Nyquist, in Hz (A7.3)
CHANNEL_NYQUIST_FRACTION = 0.45  # clamp: never ask for a cutoff the channel can't hold


class OrderDomainInvalid(ValueError):
    """Raised when a window cannot be order-resampled (e.g. RPM below Ω_min)."""


def align_rpm(rpm: np.ndarray, rpm_fs: float, n_out: int, out_fs: float) -> np.ndarray:
    """Interpolate an RPM series onto a vibration channel's sample grid.

    >>> import numpy as np
    >>> align_rpm(np.array([60.0, 120.0]), 1.0, 5, 4.0).round(1).tolist()
    [60.0, 75.0, 90.0, 105.0, 120.0]
    """
    t_rpm = np.arange(len(rpm)) / rpm_fs
    t_out = np.arange(n_out) / out_fs
    return np.interp(t_out, t_rpm, rpm)


def effective_order_bandwidth(fs: float, f_rot: float) -> float:
    """Highest order a channel can genuinely carry: min(32, 0.5·fs/f_rot) (A1).

    >>> effective_order_bandwidth(100.0, 140.0 / 60.0)  # bounce channel, 140 RPM
    21.428571428571427
    """
    return min(ORDER_NYQUIST, 0.5 * fs / f_rot)


def _lowpass(x: np.ndarray, fs: float, f_cut: float) -> np.ndarray:
    """Zero-phase FFT brick-wall low-pass (deterministic, A20)."""
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), d=1.0 / fs)
    spec[f > f_cut] = 0.0
    return np.fft.irfft(spec, n=len(x))


def resample_to_order_domain(
    x: np.ndarray,
    fs: float,
    rpm_aligned: np.ndarray,
    samples_per_rev: int = SAMPLES_PER_REV,
) -> np.ndarray:
    """Resample a time-domain signal to uniform samples-per-revolution.

    ``rpm_aligned`` must be sampled on x's own grid (see align_rpm). Returns
    the order-domain signal; its "sample rate" is samples_per_rev per
    revolution, so the ORDER STFT profile applies directly.

    Raises OrderDomainInvalid when min(RPM) < OMEGA_MIN_RPM — never divides
    through a near-zero rotation rate (A15.4).
    """
    x = np.asarray(x, dtype=np.float64)
    rpm_aligned = np.asarray(rpm_aligned, dtype=np.float64)
    if len(x) != len(rpm_aligned):
        raise ValueError("rpm_aligned must be on x's sample grid (see align_rpm)")
    if float(np.min(rpm_aligned)) < OMEGA_MIN_RPM:
        raise OrderDomainInvalid(
            f"min RPM {np.min(rpm_aligned):.1f} < Ω_min {OMEGA_MIN_RPM} — "
            "window is order-invalid"
        )

    f_rot = rpm_aligned / 60.0  # rev/s
    f_rot_min = float(np.min(f_rot))

    # A7.3: anti-alias before angular interpolation. Skip when the angular
    # rate never falls below the channel rate (pure upsampling — nothing to
    # anti-alias); otherwise cutoff = 0.8 × order-Nyquist in Hz, clamped to
    # the channel's own representable band (the rc2 fix: an unclamped cutoff
    # is unbuildable on a 100 Hz channel above ~117 RPM).
    if samples_per_rev * f_rot_min < fs:
        f_cut = min(
            AA_FRACTION * ORDER_NYQUIST * f_rot_min,
            CHANNEL_NYQUIST_FRACTION * fs,
        )
        x = _lowpass(x, fs, f_cut)

    # Shaft position in revolutions: monotonic since rpm >= Ω_min > 0.
    dt = 1.0 / fs
    revs = np.concatenate(([0.0], np.cumsum((f_rot[1:] + f_rot[:-1]) * 0.5 * dt)))
    t = np.arange(len(x)) * dt

    phi_grid = np.arange(0.0, revs[-1], 1.0 / samples_per_rev)
    t_of_phi = np.interp(phi_grid, revs, t)
    return np.interp(t_of_phi, t, x)
