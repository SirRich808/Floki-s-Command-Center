from __future__ import annotations

import asyncio
import time
from pathlib import Path

import aiosqlite
import pytest

from floki.queue import Envelope, QueueStore, Source
from floki.queue.dispatcher import Dispatcher
from floki.queue.models import MessageStatus


@pytest.fixture
async def store(tmp_path: Path) -> QueueStore:
    s = QueueStore(tmp_path / "q.db")
    await s.init()
    return s


async def test_retry_after_delays_claim(store: QueueStore) -> None:
    await store.enqueue(Envelope(source=Source.TELEGRAM, target_agent="ops", payload="x"))
    first = await store.claim_next()
    assert first is not None
    # Simulate failure with a backoff window.
    await store.mark_failed(first.id or 0, "boom", requeue=True, retry_after_seconds=10)

    # Should NOT be claimable immediately — retry_after is in the future.
    second = await store.claim_next()
    assert second is None


async def test_retry_after_unblocks_after_window(store: QueueStore, tmp_path: Path) -> None:
    await store.enqueue(Envelope(source=Source.TELEGRAM, target_agent="ops", payload="x"))
    first = await store.claim_next()
    await store.mark_failed(first.id or 0, "boom", requeue=True, retry_after_seconds=10)

    # Backdate retry_after past now so claim_next sees it as ready.
    async with aiosqlite.connect(tmp_path / "q.db") as db:
        await db.execute(
            "UPDATE envelopes SET retry_after = '2000-01-01T00:00:00.000Z' WHERE id = ?",
            (first.id,),
        )
        await db.commit()

    again = await store.claim_next()
    assert again is not None and again.id == first.id


async def test_dispatcher_uses_backoff(store: QueueStore) -> None:
    """With backoff_base>0 a failing handler should be delayed between retries."""
    timestamps: list[float] = []

    async def flaky(env: Envelope) -> None:
        timestamps.append(time.monotonic())
        raise RuntimeError("nope")

    await store.enqueue(Envelope(source=Source.CRON, target_agent="ops", payload="x"))

    # backoff_base=0.1s, max_retries=2 → expect ~0.1s gap between attempt 1 and 2.
    disp = Dispatcher(store, poll_interval=0.01, max_retries=2, backoff_base=0.1, backoff_max=1.0)
    disp.register("ops", flaky)

    task = asyncio.create_task(disp.run())
    for _ in range(200):
        if len(timestamps) >= 3 or await store.pending_count() == 0:
            break
        await asyncio.sleep(0.02)
    disp.stop()
    await asyncio.wait_for(task, timeout=2)

    # Attempts: 1, 2, 3 → after attempt 1, delay = base * 2^0 = 0.1. After attempt 2, base * 2^1 = 0.2.
    # So timestamps[1] - timestamps[0] >= ~0.1, timestamps[2] - timestamps[1] >= ~0.2.
    assert len(timestamps) >= 3
    assert (timestamps[1] - timestamps[0]) >= 0.08
    assert (timestamps[2] - timestamps[1]) >= 0.18


async def test_list_requeue_drop_failed(store: QueueStore) -> None:
    await store.enqueue(Envelope(source=Source.TELEGRAM, target_agent="ops", payload="dead"))
    env = await store.claim_next()
    assert env is not None
    await store.mark_failed(env.id or 0, "permanent", requeue=False)

    failed = await store.list_failed()
    assert len(failed) == 1
    assert failed[0].status == MessageStatus.FAILED
    assert failed[0].last_error == "permanent"

    assert await store.requeue_failed(env.id or 0) is True
    again = await store.claim_next()
    assert again is not None and again.id == env.id
    # Requeue should have reset attempts.
    assert again.attempts == 1

    # Drop it.
    assert await store.drop_envelope(env.id or 0) is True
    assert await store.drop_envelope(env.id or 0) is False


async def test_requeue_only_matches_failed_status(store: QueueStore) -> None:
    await store.enqueue(Envelope(source=Source.TELEGRAM, target_agent="ops", payload="x"))
    env = await store.claim_next()
    # status is now 'pushing' — requeue_failed should NOT touch it.
    assert await store.requeue_failed(env.id or 0) is False
