"""SQLite access layer: bulk insert, filtered postings lookup, versioning (A12).

The §31 change-control state machine is enforced here: built → validated →
approved (strictly in order), and only an approved library can be activated.
The matcher's query path (`postings`) filters on (hash, profile, domain),
the class's hashed channels, and the active library — §11's per-class channel
binding lives in this filter.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from engine.types import PROFILES

_SCHEMA = (Path(__file__).parent / "schema.sql").read_text()

_STATUS_ORDER = ("built", "validated", "approved")

# Fingerprinting pipelines (A9/A10): an episode is fingerprinted under every
# pipeline whose channels it carries — which automatically gives dysfunction
# episodes their own binding and NORMAL episodes a presence in every match
# space (§5: healthy baselines absorb matches / suppress false positives).
PIPELINES: dict[str, dict] = {
    "STICK_SLIP": {
        "channels": ("TORQUE_SURF", "RPM_DH"),
        "primary": "TORQUE_SURF",
        "domain": "time",
        "profile": "LOW",  # LOW_DEEP when predicted f0 < 0.12 Hz (A1)
        "band": (3, 102),  # 0.1–4 Hz at Δf = 0.0390625 (same bins on LOW_DEEP)
        "min_fs": 10.0,
    },
    "WHIRL_BACKWARD": {
        "channels": ("ACC_LAT_X", "ACC_LAT_Y"),
        "primary": "ACC_LAT_X",
        "domain": "order",
        "profile": "ORDER",
        "band": (8, 56),  # orders 2–14 at Δorder = 0.25
        "min_fs": 400.0,
    },
    "BIT_BOUNCE": {
        "channels": ("ACC_AX",),
        "primary": "ACC_AX",
        "domain": "order",
        "profile": "ORDER",
        "band": (8, 40),  # orders 2–10
        "min_fs": 100.0,
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class StateError(RuntimeError):
    """Raised on an illegal library state transition or activation."""


class FingerprintDB:
    SCHEMA_VERSION = 2

    def __init__(self, path: str | Path):
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        has_tables = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='episodes'"
        ).fetchone() is not None
        found = self.conn.execute("PRAGMA user_version").fetchone()[0]
        if has_tables and found != self.SCHEMA_VERSION:
            self.conn.close()
            raise StateError(
                f"{path}: store schema v{found} != code schema "
                f"v{self.SCHEMA_VERSION} — no migrations pre-release; delete the "
                f"DB file and rebuild (python -m synth.build_library)"
            )
        self.conn.executescript(_SCHEMA)
        self._seed_reference_data()
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def _seed_reference_data(self) -> None:
        for p in PROFILES.values():
            self.conn.execute(
                "INSERT OR REPLACE INTO profiles VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (p.name, p.domain, p.rate, p.n, p.hop, p.window_w,
                 p.eval_cadence, p.t_max, int(p.hashed),
                 p.peak_neighborhood[0], p.peak_neighborhood[1]),
            )
        for cls, cfg in PIPELINES.items():
            for ch in cfg["channels"]:
                role = "hashed_primary" if ch == cfg["primary"] else "hashed"
                self.conn.execute(
                    "INSERT OR REPLACE INTO class_bindings VALUES (?,?,?,?,?,?,?)",
                    (cls, ch, role, cfg["profile"], *cfg["band"], cfg["min_fs"]),
                )
        # display-only bindings (A9): WOB sees BIT_BOUNCE but is never hashed
        self.conn.execute(
            "INSERT OR REPLACE INTO class_bindings VALUES "
            "('BIT_BOUNCE','WOB','display','ORDER',8,40,10.0)"
        )

    # ---- libraries & state machine ----

    def create_library(self, version: str, notes: str = "") -> None:
        self.conn.execute(
            "INSERT INTO libraries (version, created, notes) VALUES (?,?,?)",
            (version, _now(), notes),
        )
        self.conn.commit()

    def status(self, version: str) -> str:
        row = self.conn.execute(
            "SELECT status FROM libraries WHERE version=?", (version,)
        ).fetchone()
        if row is None:
            raise KeyError(f"no library {version!r}")
        return row[0]

    def set_status(self, version: str, status: str, approved_by: str | None = None) -> None:
        """Advance the §31 state machine — one step at a time, in order."""
        current = self.status(version)
        if _STATUS_ORDER.index(status) != _STATUS_ORDER.index(current) + 1:
            raise StateError(f"illegal transition {current!r} → {status!r}")
        if status == "approved":
            if not approved_by:
                raise StateError("approval requires approved_by (name), §31")
            self.conn.execute(
                "UPDATE libraries SET status=?, approved_by=?, approved_at=? WHERE version=?",
                (status, approved_by, _now(), version),
            )
        else:
            self.conn.execute(
                "UPDATE libraries SET status=? WHERE version=?", (status, version)
            )
        self.conn.commit()

    def activate(self, version: str) -> None:
        """POST /libraries/{v}/activate — rejects anything not approved (A12)."""
        if self.status(version) != "approved":
            raise StateError(f"library {version!r} is {self.status(version)!r}, not approved")
        self.conn.execute(
            "INSERT OR REPLACE INTO app_state VALUES ('active_library_version', ?)",
            (version,),
        )
        self.conn.commit()

    def active_version(self) -> str | None:
        row = self.conn.execute(
            "SELECT value FROM app_state WHERE key='active_library_version'"
        ).fetchone()
        return row[0] if row else None

    # ---- episodes & fingerprints ----

    def add_episode(
        self,
        library_version: str,
        slug: str,
        dysfunction_class: str,
        duration_s: float,
        params: dict,
        channels: list[tuple[str, float]],
        fingerprints: list[tuple[int, str, str, str, int]],
        profile_stats: list[tuple[str, int, int, int]],
    ) -> None:
        """Bulk-insert one episode.

        ``fingerprints`` rows are (hash, channel, profile, domain, t_anchor);
        ``profile_stats`` rows are (profile, n_frames, n_hashes, n_distinct).
        """
        episode_id = f"{library_version}/{slug}"
        self.conn.execute(
            "INSERT INTO episodes VALUES (?,?,?,?,?,?)",
            (episode_id, slug, dysfunction_class, library_version, duration_s,
             json.dumps(params, sort_keys=True)),
        )
        self.conn.executemany(
            "INSERT INTO episode_channels VALUES (?,?,?)",
            [(episode_id, ch, fs) for ch, fs in channels],
        )
        self.conn.executemany(
            "INSERT INTO episode_profiles VALUES (?,?,?,?,?)",
            [(episode_id, *row) for row in profile_stats],
        )
        self.conn.executemany(
            "INSERT INTO fingerprints VALUES (?,?,?,?,?,?)",
            [(h, episode_id, ch, prof, dom, t) for h, ch, prof, dom, t in fingerprints],
        )
        anchor_counts: dict[tuple, int] = {}
        for h, ch, prof, dom, _ in fingerprints:
            key = (h, episode_id, ch, prof, dom)
            anchor_counts[key] = anchor_counts.get(key, 0) + 1
        self.conn.executemany(
            "INSERT INTO fingerprint_types VALUES (?,?,?,?,?,?)",
            [(*key, n) for key, n in anchor_counts.items()],
        )
        self.conn.commit()

    def _require_version(self, library_version: str | None) -> str:
        version = library_version or self.active_version()
        if version is None:
            raise StateError("no active library (activate an approved version first)")
        return version

    def geometry_counts(
        self,
        hashes: list[int],
        profile: str,
        domain: str,
        channels: tuple[str, ...],
        library_version: str | None = None,
    ) -> dict[str, int]:
        """episode_id → distinct matched hash types, aggregated IN SQL.

        The E4 geometry screen: stationary combs put each hash type at ~every
        anchor of ~every same-class episode, so pulling raw postings for all
        candidates is O(100k) rows — this aggregate rides the (hash, profile,
        domain) index and returns one row per episode instead.
        """
        version = self._require_version(library_version)
        out: dict[str, int] = {}
        ch_q = ",".join("?" * len(channels))
        sql = (
            f"SELECT t.episode_id, COUNT(DISTINCT t.hash) FROM fingerprint_types t "
            f"JOIN episodes e ON e.id = t.episode_id "
            f"WHERE t.hash IN ({{}}) AND t.profile=? AND t.domain=? "
            f"AND t.channel IN ({ch_q}) AND e.library_version=? "
            f"GROUP BY t.episode_id"
        )
        CHUNK = 500
        uniq = sorted(set(hashes))
        for i in range(0, len(uniq), CHUNK):
            chunk = uniq[i : i + CHUNK]
            for ep, n in self.conn.execute(
                sql.format(",".join("?" * len(chunk))),
                (*chunk, profile, domain, *channels, version),
            ).fetchall():
                out[ep] = out.get(ep, 0) + n
        return out

    def postings(
        self,
        hashes: list[int],
        profile: str,
        domain: str,
        channels: tuple[str, ...],
        library_version: str | None = None,
        episodes: tuple[str, ...] | None = None,
    ) -> dict[int, list[tuple[str, int]]]:
        """hash → [(episode_id, t_anchor)] for the matcher, filtered per A12.

        Pass ``episodes`` to restrict to the geometry screen's top candidates
        (the two-stage query path); omitting it fetches all — fine for small
        libraries, O(100k) rows against a full one.
        """
        version = self._require_version(library_version)
        out: dict[int, list[tuple[str, int]]] = {}
        ch_q = ",".join("?" * len(channels))
        uniq = sorted(set(hashes))
        CHUNK = 500
        if episodes is not None:
            # Stage-2 path: episode-first via idx_fp_ep_hash — a handful of
            # episodes' rows instead of every anchor of every hash.
            ep_q = ",".join("?" * len(episodes))
            sql = (
                f"SELECT f.hash, f.episode_id, f.t_anchor "
                f"FROM fingerprints f INDEXED BY idx_fp_ep_hash "
                f"WHERE f.episode_id IN ({ep_q}) AND f.hash IN ({{}}) "
                f"AND f.profile=? AND f.domain=? AND f.channel IN ({ch_q})"
            )
            for i in range(0, len(uniq), CHUNK):
                chunk = uniq[i : i + CHUNK]
                rows = self.conn.execute(
                    sql.format(",".join("?" * len(chunk))),
                    (*episodes, *chunk, profile, domain, *channels),
                ).fetchall()
                for h, ep, t in rows:
                    out.setdefault(h, []).append((ep, t))
            return out
        sql = (
            f"SELECT f.hash, f.episode_id, f.t_anchor FROM fingerprints f "
            f"JOIN episodes e ON e.id = f.episode_id "
            f"WHERE f.hash IN ({{}}) AND f.profile=? AND f.domain=? "
            f"AND f.channel IN ({ch_q}) AND e.library_version=?"
        )
        for i in range(0, len(uniq), CHUNK):
            chunk = uniq[i : i + CHUNK]
            rows = self.conn.execute(
                sql.format(",".join("?" * len(chunk))),
                (*chunk, profile, domain, *channels, version),
            ).fetchall()
            for h, ep, t in rows:
                out.setdefault(h, []).append((ep, t))
        return out

    def evolving_postings(
        self,
        hashes: list[int],
        profile: str,
        domain: str,
        channels: tuple[str, ...],
        episodes: tuple[str, ...],
        max_anchors_per_type: int,
    ) -> dict[int, list[tuple[str, int]]]:
        """Anchor postings for EVOLVING hash types only (E4 offset path).

        Types with n_anchors > max_anchors_per_type are stationary within the
        episode: their offset contribution is uniform by construction, so
        their anchors stay in the database. The planner drives from the small
        types table and seeks the anchor table per qualifying type.
        """
        out: dict[int, list[tuple[str, int]]] = {}
        ch_q = ",".join("?" * len(channels))
        ep_q = ",".join("?" * len(episodes))
        uniq = sorted(set(hashes))
        CHUNK = 500
        # CROSS JOIN pins the join order (SQLite honors it literally): drive
        # from the small types table, seek the anchor table per qualifying
        # type — never scan whole episodes.
        sql = (
            f"SELECT f.hash, f.episode_id, f.t_anchor "
            f"FROM fingerprint_types t "
            f"CROSS JOIN fingerprints f INDEXED BY idx_fp_ep_hash "
            f"  ON f.episode_id = t.episode_id AND f.hash = t.hash "
            f" AND f.profile = t.profile AND f.domain = t.domain "
            f" AND f.channel = t.channel "
            f"WHERE t.hash IN ({{}}) AND t.episode_id IN ({ep_q}) "
            f"AND t.profile=? AND t.domain=? AND t.channel IN ({ch_q}) "
            f"AND t.n_anchors <= ?"
        )
        for i in range(0, len(uniq), CHUNK):
            chunk = uniq[i : i + CHUNK]
            rows = self.conn.execute(
                sql.format(",".join("?" * len(chunk))),
                (*chunk, *episodes, profile, domain, *channels, max_anchors_per_type),
            ).fetchall()
            for h, ep, t in rows:
                out.setdefault(h, []).append((ep, t))
        return out

    def episode_frames(self, profile: str, library_version: str | None = None) -> dict[str, int]:
        version = library_version or self.active_version()
        rows = self.conn.execute(
            "SELECT ep.episode_id, ep.n_frames FROM episode_profiles ep "
            "JOIN episodes e ON e.id = ep.episode_id "
            "WHERE ep.profile=? AND e.library_version=?",
            (profile, version),
        ).fetchall()
        return dict(rows)

    def episode_distinct(self, profile: str, library_version: str | None = None) -> dict[str, int]:
        version = library_version or self.active_version()
        rows = self.conn.execute(
            "SELECT ep.episode_id, ep.n_distinct FROM episode_profiles ep "
            "JOIN episodes e ON e.id = ep.episode_id "
            "WHERE ep.profile=? AND e.library_version=?",
            (profile, version),
        ).fetchall()
        return dict(rows)

    def stats(self, library_version: str) -> dict:
        """Per-class episode and hash counts (Library screen, §20/§31)."""
        by_class = dict(self.conn.execute(
            "SELECT class, COUNT(*) FROM episodes WHERE library_version=? GROUP BY class",
            (library_version,),
        ).fetchall())
        n_hashes = self.conn.execute(
            "SELECT COUNT(*) FROM fingerprints f JOIN episodes e ON e.id=f.episode_id "
            "WHERE e.library_version=?",
            (library_version,),
        ).fetchone()[0]
        return {"episodes_by_class": by_class, "n_hashes": n_hashes}
