from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import aiosqlite


@dataclass(frozen=True)
class HiveEvent:
    id: int
    envelope_id: int | None
    agent: str
    event_type: str
    detail: str | None
    created_at: str


class HiveMind:
    """Unified view over every task every agent has touched.

    Writes happen from `QueueStore.mark_delivered` / `mark_failed`, which keeps
    the hive_events log append-only and co-located with the Waiting Room so
    Floki's triage prompt can query both in one DB round-trip.
    """

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    async def record(
        self,
        agent: str,
        event_type: str,
        envelope_id: int | None = None,
        detail: str | None = None,
    ) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                INSERT INTO hive_events (envelope_id, agent, event_type, detail)
                VALUES (?, ?, ?, ?)
                """,
                (envelope_id, agent, event_type, detail),
            )
            await db.commit()
            return cur.lastrowid or 0

    async def recent(self, agent: str | None = None, limit: int = 20) -> list[HiveEvent]:
        q = (
            "SELECT id, envelope_id, agent, event_type, detail, created_at "
            "FROM hive_events "
        )
        params: tuple = ()
        if agent:
            q += "WHERE agent = ? "
            params = (agent,)
        q += "ORDER BY id DESC LIMIT ?"
        params = (*params, limit)

        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(q, params)
            rows = await cur.fetchall()
        return [HiveEvent(*row) for row in rows]

    async def counts_by_agent(self) -> dict[str, int]:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT agent, COUNT(*) FROM hive_events GROUP BY agent"
            )
            rows = await cur.fetchall()
        return {row[0]: int(row[1]) for row in rows}
