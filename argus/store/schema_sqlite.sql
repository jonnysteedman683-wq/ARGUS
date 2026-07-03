-- SQLite schema (default v1 dev/local store). Timestamps are ISO-8601 UTC TEXT,
-- which sorts lexicographically, so `ts <= :as_of` gives correct as-of ordering.
-- JSON columns are stored as TEXT and (de)serialized in the repository.

CREATE TABLE IF NOT EXISTS observations (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT    NOT NULL,
    source     TEXT    NOT NULL,
    kind       TEXT    NOT NULL,
    content    TEXT    NOT NULL DEFAULT '{}',
    text       TEXT,
    confidence REAL    NOT NULL DEFAULT 1.0
);
CREATE INDEX IF NOT EXISTS idx_obs_ts ON observations (ts);
CREATE INDEX IF NOT EXISTS idx_obs_kind_ts ON observations (kind, ts);

CREATE TABLE IF NOT EXISTS metrics (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    ts    TEXT    NOT NULL,
    name  TEXT    NOT NULL,
    value REAL    NOT NULL,
    unit  TEXT,
    tags  TEXT    NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_metrics_name_ts ON metrics (name, ts);

-- Profile facts are append-only history; the current value is the latest row
-- per key with updated_at <= now (or <= :as_of).
CREATE TABLE IF NOT EXISTS profile_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    key        TEXT NOT NULL,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_profile_key_ts ON profile_history (key, updated_at);

CREATE TABLE IF NOT EXISTS preferences (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    topic      TEXT NOT NULL,
    stance     TEXT NOT NULL,
    strength   REAL NOT NULL DEFAULT 0.5,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pref_topic_ts ON preferences (topic, updated_at);
