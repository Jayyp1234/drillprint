"""M1 gates for the whirl generator (spec §12.2 under A7/A16/A17).

The order-domain half of the invariance story (sharp-after-resampling) is
M2's suite; here we assert the Hz-domain physics: the (N_b+1)-order line at
the right frequency under constant RPM, and its SMEARING under a ramp —
the time-domain half of the §9 contribution (A17).
"""

import numpy as np
import pytest

from synth.common import power_fraction_above
from synth.whirl import FS, generate, sweep


def _psd(x, fs):
    spec = np.abs(np.fft.rfft(x - x.mean())) ** 2
    return np.fft.rfftfreq(len(x), 1.0 / fs), spec


def _peak_freq(x, fs, f_lo, f_hi):
    f, spec = _psd(x, fs)
    band = (f >= f_lo) & (f <= f_hi)
    return f[band][int(np.argmax(spec[band]))]


def test_sweep_cardinality():
    assert len(list(sweep())) == 27  # 3 N_b × 3 severity × 3 profiles (A11)


def test_whirl_line_at_order_nb_plus_1_const_rpm():
    # N_b=5 at 120 RPM (2 Hz rotary): sensor-frame line at (5+1)·2 = 12 Hz (§3/A5).
    ep = generate(n_blades=5, severity=2, profile="const")
    got = _peak_freq(ep.channels["ACC_LAT_X"].samples, FS, 5.0, 33.0)
    assert got == pytest.approx(12.0, abs=0.25)


def test_imbalance_line_at_order_1():
    ep = generate(n_blades=5, severity=1, profile="const")
    got = _peak_freq(ep.channels["ACC_LAT_X"].samples, FS, 1.0, 3.0)
    assert got == pytest.approx(2.0, abs=0.15)


def test_ramp_smears_the_line_in_the_time_domain():
    # A17/M1: under an 80→140 ramp the whirl line migrates 8→14 Hz; spectral
    # concentration collapses vs the constant-RPM corner. This is the
    # time-domain half of the §9 contribution.
    const = generate(n_blades=5, severity=2, profile="const")
    ramp = generate(n_blades=5, severity=2, profile="ramp")

    def concentration(x):
        f, spec = _psd(x, FS)
        band = (f >= 5.0) & (f <= 35.0)
        return spec[band].max() / spec[band].sum()

    c_const = concentration(const.channels["ACC_LAT_X"].samples)
    c_ramp = concentration(ramp.channels["ACC_LAT_X"].samples)
    assert c_const > 3.0 * c_ramp, (c_const, c_ramp)


def test_a7_gate_no_content_above_045_fs():
    for profile in ("const", "ramp"):
        ep = generate(n_blades=6, severity=3, profile=profile)
        for name in ("ACC_LAT_X", "ACC_LAT_Y"):
            ch = ep.channels[name]
            frac = power_fraction_above(ch.samples, ch.fs, 0.45 * ch.fs)
            assert frac < 0.005, f"{profile}/{name}: {frac:.4f}"


def test_ring_band_within_100_160(monkeypatch):
    for nb in (4, 5, 6):
        ep = generate(n_blades=nb, severity=3, profile="const")
        assert 100.0 <= ep.params["f_ring_hz"] <= 160.0


def test_measured_rpm_channel_present_and_noisy():
    # A16: RPM_SURF is a measured 10 Hz channel with ±1 RPM sensor noise —
    # the only rotation source the resampler may consume.
    ep = generate(n_blades=5, severity=2, profile="const")
    rpm = ep.channels["RPM_SURF"]
    assert rpm.fs == 10.0
    assert len(rpm.samples) == 600
    assert rpm.samples.mean() == pytest.approx(120.0, abs=0.5)
    assert 0.5 < rpm.samples.std() < 2.0  # noise present, sane scale


def test_impact_count_tracks_lobes_and_revs():
    ep = generate(n_blades=5, severity=2, profile="const")
    revs = 120.0 / 60.0 * 60.0  # 2 rev/s × 60 s
    expected = revs * 6  # M = N_b+1 contacts per revolution
    assert ep.diagnostics["n_impacts"] == pytest.approx(expected, rel=0.05)


def test_deterministic():
    a = generate(4, 1, "dither", seed=5)
    b = generate(4, 1, "dither", seed=5)
    assert np.array_equal(a.channels["ACC_LAT_X"].samples, b.channels["ACC_LAT_X"].samples)
    assert np.array_equal(a.channels["RPM_SURF"].samples, b.channels["RPM_SURF"].samples)
