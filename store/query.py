"""Two-stage class matcher over the store (M3; consumed by M4's scheduler).

Stage 1 — geometry screen: COUNT(DISTINCT hash) per episode, in SQL.
Stage 2 — detailed postings for the top-K candidates only, then the full
dual-statistic matcher (offset + geometry, E4).

A ClassMatcher pre-loads the per-library static context (frames, distinct
counts, effective hash space) once; evaluate() is then the per-window hot
path the §18 ≤ 10 ms gate applies to.
"""

from __future__ import annotations

from engine.hashing import effective_hash_space
from engine.matcher import match_hashes
from engine.types import PROFILES, MatchResult

from .fingerprint_db import PIPELINES, FingerprintDB

TOP_K = 8  # candidates carried from the geometry screen into stage 2
EVOLVING_CAP = 8  # anchors per (episode, hash-type) above which a type is
                  # stationary — offset detail stays in the database (E4)


class ClassMatcher:
    def __init__(
        self,
        db: FingerprintDB,
        class_name: str,
        profile_name: str | None = None,
        library_version: str | None = None,
    ):
        cfg = PIPELINES[class_name]
        self.db = db
        self.class_name = class_name
        self.profile_name = profile_name or cfg["profile"]
        self.domain: str = cfg["domain"]
        self.channels: tuple[str, ...] = cfg["channels"]
        self.band: tuple[int, int] = cfg["band"]
        self.version = db._require_version(library_version)
        self.s_eff = effective_hash_space(PROFILES[self.profile_name], self.band)
        # static per-library context, loaded once
        self.episode_frames = db.episode_frames(self.profile_name, self.version)
        self.episode_distinct = db.episode_distinct(self.profile_name, self.version)
        # §5 negative-class absorption: matches are attributed to their winning
        # episode's CLASS — a best-match on a NORMAL_DRILLING episode is a
        # healthy verdict, never a dysfunction alert.
        self.episode_class: dict[str, str] = dict(
            db.conn.execute(
                "SELECT id, class FROM episodes WHERE library_version=?",
                (self.version,),
            ).fetchall()
        )
        # E6b: the geometry statistic's empirical null population (§5 —
        # normal baselines absorb structured noise; their match counts
        # calibrate the collision background).
        self.null_ids: set[str] = {
            eid for eid, c in self.episode_class.items() if c == "NORMAL_DRILLING"
        }

    def evaluate(self, query_hashes: list[tuple[int, int]], query_frames: int) -> list[MatchResult]:
        """One matcher evaluation of a query window against the active library."""
        hashes = [h for h, _ in query_hashes]
        geo = self.db.geometry_counts(
            hashes, self.profile_name, self.domain, self.channels, self.version
        )
        if not geo:
            return []
        top = tuple(sorted(geo, key=lambda ep: -geo[ep])[:TOP_K])
        postings = self.db.evolving_postings(
            hashes, self.profile_name, self.domain, self.channels,
            top, EVOLVING_CAP,
        )
        return match_hashes(
            query_hashes, postings, self.episode_frames, query_frames,
            s_eff=self.s_eff, episode_distinct=self.episode_distinct,
            geometry_counts=geo,
            null_episode_ids=self.null_ids,
            # E7 supersedes E6c on the query path: with prominence-gated
            # landmarks, structured noise cannot form constellations, and a
            # CLEAN stationary comb legitimately has a flat offset histogram —
            # corroboration would block genuine matches (measured: right
            # corner, p_geom 1e-64, p_off 0.36). The matcher keeps the
            # mechanism for callers that need it.
            require_offset_corroboration=False,
        )
