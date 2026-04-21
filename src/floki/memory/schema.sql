-- Washing Machine memory engine (Phase 3).
-- Lives in the same SQLite file as the Waiting Room so the washer can join
-- against envelopes in a single transaction.

CREATE TABLE IF NOT EXISTS memories (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    category          TEXT    NOT NULL,       -- pinned | decaying | insight
    scope_agent       TEXT,                   -- NULL = global (all agents see it)
    content           TEXT    NOT NULL,
    source_envelope   INTEGER,                -- envelope id that produced this memory
    decay_days        INTEGER,                -- NULL = never decays (pinned)
    created_at        TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (source_envelope) REFERENCES envelopes(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_memories_category ON memories (category);
CREATE INDEX IF NOT EXISTS idx_memories_scope    ON memories (scope_agent, category);

-- Tracks which envelopes the washer has already processed. Avoids double-extraction.
CREATE TABLE IF NOT EXISTS washer_progress (
    envelope_id     INTEGER PRIMARY KEY,
    processed_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
