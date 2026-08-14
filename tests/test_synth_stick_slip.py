"""M1 gates for the stick-slip generator (spec §12.1 under A4, A17).

Full-sweep conformance (all 135 corners) runs in the library build, not here;
these tests integrate representative corners so the suite stays fast.
"""

import numpy as np
import pytest

from synth.common import power_fraction_above, t_model, torsional_stiffness
from synth.stick_slip import (
    PERIOD_GATE_FLOOR,
    generate,
    period_gate_ceiling,
    sweep,
)

# One developed corner, reused across tests (module-scoped: ~0.15 s to make).
@pytest.fixture(scope="module")
def developed():
    return generate(3000.0, 120.0, 2.0, 200.0)


def test_sweep_cardinality():
    assert len(list(sweep())) == 135  # 5 L × 3 RPM × 3 ratio × 3 J_b (A11)


def test_developed_corner_passes_all_gates(developed):
    d = developed.diagnostics
    assert developed.dysfunction_class == "STICK_SLIP"
    assert not d["relabeled"]
    assert d["gates_pass"], d
    assert d["torque_swing"] >= 0.15  # swing gate
    assert d["min_rpm_dh_frac"] < 0.05  # stick gate
    assert PERIOD_GATE_FLOOR <= d["period_over_t_model"] <= period_gate_ceiling(120.0)


def test_low_severity_corner_relabels_normal():
    # A4.3 stability screen: T_s/T_c = 1.3 at 120 RPM settles to steady sliding.
    ep = generate(3000.0, 120.0, 1.3, 400.0)
    assert ep.dysfunction_class == "NORMAL_DRILLING"
    assert ep.diagnostics["relabeled"]
    assert not ep.diagnostics["gates_pass"]


def test_downhole_overspeed_is_physical(developed):
    # Field lore (§2): slip-phase downhole RPM reaches 2–4× surface RPM.
    rpm_dh = developed.channels["RPM_DH"].samples
    assert 1.5 * 120.0 < rpm_dh.max() < 5.0 * 120.0


def test_comb_spacing_equals_f0_no_parity_assertion(developed):
    # A22.4: assert harmonic comb SPACING = f0 — never an odd/even pattern.
    tq = developed.channels["TORQUE_SURF"].samples
    d = developed.diagnostics
    f0 = 1.0 / d["period_s"]
    spec = np.abs(np.fft.rfft(tq - tq.mean()))
    f = np.fft.rfftfreq(len(tq), 0.1)

    def line_power(freq):
        band = (f > freq - 0.02) & (f < freq + 0.02)
        return spec[band].max() if band.any() else 0.0

    floor = np.median(spec[f > 0.03])
    present = [n for n in (1, 2, 3) if line_power(n * f0) > 5.0 * floor]
    assert 1 in present and 2 in present  # comb at n·f0 (2f0 genuinely present)


def test_a7_generator_gate_no_content_above_045_fs(developed):
    for name, ch in developed.channels.items():
        frac = power_fraction_above(ch.samples, ch.fs, 0.45 * ch.fs)
        assert frac < 0.005, f"{name}: {frac:.4f} of power above 0.45·fs"


def test_surface_rpm_near_constant(developed):
    # §2: stiff PI top drive → near-constant surface RPM, oscillating torque.
    rpm_surf = developed.channels["RPM_SURF"].samples
    assert (rpm_surf.max() - rpm_surf.min()) / 120.0 < 0.15


def test_metadata_and_channels(developed):
    assert developed.slug == "stick_slip/L3000_rpm120_ts2.0_jb200"
    assert developed.duration_s == 180.0
    for name in ("TORQUE_SURF", "RPM_SURF", "RPM_DH"):
        ch = developed.channels[name]
        assert ch.fs == 10.0
        assert len(ch.samples) == 1800
    k = torsional_stiffness(3000.0)
    assert developed.params["t_model_s"] == pytest.approx(t_model(200.0, k))


def test_deterministic():
    a = generate(2250.0, 90.0, 1.6, 100.0)
    b = generate(2250.0, 90.0, 1.6, 100.0)
    assert np.array_equal(
        a.channels["TORQUE_SURF"].samples, b.channels["TORQUE_SURF"].samples
    )
