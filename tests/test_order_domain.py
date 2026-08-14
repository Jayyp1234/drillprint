"""M2 unit gates for the order-domain resampler (§9 under A7/A15)."""

import numpy as np
import pytest

from engine.order_domain import (
    OrderDomainInvalid,
    align_rpm,
    effective_order_bandwidth,
    resample_to_order_domain,
)
from engine.stft import stft_mag
from engine.types import PROFILES

ORDER = PROFILES["ORDER"]
FS = 400.0


def _rpm_series(kind, dur, fs):
    t = np.arange(int(dur * fs)) / fs
    if kind == "const":
        return np.full_like(t, 120.0)
    if kind == "ramp":
        return 80.0 + 60.0 * t / dur
    raise ValueError(kind)


def _order_signal(rpm, fs, order):
    f_rot = rpm / 60.0
    dt = 1.0 / fs
    revs = np.concatenate(([0.0], np.cumsum((f_rot[1:] + f_rot[:-1]) * 0.5 * dt)))
    return np.sin(2.0 * np.pi * order * revs)


def _dominant_order(od):
    s = stft_mag(od, ORDER).mean(axis=0)
    return np.argmax(s[1:]) + 1  # skip DC bin


def _concentration(od):
    s = stft_mag(od, ORDER).mean(axis=0)[1:]
    return s.max() / s.sum()


def test_constant_rpm_order6_lands_at_order_bin():
    rpm = _rpm_series("const", 30.0, FS)
    od = resample_to_order_domain(_order_signal(rpm, FS, 6.0), FS, rpm)
    # order 6 at Δorder = 0.25 → bin 24
    assert _dominant_order(od) == 24


def test_ramp_smeared_in_time_sharp_in_order():
    # THE §9 test: an order-6 line under an 80→140 ramp is smeared across
    # 8–14 Hz in the time domain, and collapses to one sharp constant-order
    # line after angular resampling.
    rpm = _rpm_series("ramp", 30.0, FS)
    x = _order_signal(rpm, FS, 6.0)
    od = resample_to_order_domain(x, FS, rpm)
    assert _dominant_order(od) == 24

    # sharpness: compare against the same line resampled from constant RPM
    rpm_c = _rpm_series("const", 30.0, FS)
    od_c = resample_to_order_domain(_order_signal(rpm_c, FS, 6.0), FS, rpm_c)
    assert _concentration(od) > 0.8 * _concentration(od_c)

    # ...and the time-domain STFT of the ramp signal is genuinely smeared
    HIGH = PROFILES["HIGH"]
    s_time = stft_mag(x, HIGH).mean(axis=0)[1:]
    time_conc = s_time.max() / s_time.sum()
    assert _concentration(od) > 3.0 * time_conc


def test_omega_min_guard():
    rpm = _rpm_series("const", 5.0, FS)
    rpm[100:200] = 5.0  # dips below Ω_min = 10
    with pytest.raises(OrderDomainInvalid):
        resample_to_order_domain(np.zeros(len(rpm)), FS, rpm)


def test_antialias_suppresses_fold_into_order_band():
    # A 150 Hz tone at 120 RPM is order 75 — beyond the order-Nyquist of 32.
    # Without the A7 filter it would fold to order |75 − 64| = 11, inside the
    # whirl hashing band; with it, the folded line must be gone.
    rpm = _rpm_series("const", 30.0, FS)
    t = np.arange(len(rpm)) / FS
    tone = np.sin(2.0 * np.pi * 150.0 * t)
    marker = _order_signal(rpm, FS, 6.0)  # in-band reference line
    od = resample_to_order_domain(marker + tone, FS, rpm)
    s = stft_mag(od, ORDER).mean(axis=0)
    assert s[44] < 0.02 * s[24]  # order 11 (bin 44) ≪ order 6 (bin 24)


def test_cutoff_clamped_on_slow_channel_no_crash():
    # rc2 blocking fix: at 130 RPM on a 100 Hz channel the unclamped cutoff
    # (55.5 Hz) exceeds the channel Nyquist (50 Hz); the clamp must make this
    # work, not crash — the bounce path depends on it.
    fs = 100.0
    rpm = np.full(int(30 * fs), 130.0)
    f_rot = rpm / 60.0
    t = np.arange(len(rpm)) / fs
    x = np.sin(2.0 * np.pi * 3.0 * f_rot[0] * t)  # order-3 line at const RPM
    od = resample_to_order_domain(x, fs, rpm)
    assert _dominant_order(od) == 12  # order 3 → bin 12


def test_pure_upsampling_branch_skips_filter():
    # 10 Hz channel: 64 samples/rev × 2 rev/s = 128 ≥ 10 → pure upsampling;
    # content passes through unfiltered.
    fs = 10.0
    rpm = np.full(int(60 * fs), 120.0)
    t = np.arange(len(rpm)) / fs
    x = np.sin(2.0 * np.pi * 0.3 * t)
    od = resample_to_order_domain(x, fs, rpm)
    assert len(od) > 0
    assert np.std(od) == pytest.approx(np.std(x), rel=0.1)


def test_effective_order_bandwidth_bounce_band_fits():
    # A1/A9: bounce hashing band (orders 2–10) must fit the 100 Hz channel's
    # effective order bandwidth at every spec RPM.
    for rpm in (80.0, 120.0, 130.0, 140.0):
        assert effective_order_bandwidth(100.0, rpm / 60.0) >= 10.0
    # and the 400 Hz whirl channel holds the full order-Nyquist
    assert effective_order_bandwidth(400.0, 140.0 / 60.0) == 32.0


def test_align_rpm_grid():
    rpm = np.array([100.0, 110.0, 120.0])  # 10 Hz series
    out = align_rpm(rpm, 10.0, 8, 40.0)
    assert len(out) == 8
    assert out[0] == 100.0
    assert out[4] == pytest.approx(110.0)


def test_deterministic():
    rng = np.random.default_rng(11)
    rpm = _rpm_series("ramp", 20.0, FS)
    x = rng.normal(size=len(rpm))
    a = resample_to_order_domain(x, FS, rpm)
    b = resample_to_order_domain(x.copy(), FS, rpm.copy())
    assert np.array_equal(a, b)
