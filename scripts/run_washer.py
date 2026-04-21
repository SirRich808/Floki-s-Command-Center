"""Washing Machine loop.

Default Washer is the heuristic one — regex-based pinned/decaying extraction.
Swap in a GeminiWasher by subclassing floki.memory.Washer and constructing it
in build_washer() below.
"""
from __future__ import annotations

import asyncio
import logging

from floki.config import settings
from floki.memory import HeuristicWasher, MemoryStore, Washer
from floki.memory.washer import run_wash_pass

log = logging.getLogger(__name__)


def build_washer() -> Washer:
    return HeuristicWasher()


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    cfg = settings()
    store = MemoryStore(cfg.queue_db_path)
    await store.init()

    washer = build_washer()
    log.info("washer running (interval=%ss, class=%s)", cfg.washer_interval, type(washer).__name__)

    while True:
        persisted = await run_wash_pass(store, washer)
        pruned = await store.prune_decayed()
        if persisted or pruned:
            log.info("pass done: +%d memories, -%d decayed", persisted, pruned)
        await asyncio.sleep(cfg.washer_interval)


if __name__ == "__main__":
    asyncio.run(main())
