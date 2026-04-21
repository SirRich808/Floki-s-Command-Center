from __future__ import annotations

from pathlib import Path

import pytest

from floki.hive import HiveMind
from floki.queue import Envelope, QueueStore, Source
from floki.queue.dispatcher import Dispatcher


@pytest.fixture
async def db(tmp_path: Path) -> Path:
    store = QueueStore(tmp_path / "q.db")
    await store.init()
    return tmp_path / "q.db"


async def test_record_and_recent(db: Path) -> None:
    hive = HiveMind(db)
    await hive.record("comms", "completed", envelope_id=None, detail="drafted reply")
    await hive.record("ops", "completed", envelope_id=None, detail="logged expense")

    recent = await hive.recent(limit=5)
    assert [e.agent for e in recent] == ["ops", "comms"]

    comms_only = await hive.recent(agent="comms")
    assert len(comms_only) == 1
    assert comms_only[0].detail == "drafted reply"


async def test_counts_by_agent_after_dispatch(db: Path, tmp_path: Path) -> None:
    store = QueueStore(db)
    hive = HiveMind(db)

    for agent in ("comms", "comms", "ops"):
        await store.enqueue(Envelope(source=Source.TELEGRAM, target_agent=agent, payload="x"))

    async def ok(env: Envelope) -> None:
        return None

    disp = Dispatcher(store, poll_interval=0.01)
    for agent in ("comms", "ops"):
        disp.register(agent, ok)

    import asyncio
    task = asyncio.create_task(disp.run())
    for _ in range(50):
        if await store.pending_count() == 0:
            break
        await asyncio.sleep(0.02)
    disp.stop()
    await asyncio.wait_for(task, timeout=1)

    counts = await hive.counts_by_agent()
    assert counts == {"comms": 2, "ops": 1}
