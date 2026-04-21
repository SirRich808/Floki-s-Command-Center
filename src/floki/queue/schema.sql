-- Waiting Room. Every inbound signal (Telegram, cron, voice, dashboard) lands here
-- as an Envelope. The dispatcher pulls one row at a time in FIFO order.

PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS envelopes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT    NOT NULL,            -- telegram | cron | voice | dashboard | agent
    source_ref      TEXT,                        -- e.g. telegram chat_id or cron job name
    target_agent    TEXT    NOT NULL,            -- floki | comms | content | ops | research | *broadcast*
    payload         TEXT    NOT NULL,            -- raw user text / JSON task
    routing_reason  TEXT,                        -- keyword | prefix | logic | default
    priority        INTEGER NOT NULL DEFAULT 100,
    status          TEXT    NOT NULL DEFAULT 'queued', -- queued | pushing | delivered | failed
    attempts        INTEGER NOT NULL DEFAULT 0,
    last_error      TEXT,
    created_at      TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    claimed_at      TEXT,
    delivered_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_envelopes_status_priority
    ON envelopes (status, priority, id);

CREATE INDEX IF NOT EXISTS idx_envelopes_target
    ON envelopes (target_agent, status);

-- Hive Mind hook (Phase 4 will expand this). Kept here so the dispatcher can insert
-- a delivery record without a second schema migration.
CREATE TABLE IF NOT EXISTS hive_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    envelope_id   INTEGER,
    agent         TEXT NOT NULL,
    event_type    TEXT NOT NULL,    -- delivered | failed | completed
    detail        TEXT,
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (envelope_id) REFERENCES envelopes(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_hive_agent_time
    ON hive_events (agent, created_at DESC);
