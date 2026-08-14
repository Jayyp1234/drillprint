"""Query-side signal treatments (spec §12.5 under the A11 noise policy).

The library is built from CLEAN episodes; these treatments are applied only to
benchmark/scenario query data — never to library episodes.
"""

from __future__ import annotations

import numpy as np

from .common import bandlimited_pink_noise


def add_noise_snr(x: np.ndarray, fs: float, snr_db: float,
                  rng: np.random.Generator, f_cut: float | None = None,
                  p_signal: float | None = None) -> np.ndarray:
    """Additive Gaussian + pink noise (50/50 power split) at a target SNR.

    ``f_cut`` band-limits the noise (defaults to 0.45·fs, the A7 cap).
    ``p_signal`` overrides the reference signal power (AC); the bench passes
    the dysfunction-span power so the noise floor is constant across a whole
    composite run rather than rescaling per segment.
    """
    f_cut = 0.45 * fs if f_cut is None else f_cut
    if p_signal is None:
        p_signal = float(np.var(x))
    p_noise = p_signal / (10.0 ** (snr_db / 10.0))
    white = rng.standard_normal(len(x))
    # band-limit the white component identically to the pink one
    spec = np.fft.rfft(white)
    f = np.fft.rfftfreq(len(x), d=1.0 / fs)
    spec[f > f_cut] = 0.0
    white = np.fft.irfft(spec, n=len(x))
    white /= white.std() if white.std() else 1.0
    pink = bandlimited_pink_noise(len(x), fs, f_cut, rng)
    noise = np.sqrt(p_noise / 2.0) * white + np.sqrt(p_noise / 2.0) * pink
    return x + noise


def apply_gain(x: np.ndarray, rng: np.random.Generator,
               max_frac: float = 0.2) -> tuple[np.ndarray, float]:
    """Random gain within ±max_frac (§12.5); returns (signal, gain used)."""
    gain = 1.0 + rng.uniform(-max_frac, max_frac)
    return x * gain, gain


def apply_dropouts(x: np.ndarray, fs: float, rng: np.random.Generator,
                   n_dropouts: int = 3,
                   dur_range_s: tuple[float, float] = (0.1, 0.5),
                   ) -> tuple[np.ndarray, list[tuple[int, int]]]:
    """Sensor dropouts (100–500 ms, §12.5): hold-last-value spans.

    Returns (signal, list of (start, stop) sample spans) — the span list is
    what ingestion's gap policy (A15) consumes when replaying treated data.
    """
    y = x.copy()
    spans: list[tuple[int, int]] = []
    for _ in range(n_dropouts):
        dur = int(rng.uniform(*dur_range_s) * fs)
        if dur < 1 or dur >= len(y) - 1:
            continue
        start = int(rng.integers(1, len(y) - dur))
        y[start : start + dur] = y[start - 1]
        spans.append((start, start + dur))
    return y, spans


def decimate_to_1hz(x: np.ndarray, fs: float) -> np.ndarray:
    """1 Hz decimated variant (§12.5) with anti-alias filtering — feeds the
    LOW-DECIM display path (A1), never hashing."""
    from scipy.signal import decimate

    q = int(round(fs))
    if q <= 1:
        return x.copy()
    # scipy caps single-stage decimation quality around q≈13; stage it.
    y = x
    while q > 10:
        y = decimate(y, 10, ftype="fir", zero_phase=True)
        q //= 10
    return decimate(y, q, ftype="fir", zero_phase=True) if q > 1 else y
