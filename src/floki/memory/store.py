from __future__ import annotations

from pathlib import Path

import aiosqlite

from floki.memory.models import Memory, MemoryCategory, MemoryDraft

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class MemoryStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    async def init(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            with open(SCHEMA_PATH) as f:
                await db.executescript(f.read())
            await db.commit()

    async def insert(self, draft: MemoryDraft, source_envelope: int | None = None) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                INSERT INTO memories (category, scope_agent, content, source_envelope, decay_days)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    draft.category.value,
                    draft.scope_agent,
                    draft.content,
                    source_envelope,
                    draft.decay_days,
                ),
            )
            await db.commit()
            return cur.lastrowid or 0

    async def for_agent(self, agent_name: str) -> list[Memory]:
        """All live memories visible to this agent: global pinned/insights,
        plus memories scoped to this agent. Decayed rows are filtered out."""
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                SELECT id, category, scope_agent, content, source_envelope,
                       decay_days, created_at
                FROM memories
                WHERE (scope_agent IS NULL OR scope_agent = ?)
                  AND (
                    decay_days IS NULL
                    OR julianday('now') - julianday(created_at) <= decay_days
                  )
                ORDER BY
                  CASE category
                    WHEN 'pinned' THEN 0
                    WHEN 'insight' THEN 1
                    ELSE 2
                  END,
                  id DESC
                """,
                (agent_name,),
            )
            rows = await cur.fetchall()
        return [
            Memory(
                id=r[0],
                category=MemoryCategory(r[1]),
                scope_agent=r[2],
                content=r[3],
                source_envelope=r[4],
                decay_days=r[5],
                created_at=r[6],
            )
            for r in rows
        ]

    async def prune_decayed(self) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                DELETE FROM memories
                WHERE decay_days IS NOT NULL
                  AND julianday('now') - julianday(created_at) > decay_days
                """
            )
            await db.commit()
            return cur.rowcount or 0

    async def counts_by_category(self) -> dict[str, int]:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT category, COUNT(*) FROM memories GROUP BY category"
            )
            rows = await cur.fetchall()
        return {r[0]: int(r[1]) for r in rows}

    async def unwashed_envelopes(self, limit: int = 100) -> list[tuple[int, str, str]]:
        """Envelopes the washer hasn't processed yet. Returns (id, payload, target_agent)."""
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                SELECT e.id, e.payload, e.target_agent
                FROM envelopes e
                LEFT JOIN washer_progress w ON w.envelope_id = e.id
                WHERE w.envelope_id IS NULL
                ORDER BY e.id ASC
                LIMIT ?
                """,
                (limit,),
            )
            rows = await cur.fetchall()
        return [(int(r[0]), r[1], r[2]) for r in rows]

    async def mark_washed(self, envelope_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO washer_progress (envelope_id) VALUES (?)",
                (envelope_id,),
            )
            await db.commit()
