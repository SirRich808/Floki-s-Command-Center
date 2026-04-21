from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from floki.queue import Envelope, QueueStore, Source
from floki.queue.dispatcher import Dispatcher
from floki.queue.models import MessageStatus


@pytest.fixture
async def store(tmp_path: Path) -> QueueStore:
    s = QueueStore(tmp_path / "q.db")
    await s.init()
    return s


async def test_enqueue_and_claim_fifo(store: QueueStore) -> None:
    for i in range(3):
        await store.enqueue(Envelope(source=Source.TELEGRAM, target_agent="comms", payload=f"m{i}"))

    first = await store.claim_next()
    second = await store.claim_next()
    third = await store.claim_next()

    assert first and first.payload == "m0"
    assert second and second.payload == "m1"
    assert third and third.payload == "m2"
    assert first.status == MessageStatus.PUSHING


async def test_claim_respects_priority(store: QueueStore) -> None:
    await store.enqueue(Envelope(source=Source.TELEGRAM, target_agent="ops", payload="low", priority=200))
    await store.enqueue(Envelope(source=Source.TELEGRAM, target_agent="ops", payload="high", priority=10))

    first = await store.claim_next()
    assert first and first.payload == "high"


async def test_dispatcher_delivers_one_at_a_time(store: QueueStore) -> None:
    """Core collision-prevention guarantee: no two handler bodies overlap."""
    in_flight = 0
    max_concurrent = 0
    seen: list[str] = []

    async def handler(env: Envelope) -> None:
        nonlocal in_flight, max_concurrent
        in_flight += 1
        max_concurrent = max(max_concurrent, in_flight)
        await asyncio.sleep(0.01)
        seen.append(env.payload)
        in_flight -= 1

    for i in range(5):
        await store.enqueue(Envelope(source=Source.CRON, target_agent="comms", payload=f"t{i}"))

    dispatcher = Dispatcher(store, poll_interval=0.01)
    dispatcher.register("comms", handler)

    task = asyncio.create_task(dispatcher.run())
    for _ in range(50):
        if len(seen) >= 5:
            break
        await asyncio.sleep(0.02)
    dispatcher.stop()
    await asyncio.wait_for(task, timeout=1)

    assert seen == ["t0", "t1", "t2", "t3", "t4"]
    assert max_concurrent == 1


async def test_dispatcher_requeues_on_failure_until_max_retries(store: QueueStore) -> None:
    attempts = 0

    async def flaky(env: Envelope) -> None:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("boom")

    await store.enqueue(Envelope(source=Source.TELEGRAM, target_agent="ops", payload="x"))
    dispatcher = Dispatcher(store, poll_interval=0.01, max_retries=2)
    dispatcher.register("ops", flaky)

    task = asyncio.create_task(dispatcher.run())
    for _ in range(100):
        if attempts >= 3 and await store.pending_count() == 0:
            break
        await asyncio.sleep(0.02)
    dispatcher.stop()
    await asyncio.wait_for(task, timeout=1)

    assert attempts == 3  # initial + 2 retries
