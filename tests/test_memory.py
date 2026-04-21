from __future__ import annotations

import asyncio
import time
from pathlib import Path

import aiosqlite
import pytest

from floki.agents import AgentRegistry
from floki.memory import (
    HeuristicWasher,
    MemoryCategory,
    MemoryDraft,
    MemoryInjector,
    MemoryStore,
)
from floki.memory.washer import run_wash_pass
from floki.queue import Envelope, QueueStore, Source


@pytest.fixture
async def stores(tmp_path: Path):
    db = tmp_path / "q.db"
    q = QueueStore(db)
    await q.init()
    m = MemoryStore(db)
    await m.init()
    return q, m, db


async def test_heuristic_washer_extracts_pinned_facts() -> None:
    w = HeuristicWasher()
    drafts = await w.extract("Hi, my name is Richard and I live in Austin", "floki")
    pinned = [d for d in drafts if d.category == MemoryCategory.PINNED]
    contents = " | ".join(d.content for d in pinned)
    assert "Richard" in contents
    assert "Austin" in contents


async def test_heuristic_washer_defaults_to_decaying(stores) -> None:
    w = HeuristicWasher()
    drafts = await w.extract("need to ship the Q3 deck by Friday", "ops")
    assert len(drafts) == 1
    assert drafts[0].category == MemoryCategory.DECAYING
    assert drafts[0].scope_agent == "ops"
    assert drafts[0].decay_days == HeuristicWasher.DEFAULT_DECAY_DAYS


async def test_wash_pass_end_to_end(stores) -> None:
    q, m, _ = stores
    await q.enqueue(Envelope(source=Source.TELEGRAM, target_agent="floki",
                             payload="Remember that my business is Floki Studios"))
    await q.enqueue(Envelope(source=Source.TELEGRAM, target_agent="ops",
                             payload="log $42 for office supplies"))

    persisted = await run_wash_pass(m, HeuristicWasher())
    # "Remember that my business is X" legitimately fires two pinned patterns
    # (the business name + the remember-this intent) plus the ops decaying row.
    assert persisted >= 2

    # Running again does nothing (idempotent via washer_progress).
    assert await run_wash_pass(m, HeuristicWasher()) == 0

    counts = await m.counts_by_category()
    assert counts.get("pinned", 0) >= 1
    assert counts.get("decaying", 0) >= 1


async def test_scope_and_pinned_visibility(stores) -> None:
    _, m, _ = stores
    await m.insert(MemoryDraft(category=MemoryCategory.PINNED, content="User is Richard"))
    await m.insert(MemoryDraft(
        category=MemoryCategory.DECAYING,
        content="ops-only note",
        scope_agent="ops",
        decay_days=30,
    ))

    ops_mems = await m.for_agent("ops")
    comms_mems = await m.for_agent("comms")

    ops_content = {x.content for x in ops_mems}
    comms_content = {x.content for x in comms_mems}
    assert "User is Richard" in ops_content and "User is Richard" in comms_content
    assert "ops-only note" in ops_content
    assert "ops-only note" not in comms_content


async def test_prune_decayed_removes_expired(stores) -> None:
    _, m, db = stores
    await m.insert(MemoryDraft(
        category=MemoryCategory.DECAYING, content="stale", decay_days=1,
    ))
    # Backdate the row past its TTL.
    async with aiosqlite.connect(db) as conn:
        await conn.execute(
            "UPDATE memories SET created_at = '2000-01-01T00:00:00.000Z' WHERE content = 'stale'"
        )
        await conn.commit()

    pruned = await m.prune_decayed()
    assert pruned == 1
    assert not await m.for_agent("ops")


async def test_injector_builds_md_without_vault(stores) -> None:
    _, m, _ = stores
    await m.insert(MemoryDraft(category=MemoryCategory.PINNED, content="User is Richard."))
    await m.insert(MemoryDraft(
        category=MemoryCategory.DECAYING, content="needs Q3 deck", scope_agent="ops", decay_days=7,
    ))
    injector = MemoryInjector(m, AgentRegistry(), obsidian_root=None)
    md = await injector.build("ops")
    assert "# Floki memory brief for `ops`" in md
    assert "User is Richard." in md
    assert "needs Q3 deck" in md


async def test_injector_reads_obsidian_vault(tmp_path: Path, stores) -> None:
    _, m, _ = stores
    vault_root = tmp_path / "vaults"
    (vault_root / "Finance").mkdir(parents=True)
    (vault_root / "Finance" / "budget.md").write_text("# Q3 budget\n- AWS: $2k")
    injector = MemoryInjector(m, AgentRegistry(), obsidian_root=vault_root)
    md = await injector.build("ops")
    assert "Q3 budget" in md
    assert "AWS: $2k" in md
