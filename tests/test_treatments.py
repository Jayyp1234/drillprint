"""Query-side treatment gates (spec §12.5 under the A11 clean-library policy)."""

import numpy as np
import pytest

from synth.treatments import add_noise_snr, apply_dropouts, apply_gain, decimate_to_1hz


@pytest.fixture()
def signal():
    t = np.arange(4000) / 100.0
    return np.sin(2.0 * np.pi * 6.0 * t)


def test_snr_hits_target(signal):
    rng = np.random.default_rng(1)
    for snr_db in (20.0, 10.0, 3.0, 0.0):
        noisy = add_noise_snr(signal, 100.0, snr_db, rng)
        measured = 10.0 * np.log10(np.var(signal) / np.var(noisy - signal))
        assert measured == pytest.approx(snr_db, abs=1.5)


def test_noise_respects_a7_band_limit(signal):
    rng = np.random.default_rng(2)
    noise = add_noise_snr(signal, 100.0, 0.0, rng) - signal
    spec = np.abs(np.fft.rfft(noise)) ** 2
    f = np.fft.rfftfreq(len(noise), 0.01)
    assert spec[f > 45.0].sum() / spec.sum() < 0.01


def test_gain_within_bounds(signal):
    rng = np.random.default_rng(3)
    for _ in range(20):
        y, g = apply_gain(signal, rng)
        assert 0.8 <= g <= 1.2
        assert np.array_equal(y, signal * g)


def test_dropouts_hold_last_value(signal):
    rng = np.random.default_rng(4)
    y, spans = apply_dropouts(signal, 100.0, rng)
    assert 1 <= len(spans) <= 3
    for start, stop in spans:
        assert 10 <= stop - start <= 50  # 100–500 ms at 100 Hz
        assert (y[start:stop] == y[start - 1]).all()
    # outside spans the signal is untouched
    mask = np.ones(len(y), bool)
    for start, stop in spans:
        mask[start:stop] = False
    assert np.array_equal(y[mask], signal[mask])


def test_decimate_to_1hz():
    t = np.arange(12000) / 100.0
    x = np.sin(2.0 * np.pi * 0.2 * t)  # 0.2 Hz — survives 1 Hz decimation
    y = decimate_to_1hz(x, 100.0)
    assert len(y) == 120
    # the slow line survives; content near the old band is gone
    spec = np.abs(np.fft.rfft(y - y.mean()))
    f = np.fft.rfftfreq(len(y), 1.0)
    assert f[int(np.argmax(spec))] == pytest.approx(0.2, abs=0.05)
