"""Shared synthesis infrastructure: constants, RPM profiles, noise, episode type."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

# Drillstring constants (spec §2, A11)
G_STEEL = 79.6e9  # Pa
RHO_STEEL = 7850.0  # kg/m^3
D_OUTER = 0.127  # m (5" drillpipe)
D_INNER = 0.1086  # m
J_PIPE = (math.pi / 32.0) * (D_OUTER**4 - D_INNER**4)  # 1.1884e-5 m^4
C_T = math.sqrt(G_STEEL / RHO_STEEL)  # torsional wave speed ~3184 m/s


def torsional_stiffness(length_m: float) -> float:
    """k = G·J_p / L  [N·m/rad].

    >>> round(torsional_stiffness(3000.0), 1)
    315.3
    """
    return G_STEEL * J_PIPE / length_m


def t_model(j_b: float, k: float) -> float:
    """Natural period of the 2-DOF system the code integrates (A4): 2π√(J_b/k)."""
    return 2.0 * math.pi * math.sqrt(j_b / k)


@dataclass(frozen=True)
class Channel:
    """One emitted channel: sample rate and samples."""

    fs: float
    samples: np.ndarray


@dataclass
class SynthEpisode:
    """Generator output: channels + provenance (spec §12: signal dict, metadata)."""

    slug: str
    dysfunction_class: str
    duration_s: float
    channels: dict[str, Channel]
    params: dict = field(default_factory=dict)
    diagnostics: dict = field(default_factory=dict)


def rpm_profile(kind: str, duration_s: float, fs: float, ramp_to: float = 140.0) -> np.ndarray:
    """Pinned RPM profiles (A11): const=120, ramp 80→ramp_to, dither 120±10 @ 0.1 Hz."""
    t = np.arange(int(round(duration_s * fs))) / fs
    if kind == "const":
        return np.full_like(t, 120.0)
    if kind == "ramp":
        return 80.0 + (ramp_to - 80.0) * t / duration_s
    if kind == "dither":
        return 120.0 + 10.0 * np.sin(2.0 * np.pi * 0.1 * t)
    raise ValueError(f"unknown RPM profile: {kind}")


def shaft_phase(rpm: np.ndarray, fs: float) -> np.ndarray:
    """Cumulative shaft angle θ(t) [rad] from an RPM series (§9: φ = ∫Ω dt)."""
    omega = rpm * (2.0 * np.pi / 60.0)
    return np.concatenate(([0.0], np.cumsum((omega[1:] + omega[:-1]) * 0.5))) / fs


def bandlimited_pink_noise(n: int, fs: float, f_cut: float, rng: np.random.Generator) -> np.ndarray:
    """Unit-variance pink (1/f) noise with zero content above f_cut (A7 gate)."""
    spec = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, d=1.0 / fs)
    shape = np.zeros_like(f)
    nz = f > 0
    shape[nz] = 1.0 / np.sqrt(f[nz])
    shape[f > f_cut] = 0.0
    x = np.fft.irfft(spec * shape, n=n)
    sd = x.std()
    return x / sd if sd > 0 else x


def add_impact_rings(
    x: np.ndarray,
    fs: float,
    impact_times: np.ndarray,
    f_ring: float,
    tau_s: float,
    amp: float,
) -> None:
    """Add decaying-sinusoid rings in place at each impact time (spec §12.2/§12.3)."""
    n_ring = int(round(6.0 * tau_s * fs))
    t_ring = np.arange(n_ring) / fs
    ring = np.exp(-t_ring / tau_s) * np.sin(2.0 * np.pi * f_ring * t_ring)
    for t0 in impact_times:
        i = int(round(t0 * fs))
        if 0 <= i < len(x):
            seg = min(n_ring, len(x) - i)
            x[i : i + seg] += amp * ring[:seg]


def bandlimit(x: np.ndarray, fs: float, f_cut: float) -> np.ndarray:
    """Zero-phase brick-wall low-pass (FFT). The synthesis-chain anti-alias
    step: impact onsets are genuinely broadband, and a real accelerometer
    chain band-limits them before sampling — this is that filter (A7)."""
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), d=1.0 / fs)
    spec[f > f_cut] = 0.0
    return np.fft.irfft(spec, n=len(x))


def power_fraction_above(x: np.ndarray, fs: float, f_cut: float) -> float:
    """Fraction of total AC power above f_cut — the A7 generator-gate metric."""
    spec = np.abs(np.fft.rfft(x - np.mean(x))) ** 2
    f = np.fft.rfftfreq(len(x), d=1.0 / fs)
    total = spec[f > 0].sum()
    return float(spec[f > f_cut].sum() / total) if total > 0 else 0.0


def measured_rpm_channel(rpm: np.ndarray, fs_src: float, rng: np.random.Generator) -> Channel:
    """RPM_SURF as a *measured* 10 Hz channel with ±1 RPM sensor noise (A16).

    The sensor noise is band-limited to 0.44·fs — white noise to Nyquist would
    itself violate the A7 generator gate.
    """
    step = int(round(fs_src / 10.0))
    sampled = rpm[::step].copy() if step > 1 else rpm.copy()
    noise = bandlimited_pink_noise(len(sampled), 10.0, 4.4, rng)
    white = bandlimit(rng.standard_normal(len(sampled)), 10.0, 4.4)
    sd = white.std()
    white = white / sd if sd else white
    return Channel(10.0, sampled + 0.7 * noise + 0.7 * white)
