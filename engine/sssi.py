"""Surface stick-slip severity index (SSSI) — spec §2 / A2 Tier-1 advisory.

SSSI = (T_max − T_min) / (2 · T_mean) over a window of torque band-filtered
around the predicted fundamental f₀. Tier-1 stick-slip advisory fires when
SSSI exceeds a calibrated threshold (≤ 2 advisories / data-hour on normal).
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfiltfilt


def sssi(
    torque: np.ndarray,
    fs: float,
    f0_hz: float,
    n_periods: float = 2.0,
    bandwidth_frac: float = 0.5,
) -> float:
    """Compute SSSI on the trailing ``n_periods`` of predicted periods.

    Returns 0.0 when the window is too short or mean torque is near zero.
    The band is [f0·(1−bandwidth_frac), f0·(1+bandwidth_frac)], clamped
    below Nyquist.

    >>> import numpy as np
    >>> t = np.linspace(0, 20, 201)
    >>> x = 10.0 + 3.0 * np.sin(2 * np.pi * 0.25 * t)
    >>> round(sssi(x, 10.0, 0.25), 2)
    0.3
    """
    torque = np.asarray(torque, dtype=np.float64)
    if f0_hz <= 0 or fs <= 0 or len(torque) < 8:
        return 0.0
    win_s = n_periods / f0_hz
    n = min(len(torque), max(8, int(round(win_s * fs))))
    x = torque[-n:]
    lo = max(f0_hz * (1.0 - bandwidth_frac), 0.01)
    hi = min(f0_hz * (1.0 + bandwidth_frac), 0.45 * fs)
    if hi <= lo:
        y = x - np.mean(x)
    else:
        sos = butter(2, [lo, hi], btype="band", fs=fs, output="sos")
        y = sosfiltfilt(sos, x)
    mean = float(np.mean(x))
    if abs(mean) < 1e-9:
        return 0.0
    return float((np.max(y) - np.min(y)) / (2.0 * abs(mean)))


def band_energy_rms(
    x: np.ndarray,
    fs: float,
    band_hz: tuple[float, float],
) -> float:
    """RMS of a zero-phase band-passed signal — whirl/bounce Tier-1 watcher."""
    x = np.asarray(x, dtype=np.float64)
    if len(x) < 8 or fs <= 0:
        return 0.0
    lo, hi = band_hz
    hi = min(hi, 0.45 * fs)
    lo = max(lo, 0.01)
    if hi <= lo:
        return float(np.sqrt(np.mean((x - np.mean(x)) ** 2)))
    sos = butter(2, [lo, hi], btype="band", fs=fs, output="sos")
    y = sosfiltfilt(sos, x)
    return float(np.sqrt(np.mean(y ** 2)))
