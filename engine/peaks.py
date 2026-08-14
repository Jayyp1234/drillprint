"""Constellation extraction (spec §7, determinism pins A23).

Pipeline: local-maximum test (maximum_filter, mode='constant', cval=-inf)
→ per-frame adaptive threshold median(frame) + β dB → density cap of the
P strongest per frame with the deterministic tie-break (higher mag, then
lower k). Constant plateaus (dropouts) are rejected by the median gate.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import maximum_filter, percentile_filter

from .types import Peak

BETA_DB = 8.0  # A23 default
NEIGHBORHOOD = (3, 3)  # (Δm, Δk): neighborhood half-widths
MAX_PER_FRAME = 5
# E7: local-prominence gate. A landmark must stand this far above the running
# median of its LOCAL spectral neighborhood — this whitens pink-noise tilt
# (whole-band medians under-reject low-bin noise maxima) and keeps noise
# bumps (~4-6 dB proud) out of the constellation while genuine comb/order
# lines (15-40 dB proud) pass. Wang's landmarks are locally dominant energy;
# this makes "locally" mean the spectrum, not just the frame.
PROMINENCE_DB = 10.0
PROMINENCE_HALF_WIDTH = 8  # bins each side for the local background median


def find_peaks(
    log_spec: np.ndarray,
    beta_db: float = BETA_DB,
    neighborhood: tuple[int, int] = NEIGHBORHOOD,
    max_per_frame: int = MAX_PER_FRAME,
    band: tuple[int, int] | None = None,
    prominence_db: float = PROMINENCE_DB,
    persistence_frac: float = 0.0,
) -> list[Peak]:
    """Extract the sparse constellation from a log-magnitude spectrogram.

    ``log_spec`` has shape (n_frames, n_bins). Returns peaks sorted by
    (frame, bin) — a stable, deterministic ordering.

    ``band`` = (k_lo, k_hi) restricts CANDIDATES to the class's hashing band
    (A9) before the density cap — out-of-band content must not crowd the
    per-frame peak budget (E4: without this, a class's own harmonic lines
    lose cap slots to out-of-band energy and the constellation destabilizes).
    The local-max test and the median threshold still run on the FULL
    spectrum: a narrow band dense with lines would otherwise put the median
    on the lines themselves and the gate would reject its own signal.
    """
    ls = np.asarray(log_spec, dtype=np.float64)
    if ls.size == 0:
        return []
    dm, dk = neighborhood
    footprint = (2 * dm + 1, 2 * dk + 1)
    local_max = ls >= maximum_filter(ls, size=footprint, mode="constant", cval=-np.inf)
    threshold = np.median(ls, axis=1, keepdims=True) + beta_db
    candidates = local_max & (ls >= threshold)
    if prominence_db > 0:
        # 25th percentile, not median: on a DENSE comb (stick-slip lines every
        # ~5 bins) the local median lands on the lines themselves and would
        # reject the comb wholesale; the between-line noise floor always owns
        # the low quantiles regardless of line density.
        local_bg = percentile_filter(
            ls, percentile=25, size=(1, 2 * PROMINENCE_HALF_WIDTH + 1),
            mode="nearest",
        )
        candidates &= ls >= local_bg + prominence_db
    if persistence_frac > 0 and ls.shape[0] >= 4:
        # E8 temporal persistence: every fingerprinted phenomenon is
        # stationary (or slowly AM) in its hashing domain — genuine lines
        # recur in ~50-100% of a window's frames while noise maxima flicker
        # at scattered bins (measured: genuine whirl 57/57 frames at 8 bins;
        # treated-normal spurious peaks <=6/56 at 32 bins). A bin (±1) must
        # recur in >= persistence_frac of frames to carry landmarks.
        near = candidates.copy()
        near[:, :-1] |= candidates[:, 1:]
        near[:, 1:] |= candidates[:, :-1]
        support = near.sum(axis=0)
        needed = max(2, int(np.ceil(persistence_frac * ls.shape[0])))
        candidates &= (support >= needed)[None, :]
    if band is not None:
        k_lo, k_hi = band
        mask = np.zeros(ls.shape[1], dtype=bool)
        mask[k_lo : k_hi + 1] = True
        candidates &= mask[None, :]

    out: list[Peak] = []
    for m in np.flatnonzero(candidates.any(axis=1)):
        ks = np.flatnonzero(candidates[m])
        # density cap: strongest first; ties broken by lower bin index (A23)
        order = sorted(ks, key=lambda k: (-ls[m, k], k))[:max_per_frame]
        out.extend(Peak(int(m), int(k), float(ls[m, k])) for k in order)
    out.sort(key=lambda p: (p.m, p.k))
    return out
