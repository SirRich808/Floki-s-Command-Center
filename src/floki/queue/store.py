from __future__ import annotations

from pathlib import Path

import aiosqlite

from floki.queue.models import Envelope, MessageStatus, Source

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class QueueStore:
    """Async SQLite-backed Waiting Room.

    Two atomicity guarantees matter:
      1. enqueue() is a single INSERT.
      2. claim_next() uses BEGIN IMMEDIATE so concurrent dispatchers can't double-claim.
    """

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    async def init(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            with open(SCHEMA_PATH) as f:
                await db.executescript(f.read())
            await db.commit()

    async def enqueue(self, env: Envelope) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                INSERT INTO envelopes
                    (source, source_ref, target_agent, payload, routing_reason, priority)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    env.source.value,
                    env.source_ref,
                    env.target_agent,
                    env.payload,
                    env.routing_reason,
                    env.priority,
                ),
            )
            await db.commit()
            return cur.lastrowid or 0

    async def claim_next(self) -> Envelope | None:
        """Atomically mark the oldest queued envelope as 'pushing' and return it."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("BEGIN IMMEDIATE")
            cur = await db.execute(
                """
                SELECT id, source, source_ref, target_agent, payload,
                       routing_reason, priority, status, attempts,
                       last_error, created_at, claimed_at, delivered_at
                FROM envelopes
                WHERE status = 'queued'
                ORDER BY priority ASC, id ASC
                LIMIT 1
                """
            )
            row = await cur.fetchone()
            if row is None:
                await db.commit()
                return None

            env_id = row[0]
            await db.execute(
                """
                UPDATE envelopes
                SET status = 'pushing',
                    claimed_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
                    attempts = attempts + 1
                WHERE id = ?
                """,
                (env_id,),
            )
            await db.commit()

            return Envelope(
                id=row[0],
                source=Source(row[1]),
                source_ref=row[2],
                target_agent=row[3],
                payload=row[4],
                routing_reason=row[5] or "default",
                priority=row[6],
                status=MessageStatus.PUSHING,
                attempts=row[8] + 1,
                last_error=row[9],
                created_at=row[10],
                claimed_at=row[11],
                delivered_at=row[12],
            )

    async def mark_delivered(self, envelope_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE envelopes
                SET status = 'delivered',
                    delivered_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE id = ?
                """,
                (envelope_id,),
            )
            await db.execute(
                "INSERT INTO hive_events (envelope_id, agent, event_type) "
                "SELECT id, target_agent, 'delivered' FROM envelopes WHERE id = ?",
                (envelope_id,),
            )
            await db.commit()

    async def mark_failed(self, envelope_id: int, error: str, requeue: bool) -> None:
        new_status = "queued" if requeue else "failed"
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE envelopes
                SET status = ?, last_error = ?, claimed_at = NULL
                WHERE id = ?
                """,
                (new_status, error, envelope_id),
            )
            if not requeue:
                await db.execute(
                    "INSERT INTO hive_events (envelope_id, agent, event_type, detail) "
                    "SELECT id, target_agent, 'failed', ? FROM envelopes WHERE id = ?",
                    (error, envelope_id),
                )
            await db.commit()

    async def pending_count(self) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("SELECT COUNT(*) FROM envelopes WHERE status = 'queued'")
            row = await cur.fetchone()
            return int(row[0]) if row else 0
