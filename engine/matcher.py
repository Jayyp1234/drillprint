"""Offset-histogram matching with corrected Poisson significance (spec §10/A3).

Decision statistic per episode: score = max δ-bin count. Background rate λ is
estimated EXCLUDING the max bin (self-contamination guard) and floored at
LAM_MIN. Significance is multiple-comparison corrected across every episode ×
δ-bin tested: p_corr = n_episodes · n_bins · P(Poisson(λ) ≥ score). Tier-2
alert requires score ≥ S_MIN and p_corr < P_THRESHOLD; the K=2 debounce
belongs to the streaming layer (M4).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping

from scipy.stats import poisson

from .types import MatchResult

DELTA_BIN_WIDTH = 3  # frames (spec §11: ≥ 3 frames vs quantization jitter)
S_MIN = 8
P_THRESHOLD = 1e-4
LAM_MIN = 0.05
D_MIN = 12  # geometry statistic: minimum distinct matched hash types (E4)
# E6c: offset-consistency gate for time-domain geometry alerts. This is a
# non-flatness requirement, not the significance claim (that is p_geom):
# structured noise shows p_off ~ 1.0, genuine matches ≤ ~0.09 even at 0 dB —
# 0.1 keeps a 10× margin against the measured spurious case.
CORROBORATION_P = 0.1


def match_hashes(
    query_hashes: Iterable[tuple[int, int]],
    postings: Mapping[int, Iterable[tuple[str, int]]],
    episode_frames: Mapping[str, int],
    query_frames: int,
    bin_width: int = DELTA_BIN_WIDTH,
    s_min: int = S_MIN,
    p_threshold: float = P_THRESHOLD,
    s_eff: int | None = None,
    episode_distinct: Mapping[str, int] | None = None,
    d_min: int = D_MIN,
    geometry_counts: Mapping[str, int] | None = None,
    null_episode_ids: set[str] | None = None,
    require_offset_corroboration: bool = False,
) -> list[MatchResult]:
    """Score every candidate episode against one query window.

    ``postings`` maps hash → (episode_id, t_anchor_frame) postings (the store's
    hash index, already filtered to the active library, matching profile/domain,
    and the class's hashed channels — spec A12). ``episode_frames`` gives each
    episode's frame count, used to size the δ-bin space for the correction.

    Geometry statistic (E4): pass ``s_eff`` (effective in-band hash space, see
    hashing.effective_hash_space) and ``episode_distinct`` (distinct hash-type
    count per episode, a stored library column) to activate cross-realization
    scoring: distinct matched types m vs the collision null
    λ_geom = n_query_types × episode_types / s_eff, corrected across episodes.
    Omitting them leaves geometry fields inert (M0-compatible).

    ``geometry_counts`` (episode → distinct matched types, from the store's
    SQL screen) overrides the postings-derived counts — the two-stage query
    path passes anchor postings for EVOLVING types only, so stationary-only
    matches would otherwise undercount; such episodes still get a result with
    empty offset statistics (their histogram is uniform by construction, E4).

    Returns results sorted by best significance; empty if nothing collided.
    """
    histograms: dict[str, Counter[int]] = defaultdict(Counter)
    pair_counts: Counter[str] = Counter()
    type_matches: dict[str, set[int]] = defaultdict(set)
    query_types: set[int] = set()
    for h, t_q in query_hashes:
        query_types.add(h)
        for episode_id, t_lib in postings.get(h, ()):
            delta_bin = (t_lib - t_q) // bin_width
            histograms[episode_id][delta_bin] += 1
            pair_counts[episode_id] += 1
            type_matches[episode_id].add(h)

    n_episodes = max(len(episode_frames), 1)
    candidate_ids = set(histograms)
    if geometry_counts is not None:
        candidate_ids |= set(geometry_counts)
    results: list[MatchResult] = []
    for episode_id in candidate_ids:
        hist = histograms.get(episode_id, Counter())
        if hist:
            delta_star, score = max(hist.items(), key=lambda kv: (kv[1], -kv[0]))
        else:
            delta_star, score = 0, 0
        pairs = pair_counts[episode_id]
        n_bins = (episode_frames[episode_id] + query_frames) // bin_width + 1
        lam = max((pairs - score) / max(n_bins - 1, 1), LAM_MIN)
        if score > 0:
            p_raw = float(poisson.sf(score - 1, lam))  # P(X ≥ score)
            p_corr = min(1.0, n_episodes * n_bins * p_raw)
        else:
            p_corr = 1.0
        if geometry_counts is not None:
            distinct = geometry_counts.get(episode_id, 0)
        else:
            distinct = len(type_matches[episode_id])
        # E8b: the offset path also requires the distinct-evidence floor — on
        # stationary library content a SINGLE repeated query type piles into
        # one δ-bin and fakes alignment (measured: spurious fire at d=2,
        # coverage 0.01; genuine matches all carry d ≥ 16). Diagonal
        # significance without diverse type evidence is not a match.
        alert = score >= s_min and p_corr < p_threshold and distinct >= d_min
        lam_geom, p_geom_corr, geom_alert = 0.0, None, False
        if s_eff is not None and episode_distinct is not None:
            # NOTE (E7, open): the uniform null underestimates collisions when
            # query and library types concentrate in the same spectral region;
            # an empirical normals-median null was tried and reverted — it
            # flattens p_geom and destabilizes §5 absorption ranking (see
            # ERRATA E7). The E6c corroboration gate below carries the
            # structured-noise defense for time-domain pipelines instead.
            lam_analytic = len(query_types) * episode_distinct[episode_id] / s_eff
            lam_geom = max(lam_analytic, LAM_MIN)
            p_geom = float(poisson.sf(distinct - 1, lam_geom))
            p_geom_corr = min(1.0, n_episodes * p_geom)
            geom_alert = distinct >= d_min and p_geom_corr < p_threshold
            # E6c: time-domain libraries are deterministic, so a genuine match
            # ALWAYS carries diagonal-alignment structure — require it. Pure
            # type-region overlap (flat histogram, p_off ~ 1) is structured
            # noise resembling comb geometry, not a matched signal. Order-
            # domain cross-realization matches legitimately lack offsets and
            # keep the pure geometry path.
            if require_offset_corroboration and geom_alert:
                geom_alert = p_corr < CORROBORATION_P

        best_p = p_corr if p_geom_corr is None else min(p_corr, p_geom_corr)
        results.append(
            MatchResult(
                episode_id=episode_id,
                score=score,
                delta_star=delta_star,
                matched_pairs=pairs,
                lam=lam,
                p_corr=p_corr,
                confidence=min(1.0, max(0.0, 1.0 - best_p)),
                alert=alert,
                distinct_matched=distinct,
                lam_geom=lam_geom,
                p_geom_corr=p_geom_corr,
                geom_alert=geom_alert,
                histogram=dict(hist),
            )
        )
    # E7b: rank by RAW matched evidence (distinct types), Shazam-faithful.
    # Per-episode p-values normalize λ by each episode's type count, which
    # under noise queries ranks THIN dysfunction fingerprints above DENSE
    # normal sponges — inverting §5 absorption (measured: spurious ORDER
    # windows, normals d=282 vs corners ~100, yet corners outranked on p).
    # p-values remain the significance GATES of the winner; they no longer
    # decide who wins.
    results.sort(
        key=lambda r: (
            -r.distinct_matched,
            min(r.p_corr, r.p_geom_corr) if r.p_geom_corr is not None else r.p_corr,
            -r.score,
        )
    )
    return results
