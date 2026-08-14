"""M1 gates for bit-bounce and normal generators (spec §12.3/§12.4, A9/A10/A11)."""

import numpy as np
import pytest

from synth.common import power_fraction_above
from synth import bit_bounce, normal


def _psd(x, fs):
    spec = np.abs(np.fft.rfft(x - x.mean())) ** 2
    return np.fft.rfftfreq(len(x), 1.0 / fs), spec


def _line_snr(x, fs, freq, half=0.15):
    f, spec = _psd(x, fs)
    band = (f > freq - half) & (f < freq + half)
    floor = np.median(spec[f > 0.5])
    return spec[band].max() / floor


# ---------- bit bounce ----------

def test_bounce_sweep_cardinality():
    assert len(list(bit_bounce.sweep())) == 9  # 3 severity × 3 profiles (A11)


def test_order_3_6_9_lines_at_const_120rpm():
    # 120 RPM = 2 Hz rotary → order lines at 6, 12, 18 Hz on ACC_AX (§4/A9).
    ep = bit_bounce.generate(severity=2, profile="const")
    acc = ep.channels["ACC_AX"].samples
    for freq in (6.0, 12.0, 18.0):
        assert _line_snr(acc, 100.0, freq) > 20.0, freq


def test_bounce_ramp_caps_at_130rpm():
    # A11: bounce ramp is 80→130, keeping order 9 ≤ 19.5 Hz in the display band.
    ep = bit_bounce.generate(severity=2, profile="ramp")
    rpm = ep.channels["RPM_SURF"].samples
    assert rpm.max() < 134.0  # 130 + sensor noise headroom
    # at end of ramp (~130 RPM) the order-3 line sits near 6.5 Hz
    tail = ep.channels["ACC_AX"].samples[-1000:]  # last 10 s
    f, spec = _psd(tail, 100.0)
    band = (f >= 4.0) & (f <= 8.0)
    assert f[band][int(np.argmax(spec[band]))] == pytest.approx(6.4, abs=0.4)


def test_wob_is_band_limited_no_order3_line():
    # A9: 10 Hz WOB cannot carry the 6 Hz order-3 line (0.45·fs = 4.5 Hz);
    # it carries mean + slow envelope only — that is WHY it is display-only.
    ep = bit_bounce.generate(severity=3, profile="const")
    wob = ep.channels["WOB"]
    assert wob.fs == 10.0
    assert power_fraction_above(wob.samples, 10.0, 4.5) < 0.005
    assert _line_snr(wob.samples, 10.0, 0.2) > 5.0  # the slow lift-off envelope


def test_hookload_complements_wob():
    ep = bit_bounce.generate(severity=2, profile="const")
    wob = ep.channels["WOB"].samples
    hl = ep.channels["HOOKLOAD"].samples
    total = wob + hl
    assert np.abs(total - bit_bounce.STRING_WEIGHT_KN).mean() < 2.0


def test_bounce_a7_gate_all_channels():
    ep = bit_bounce.generate(severity=3, profile="const")
    for name, ch in ep.channels.items():
        frac = power_fraction_above(ch.samples, ch.fs, 0.45 * ch.fs)
        assert frac < 0.005, f"{name}: {frac:.4f}"


# ---------- normal ----------

def test_normal_variants_and_channel_set():
    assert len(list(normal.sweep())) == 5  # A11
    ep = normal.generate("quiet")
    # A10: the normal generator emits the FULL surface set.
    assert set(ep.channels) == {
        "TORQUE_SURF", "RPM_SURF", "WOB", "ACC_AX", "ACC_LAT_X", "ACC_LAT_Y",
    }
    assert ep.dysfunction_class == "NORMAL_DRILLING"
    assert ep.duration_s == 120.0


def test_pump60_comb_on_torque_strongest_at_3hz():
    # A10/A11: pump comb rides the stick-slip-bound channel; stroke comb at
    # n×1.0 Hz with the 3×-piston line emphasized.
    ep = normal.generate("pump60")
    tq = ep.channels["TORQUE_SURF"].samples
    snrs = {freq: _line_snr(tq, 10.0, freq, half=0.1) for freq in (1.0, 2.0, 3.0, 4.0)}
    assert all(s > 5.0 for s in snrs.values()), snrs  # comb present
    assert snrs[3.0] == max(snrs.values())  # 3× piston line dominates


def test_pump110_comb_capped_below_a7_limit():
    # v1.3 erratum: SPM 110 → lines at 1.83, 3.67 Hz only (5.5 Hz would breach
    # Nyquist/A7 on a 10 Hz channel).
    ep = normal.generate("pump110")
    tq = ep.channels["TORQUE_SURF"].samples
    assert _line_snr(tq, 10.0, 1.833, half=0.1) > 5.0
    assert _line_snr(tq, 10.0, 3.667, half=0.1) > 5.0
    assert power_fraction_above(tq, 10.0, 4.5) < 0.005


def test_normal_a7_gate_all_channels():
    for variant in ("quiet", "pump110", "rough"):
        ep = normal.generate(variant)
        for name, ch in ep.channels.items():
            frac = power_fraction_above(ch.samples, ch.fs, 0.45 * ch.fs)
            assert frac < 0.005, f"{variant}/{name}: {frac:.4f}"


def test_normal_deterministic_across_processes():
    a = normal.generate("pump60", seed=3)
    b = normal.generate("pump60", seed=3)
    assert np.array_equal(a.channels["TORQUE_SURF"].samples, b.channels["TORQUE_SURF"].samples)
