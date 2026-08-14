"""Core datatypes and the normative STFT profile registry (spec v1.3 §6/A1).

Every hashed profile must satisfy the window invariant
``frames_per_window(p) >= p.t_max + 3`` — asserted in tests/test_profiles.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Profile:
    """One STFT parameterization.

    ``rate`` is samples/second for time-domain profiles and samples/revolution
    for the order domain. ``window_w`` is the query-window length in seconds
    (time domain) or revolutions (order domain); None means the profile is
    display-only and never scheduled for matching. ``t_max`` is the per-profile
    anchor→target pairing limit in frames (spec A1); None means not hashed.

    >>> PROFILES["LOW"].delta_f
    0.0390625
    >>> frames_per_window(PROFILES["LOW"])
    15
    """

    name: str
    domain: str  # 'time' | 'order'
    rate: float
    n: int
    hop: int
    window_w: float | None
    eval_cadence: float
    t_max: int | None
    hashed: bool
    # Peak-picking neighborhood (Δm frames, Δk bins) — E4: Wang's (3, 3)
    # suits transient content; a stationary comb needs frequency-axis-only
    # picking ((0, 1)) or the ±Δm-frame local-max test thins each line to one
    # peak per 2Δm+1 frames and the ±Δk window lets a strong line's skirt
    # suppress its own sidebands.
    peak_neighborhood: tuple[int, int] = (3, 3)
    # E8: fraction of a window's frames a bin (±1) must recur in to carry
    # landmarks — stationary-content persistence gate; 0.0 disables.
    persistence_frac: float = 0.25

    @property
    def delta_f(self) -> float:
        """Bin width: Hz for time domain, orders for order domain."""
        return self.rate / self.n

    @property
    def frame_span(self) -> float:
        """Frame length in seconds (time) or revolutions (order)."""
        return self.n / self.rate

    @property
    def n_bins(self) -> int:
        """Number of rfft bins (N/2 + 1)."""
        return self.n // 2 + 1


PROFILES: dict[str, Profile] = {
    # (1,1) neighborhood: the stick-slip comb is stationary in time exactly
    # like ORDER-domain lines — a wide time-neighborhood makes a line compete
    # with its own noise-jittered self across frames and thins it ~4x under
    # in-band noise (E4b rationale, applied to LOW; 2026-08-11 bench forensics).
    # persistence 0.0 on LOW/LOW_DEEP: their in-band noise mode is fully
    # rejected by the E7 prominence gate (measured 0/48 spurious), and at low
    # SNR genuine comb lines recur in only ~20-30% of frames — persistence
    # would cost detection without buying rejection. ORDER keeps 0.25: its
    # flicker noise passes prominence but fails persistence (E8).
    "LOW": Profile("LOW", "time", 10.0, 256, 64, 120.0, 6.4, 12, True,
                   peak_neighborhood=(1, 1), persistence_frac=0.0),
    "LOW_DEEP": Profile("LOW_DEEP", "time", 10.0, 512, 128, 240.0, 12.8, 12, True,
                        peak_neighborhood=(1, 1), persistence_frac=0.0),
    "MID": Profile("MID", "time", 100.0, 512, 128, 30.0, 1.28, None, False),
    "HIGH": Profile("HIGH", "time", 400.0, 1024, 256, 10.0, 1.0, None, False),
    "ORDER": Profile("ORDER", "order", 64.0, 256, 64, 16.0, 1.0, 10, True,
                     peak_neighborhood=(0, 1)),
    "LOW_DECIM": Profile("LOW_DECIM", "time", 1.0, 256, 64, None, 64.0, None, False),
}


def frames_per_window(profile: Profile) -> int:
    """Complete STFT frames inside one query window.

    >>> [frames_per_window(PROFILES[p]) for p in ("LOW", "LOW_DEEP", "ORDER")]
    [15, 15, 13]
    """
    if profile.window_w is None:
        raise ValueError(f"profile {profile.name} has no query window (display-only)")
    n_samples = int(round(profile.window_w * profile.rate))
    if n_samples < profile.n:
        return 0
    return (n_samples - profile.n) // profile.hop + 1


@dataclass(frozen=True)
class Peak:
    """One constellation landmark: STFT frame index, bin index, log-magnitude (dB)."""

    m: int
    k: int
    mag_db: float


@dataclass(frozen=True)
class MatchResult:
    """Per-episode outcome of one matcher evaluation (spec §10/A3, E4).

    Two statistics, two jobs (erratum E4):

    - **Offset statistic** (``score``/``p_corr``/``alert``): the Shazam
      diagonal-alignment spike. Discriminative for time-EVOLVING content and
      same-instance replay; structurally flat for steady-state signatures
      matched across realizations (every hash type recurs at every library
      frame, so matches spread uniformly over offsets).
    - **Geometry statistic** (``distinct_matched``/``p_geom_corr``/
      ``geom_alert``): the number of distinct hash TYPES shared with the
      episode, against a Poisson collision null — the cross-realization test
      of spectral-geometry identity (populated only when the caller supplies
      the effective hash space and episode type counts).

    ``confidence`` is 1 − min(p_corr, p_geom_corr) clamped to [0, 1] — the
    only confidence statistic displayed anywhere (A3.4). The K=2 debounce is
    applied by the streaming layer (M4), not here.
    """

    episode_id: str
    score: int
    delta_star: int  # winning offset bin index (units: bin_width frames)
    matched_pairs: int
    lam: float
    p_corr: float
    confidence: float
    alert: bool
    distinct_matched: int = 0
    lam_geom: float = 0.0
    p_geom_corr: float | None = None
    geom_alert: bool = False
    histogram: dict[int, int] = field(repr=False, default_factory=dict)
