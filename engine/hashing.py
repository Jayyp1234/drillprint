"""Combinatorial hashing (spec §8, per-profile T_max per A1).

Hash layout: f1 (10 bits) | Δk signed (8 bits, |Δk| ≤ K_MAX=63) | Δt (6 bits,
1 ≤ Δt ≤ profile.t_max). Target selection is deterministic: candidates sorted
by (Δt, |Δk|, k), first FANOUT taken — so two runs over the same constellation
emit byte-identical hash streams (A20 determinism).
"""

from __future__ import annotations

from .types import Peak, Profile

F1_BITS, DK_BITS, DT_BITS = 10, 8, 6
K_MAX = 63
FANOUT = 8

_F1_MAX = (1 << F1_BITS) - 1  # 1023
_DT_MAX = (1 << DT_BITS) - 1  # 63


def pack_hash(f1: int, dk: int, dt: int) -> int:
    """Pack (anchor bin, signed bin delta, frame delta) into a 24-bit int.

    >>> pack_hash(10, 2, 1)
    163969
    >>> pack_hash(0, -1, 1) == (0 << 14) | (0xFF << 6) | 1
    True
    """
    if not 0 <= f1 <= _F1_MAX:
        raise ValueError(f"f1 out of range: {f1}")
    if not -128 <= dk <= 127:
        raise ValueError(f"dk out of range: {dk}")
    if not 1 <= dt <= _DT_MAX:
        raise ValueError(f"dt out of range: {dt}")
    return (f1 << (DK_BITS + DT_BITS)) | ((dk & 0xFF) << DT_BITS) | dt


def unpack_hash(h: int) -> tuple[int, int, int]:
    """Inverse of pack_hash.

    >>> unpack_hash(pack_hash(511, -63, 12))
    (511, -63, 12)
    """
    f1 = h >> (DK_BITS + DT_BITS)
    dk = (h >> DT_BITS) & 0xFF
    if dk >= 128:
        dk -= 256
    return f1, dk, h & _DT_MAX


def effective_hash_space(profile: Profile, band: tuple[int, int]) -> int:
    """In-band hash-type space for a class: band_bins × Δk values × Δt values.

    The collision null of the geometry statistic (E4) — NOT 2^24: only
    in-band anchors with |Δk| ≤ K_MAX and Δt ≤ t_max are reachable.

    >>> from engine.types import PROFILES
    >>> effective_hash_space(PROFILES["ORDER"], (8, 56))  # whirl orders 2–14
    62230
    """
    if profile.t_max is None:
        raise ValueError(f"profile {profile.name} is not hashed")
    k_lo, k_hi = band
    return (k_hi - k_lo + 1) * (2 * K_MAX + 1) * profile.t_max


def hash_constellation(
    peaks: list[Peak],
    profile: Profile,
    fanout: int = FANOUT,
    k_max: int = K_MAX,
) -> list[tuple[int, int]]:
    """Emit (hash, t_anchor_frame) pairs for a constellation.

    Pairing rule: for each anchor (in (m, k) order), targets are peaks with
    1 ≤ Δt ≤ profile.t_max and |Δk| ≤ k_max, sorted by (Δt, |Δk|, k), first
    ``fanout`` taken. Library and query use the identical rule, so their hash
    populations match by construction (A1).
    """
    if profile.t_max is None:
        raise ValueError(f"profile {profile.name} is not hashed")
    t_max = profile.t_max
    ordered = sorted(peaks, key=lambda p: (p.m, p.k))
    out: list[tuple[int, int]] = []
    for anchor in ordered:
        candidates = [
            (p.m - anchor.m, abs(p.k - anchor.k), p.k, p)
            for p in ordered
            if 1 <= p.m - anchor.m <= t_max and abs(p.k - anchor.k) <= k_max
        ]
        candidates.sort(key=lambda c: (c[0], c[1], c[2]))
        for dt, _, _, target in candidates[:fanout]:
            out.append((pack_hash(anchor.k, target.k - anchor.k, dt), anchor.m))
    return out
