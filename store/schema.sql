-- DrillPrint fingerprint store, schema v2 (spec v1.3 A12; E4/E5 additions noted).

PRAGMA user_version = 2;

CREATE TABLE IF NOT EXISTS libraries (
  version      TEXT PRIMARY KEY,
  created      TEXT NOT NULL,
  notes        TEXT,
  status       TEXT NOT NULL DEFAULT 'built'
               CHECK (status IN ('built','validated','approved')),
  approved_by  TEXT,
  approved_at  TEXT
);

-- Single source of truth for runtime state: 'active_library_version', 'project_stage', ...
CREATE TABLE IF NOT EXISTS app_state (
  key   TEXT PRIMARY KEY,
  value TEXT
);

-- Episode identity is (library_version, slug): the same sweep corner keeps
-- its canonical slug across library rebuilds (v1.3 erratum to A12, which
-- wrongly made slug globally UNIQUE). id = '<version>/<slug>'.
CREATE TABLE IF NOT EXISTS episodes (
  id              TEXT PRIMARY KEY,
  slug            TEXT NOT NULL,
  class           TEXT NOT NULL,
  library_version TEXT NOT NULL REFERENCES libraries(version),
  duration_s      REAL NOT NULL,
  params_json     TEXT NOT NULL,
  UNIQUE (library_version, slug)
);

CREATE TABLE IF NOT EXISTS episode_channels (
  episode_id TEXT NOT NULL REFERENCES episodes(id),
  channel    TEXT NOT NULL,
  fs         REAL NOT NULL,
  PRIMARY KEY (episode_id, channel)
);

-- Per-(episode, profile) fingerprinting stats: n_frames feeds the offset
-- statistic's δ-bin sizing; n_distinct feeds the E4 geometry null.
-- (Schema addition over A12 — record in errata for v1.3.1.)
CREATE TABLE IF NOT EXISTS episode_profiles (
  episode_id TEXT NOT NULL REFERENCES episodes(id),
  profile    TEXT NOT NULL,
  n_frames   INTEGER NOT NULL,
  n_hashes   INTEGER NOT NULL,
  n_distinct INTEGER NOT NULL,
  PRIMARY KEY (episode_id, profile)
);

CREATE TABLE IF NOT EXISTS fingerprints (
  hash       INTEGER NOT NULL,               -- 24-bit packed
  episode_id TEXT NOT NULL REFERENCES episodes(id),
  channel    TEXT NOT NULL,
  profile    TEXT NOT NULL,                  -- 'LOW'|'LOW_DEEP'|'ORDER'
  domain     TEXT NOT NULL,                  -- 'time'|'order'
  t_anchor   INTEGER NOT NULL                -- hop-frame index within the episode
);
CREATE INDEX IF NOT EXISTS idx_fp_lookup  ON fingerprints(hash, profile, domain);
CREATE INDEX IF NOT EXISTS idx_fp_ep_hash ON fingerprints(episode_id, hash);

-- Materialized DISTINCT (hash, episode) pairs: the E4 geometry screen reads
-- this, not the anchor-level table — a stationary comb stores each hash type
-- at ~every anchor, so the screen would otherwise walk ~100k redundant rows
-- per evaluation. (Schema addition over A12 — errata for v1.3.1.)
CREATE TABLE IF NOT EXISTS fingerprint_types (
  hash       INTEGER NOT NULL,
  episode_id TEXT NOT NULL REFERENCES episodes(id),
  channel    TEXT NOT NULL,
  profile    TEXT NOT NULL,
  domain     TEXT NOT NULL,
  n_anchors  INTEGER NOT NULL,  -- anchors carrying this type in this episode:
                                -- > EVOLVING_CAP means stationary (E4) — its
                                -- offset contribution is uniform, so its
                                -- anchors never need to be fetched
  PRIMARY KEY (hash, profile, domain, channel, episode_id)
) WITHOUT ROWID;

-- The A1 profile table, as data.
CREATE TABLE IF NOT EXISTS profiles (
  name            TEXT PRIMARY KEY,
  domain          TEXT NOT NULL,
  rate            REAL NOT NULL,
  n               INTEGER NOT NULL,
  hop             INTEGER NOT NULL,
  window_w        REAL,
  eval_cadence    REAL NOT NULL,
  t_max           INTEGER,
  hashed          INTEGER NOT NULL,
  peak_dm         INTEGER NOT NULL,          -- E4b per-profile peak neighborhood
  peak_dk         INTEGER NOT NULL
);

-- The A9/A10 class bindings, as data. band_lo/band_hi are hashing-band bin
-- indices for the bound profile (addition over A12 — errata for v1.3.1).
CREATE TABLE IF NOT EXISTS class_bindings (
  class    TEXT NOT NULL,
  channel  TEXT NOT NULL,
  role     TEXT NOT NULL CHECK (role IN ('hashed_primary','hashed','display')),
  profile  TEXT NOT NULL,
  band_lo  INTEGER NOT NULL,
  band_hi  INTEGER NOT NULL,
  min_fs   REAL NOT NULL,
  PRIMARY KEY (class, channel)
);
