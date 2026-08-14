"""Windowing and STFT (spec §6, determinism pins A23).

Hann is the periodic form (COLA-exact at hop = N/4 and N/2); only complete
frames are produced — no padding, so library and query frame grids agree.
"""

from __future__ import annotations

import numpy as np

from .types import Profile

LOG_EPS = 1e-12  # applied after per-channel normalization (A23)


def hann_periodic(n: int) -> np.ndarray:
    """Periodic Hann window w[i] = 0.5·(1 − cos(2πi/N)).

    >>> w = hann_periodic(8)
    >>> float(w[0]), float(round(w[4], 6))
    (0.0, 1.0)
    """
    return 0.5 * (1.0 - np.cos(2.0 * np.pi * np.arange(n) / n))


def frame_count(n_samples: int, profile: Profile) -> int:
    """Number of complete frames a signal of ``n_samples`` yields."""
    if n_samples < profile.n:
        return 0
    return (n_samples - profile.n) // profile.hop + 1


def stft_mag(x: np.ndarray, profile: Profile) -> np.ndarray:
    """Magnitude STFT, shape (n_frames, N/2+1). Complete frames only."""
    x = np.asarray(x, dtype=np.float64)
    n, hop = profile.n, profile.hop
    n_frames = frame_count(len(x), profile)
    if n_frames == 0:
        return np.empty((0, profile.n_bins))
    window = hann_periodic(n)
    idx = np.arange(n)[None, :] + hop * np.arange(n_frames)[:, None]
    return np.abs(np.fft.rfft(x[idx] * window, axis=1))


def log_magnitude(s: np.ndarray, eps: float = LOG_EPS) -> np.ndarray:
    """20·log10(|S| + ε) — finite everywhere, including on silence.

    >>> bool(np.isfinite(log_magnitude(np.zeros((2, 3)))).all())
    True
    """
    return 20.0 * np.log10(np.asarray(s, dtype=np.float64) + eps)
