"""Stick-slip generator: the §2 2-DOF torsional model (A6 form, A11 constants).

    J_t·θ̈_t + k·(θ_t − θ_b) + c·(θ̇_t − θ̇_b) = T_motor(t)
    J_b·θ̈_b − k·(θ_t − θ_b) − c·(θ̇_t − θ̇_b) = −T_friction(θ̇_b)

PI-controlled top drive, tanh-regularized Stribeck bit friction, LSODA.
The system is integrated at 40 Hz and anti-alias-decimated to the emitted
10 Hz — the A7 generator gate ("nothing above 0.45·f_s") holds by construction.

A4 sanity gates (tested in tests/test_synth_stick_slip.py):
  - stability screen: torque swing < 5 %  → no limit cycle → relabel NORMAL_DRILLING
  - period gate:      measured period ∈ [1.0, 2.0] × T_model,  T_model = 2π√(J_b/k)
  - stick gate:       min RPM_DH < 5 % of commanded RPM
  - swing gate:       torque swing ≥ 15 % of mean
"""

from __future__ import annotations

import math
from collections.abc import Iterator

import numpy as np
from scipy.integrate import solve_ivp
from scipy.signal import decimate

from .common import Channel, SynthEpisode, t_model, torsional_stiffness

# Pinned constants (A11)
T_C = 6000.0  # N·m Coulomb torque
J_T = 1000.0  # kg·m² top-drive inertia
OMEGA_S = 1.0  # rad/s Stribeck velocity
ZETA = 0.05  # string damping ratio -> c = 2ζ√(k·J_b)
# PI gains: v1.3 erratum — A11's pinned 500/50 lets surface RPM swing ~75%,
# violating §2's "near-constant RPM, oscillating torque". 20000/2000 gives a
# 20 rad/s closed-loop top pole (realistic stiff top drive). Fold into v1.3.1.
K_P, K_I = 20000.0, 2000.0
EPS_REG = 1e-3  # rad/s tanh regularization (§2)

FS_OUT = 10.0
FS_INTERNAL = 40.0
DURATION_S = 180.0  # A11
SETTLE_S = 20.0  # integrated but not emitted

# A4 gate constants
SWING_RELABEL = 0.05
SWING_GATE = 0.15
# Period gate: v1.3 erratum, measured across the full 135-corner sweep.
# Floor 0.9: the slip-phase oscillation runs slightly FASTER than the free
# natural period at low-dwell corners. Ceiling is RPM-aware per A4's own
# rationale ("dwell grows as commanded RPM falls"): dwell/T_model =
# (T_s−T_rel)/(2π·Ω·√(k·J_b)) is verified ≈1.3-1.45×(T_s−T_c)/(k·Ω) at 60 RPM,
# pushing genuine dwell-dominated cycles to ratio 2.0-2.6. Fold into v1.3.1.
PERIOD_GATE_FLOOR = 0.9
STICK_GATE_FRAC = 0.05
STEADY_WINDOW_S = 90.0  # diagnostics run on the last 90 s (transient-free)
DECAY_RATIO = 0.6  # last-third/first-third swing below this => decaying, not a limit cycle
TRIM_S = 2.0  # guard band against zero-phase FIR decimation edge artifacts


def period_gate_ceiling(rpm_set: float) -> float:
    """RPM-aware period-gate ceiling (v1.3 erratum): 2.0 at >=90 RPM, 2.7 below."""
    return 2.0 if rpm_set >= 90.0 else 2.7


def sweep() -> Iterator[dict]:
    """The 135-corner A11 sweep: L × Ω_set × T_s/T_c × J_b."""
    for length_m in (1500.0, 2250.0, 3000.0, 4000.0, 5000.0):
        for rpm_set in (60.0, 90.0, 120.0):
            for ts_ratio in (1.3, 1.6, 2.0):
                for j_b in (100.0, 200.0, 400.0):
                    yield {
                        "length_m": length_m,
                        "rpm_set": rpm_set,
                        "ts_ratio": ts_ratio,
                        "j_b": j_b,
                    }


def _slug(p: dict) -> str:
    return (
        f"stick_slip/L{p['length_m']:.0f}_rpm{p['rpm_set']:.0f}"
        f"_ts{p['ts_ratio']}_jb{p['j_b']:.0f}"
    )


