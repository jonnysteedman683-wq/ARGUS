-- TimescaleDB schema (production). Apply after `CREATE EXTENSION timescaledb;`.
-- Same logical model as the SQLite schema, but with jsonb + hypertables and
-- native timestamptz for efficient time-series scans and retention policies.

CREATE TABLE IF NOT EXISTS observations (
    ts         TIMESTAMPTZ NOT NULL,
    source     TEXT        NOT NULL,
    kind       TEXT        NOT NULL,
    content    JSONB       NOT NULL DEFAULT '{}',
    text       TEXT,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 1.0
);
SELECT create_hypertable('observations', 'ts', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_obs_kind_ts ON observations (kind, ts DESC);

CREATE TABLE IF NOT EXISTS metrics (
    ts    TIMESTAMPTZ NOT NULL,
    name  TEXT        NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    unit  TEXT,
    tags  JSONB       NOT NULL DEFAULT '{}'
);
SELECT create_hypertable('metrics', 'ts', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_metrics_name_ts ON metrics (name, ts DESC);

CREATE TABLE IF NOT EXISTS profile_history (
    key        TEXT        NOT NULL,
    value      TEXT        NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_profile_key_ts ON profile_history (key, updated_at DESC);

CREATE TABLE IF NOT EXISTS preferences (
    topic      TEXT        NOT NULL,
    stance     TEXT        NOT NULL,
    kind       TEXT        NOT NULL DEFAULT 'stated',   -- 'stated' | 'revealed'
    context    TEXT,
    strength   DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    source     TEXT        NOT NULL DEFAULT 'conversation',
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pref_topic_ts ON preferences (topic, kind, updated_at DESC);

CREATE TABLE IF NOT EXISTS preference_changes (
    topic      TEXT        NOT NULL,
    context    TEXT,
    kind       TEXT        NOT NULL DEFAULT 'stated',
    old_stance TEXT        NOT NULL,
    new_stance TEXT        NOT NULL,
    reason     TEXT,
    ts         TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pref_change_topic_ts ON preference_changes (topic, ts DESC);
