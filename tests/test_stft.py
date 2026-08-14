"""STFT gates (spec §21 M0: known sinusoid → correct bin; COLA; determinism)."""

import numpy as np
import pytest

from engine.stft import frame_count, hann_periodic, log_magnitude, stft_mag
from engine.types import PROFILES

LOW = PROFILES["LOW"]


def test_known_sinusoid_lands_in_correct_bin():
    # Bin-20 sinusoid of the LOW profile: f = 20 * fs / N = 0.78125 Hz.
    k_true = 20
    f = k_true * LOW.rate / LOW.n
    t = np.arange(int(120 * LOW.rate)) / LOW.rate
    x = np.sin(2 * np.pi * f * t)
    s = stft_mag(x, LOW)
    assert s.shape == (15, LOW.n_bins)
    assert (s.argmax(axis=1) == k_true).all()


def test_cola_periodic_hann():
    # Periodic Hann overlap-add: constant 2.0 at hop N/4, 1.0 at hop N/2.
    n = 256
    w = hann_periodic(n)
    for hop, expected in ((n // 4, 2.0), (n // 2, 1.0)):
        acc = np.zeros(n * 8)
        for start in range(0, len(acc) - n + 1, hop):
            acc[start : start + n] += w
        mid = acc[n : len(acc) - n]  # exclude ramp-up/down edges
        assert mid == pytest.approx(np.full_like(mid, expected), abs=1e-9)


def test_log_magnitude_finite_on_silence():
    assert np.isfinite(log_magnitude(np.zeros((3, 5)))).all()


def test_frame_count_complete_frames_only():
    assert frame_count(1200, LOW) == 15
    assert frame_count(LOW.n - 1, LOW) == 0
    assert frame_count(LOW.n, LOW) == 1
    assert frame_count(LOW.n + LOW.hop - 1, LOW) == 1
    assert frame_count(LOW.n + LOW.hop, LOW) == 2


def test_stft_deterministic():
    rng = np.random.default_rng(7)
    x = rng.normal(size=2000)
    assert np.array_equal(stft_mag(x, LOW), stft_mag(x.copy(), LOW))