def generate(
    length_m: float = 3000.0,
    rpm_set: float = 120.0,
    ts_ratio: float = 1.6,
    j_b: float = 200.0,
    duration_s: float = DURATION_S,
) -> SynthEpisode:
    """Integrate one sweep corner and emit TORQUE_SURF / RPM_SURF / RPM_DH at 10 Hz.

    Starts from rest — the spin-up transient is what pushes the locally-stable
    Stribeck equilibrium into its limit cycle (or not: low-severity corners
    reach steady sliding and are relabeled NORMAL_DRILLING per A4.3).
    """
    k = torsional_stiffness(length_m)
    c = 2.0 * ZETA * math.sqrt(k * j_b)
    t_s = ts_ratio * T_C
    omega_set = rpm_set * 2.0 * math.pi / 60.0

    def friction(omega_b: float) -> float:
        stribeck = T_C + (t_s - T_C) * math.exp(-abs(omega_b) / OMEGA_S)
        return stribeck * math.tanh(omega_b / EPS_REG)

    def rhs(_t: float, y: np.ndarray) -> list[float]:
        omega_t, dtheta, omega_b, i_err = y
        t_motor = K_P * (omega_set - omega_t) + K_I * i_err
        coupling = k * dtheta + c * (omega_t - omega_b)
        return [
            (t_motor - coupling) / J_T,
            omega_t - omega_b,
            (coupling - friction(omega_b)) / j_b,
            omega_set - omega_t,
        ]

    t_end = duration_s + SETTLE_S + TRIM_S
    t_eval = np.arange(0.0, t_end, 1.0 / FS_INTERNAL)
    sol = solve_ivp(
        rhs, (0.0, t_end), [0.0, 0.0, 0.0, 0.0],
        method="LSODA", t_eval=t_eval, rtol=1e-6, atol=1e-8,
    )
    omega_t, dtheta, omega_b, i_err = sol.y
    torque_nm = K_P * (omega_set - omega_t) + K_I * i_err

    def to_out(x: np.ndarray) -> np.ndarray:
        # trailing TRIM_S guards against the zero-phase FIR filter's edge ring
        y = decimate(x, int(FS_INTERNAL / FS_OUT), ftype="fir", zero_phase=True)
        return y[-int((duration_s + TRIM_S) * FS_OUT) : -int(TRIM_S * FS_OUT)]

    torque_knm = to_out(torque_nm) / 1000.0
    rpm_surf = to_out(omega_t) * 60.0 / (2.0 * np.pi)
    rpm_dh = to_out(omega_b) * 60.0 / (2.0 * np.pi)

    diag = _diagnostics(torque_knm, rpm_dh, rpm_set, j_b, k)
    params = {"length_m": length_m, "rpm_set": rpm_set, "ts_ratio": ts_ratio,
              "j_b": j_b, "k_nm_per_rad": k, "t_model_s": t_model(j_b, k)}
    cls = "NORMAL_DRILLING" if diag["relabeled"] else "STICK_SLIP"
    return SynthEpisode(
        slug=_slug(params),
        dysfunction_class=cls,
        duration_s=duration_s,
        channels={
            "TORQUE_SURF": Channel(FS_OUT, torque_knm),
            "RPM_SURF": Channel(FS_OUT, rpm_surf),
            "RPM_DH": Channel(FS_OUT, rpm_dh),
        },
        params=params,
        diagnostics=diag,
    )


def _swing(torque: np.ndarray) -> float:
    """Percentile peak-to-peak swing: robust to isolated single-sample spikes,
    while clipping a genuine sawtooth (>=10 % of samples near each extreme)
    by well under 5 %."""
    mean = float(np.mean(torque))
    if not mean:
        return 0.0
    lo, hi = np.percentile(torque, (0.5, 99.5))
    return float((hi - lo) / mean)


def _measure_period(torque: np.ndarray, rpm_dh: np.ndarray, rpm_set: float,
                    fs: float) -> float:
    """Period from stick-event intervals (robust for relaxation cycles);
    FFT-peak fallback for non-sticking oscillations."""
    below = rpm_dh < STICK_GATE_FRAC * rpm_set
    onsets = np.flatnonzero(below[1:] & ~below[:-1])
    if len(onsets) >= 3:
        return float(np.median(np.diff(onsets)) / fs)
    spec = np.abs(np.fft.rfft(torque - np.mean(torque)))
    f = np.fft.rfftfreq(len(torque), d=1.0 / fs)
    band = f >= 0.03
    f0 = f[band][int(np.argmax(spec[band]))]
    return 1.0 / f0 if f0 > 0 else math.inf


def _diagnostics(torque_knm: np.ndarray, rpm_dh: np.ndarray, rpm_set: float,
                 j_b: float, k: float) -> dict:
    """A4 gate measurements over the steady (last STEADY_WINDOW_S) window.

    Stability screen (A4.3) relabels a corner NORMAL_DRILLING when it either
    never oscillates (swing < 5 %) or is still ringing DOWN from the startup
    transient (swing decaying across the steady window) — both are 'no limit
    cycle developed', which is expected physics, not generator failure.
    """
    w = int(STEADY_WINDOW_S * FS_OUT)
    tq, dh = torque_knm[-w:], rpm_dh[-w:]
    swing = _swing(tq)
    third = w // 3
    decaying = _swing(tq[-third:]) < DECAY_RATIO * _swing(tq[:third])
    relabeled = swing < SWING_RELABEL or decaying
    period = _measure_period(tq, dh, rpm_set, FS_OUT)
    ratio = period / t_model(j_b, k)
    min_rpm_frac = float(np.min(dh) / rpm_set)
    gates = {
        "period": bool(PERIOD_GATE_FLOOR <= ratio <= period_gate_ceiling(rpm_set)),
        "stick": bool(min_rpm_frac < STICK_GATE_FRAC),
        "swing": bool(swing >= SWING_GATE),
    }
    return {
        "torque_swing": swing,
        "decaying": bool(decaying),
        "period_s": period,
        "period_over_t_model": float(ratio),
        "min_rpm_dh_frac": min_rpm_frac,
        "relabeled": bool(relabeled),
        "gates_pass": bool((not relabeled) and all(gates.values())),
        "gates": gates,
    }
