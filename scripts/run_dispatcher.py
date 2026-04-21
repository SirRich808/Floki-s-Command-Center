"""Run the single-consumer dispatcher.

Uses TmuxAdapter per agents.yaml by default. Override via FLOKI_ADAPTER=stub
for dry-runs without tmux installed.
"""
from __future__ import annotations

import asyncio
import logging
import os

from floki.agents import AdapterRegistry, AgentRegistry, StubAdapter
from floki.config import settings
from floki.queue import QueueStore
from floki.queue.dispatcher import Dispatcher

log = logging.getLogger(__name__)


def build_adapters(agents: AgentRegistry) -> AdapterRegistry:
    mode = os.getenv("FLOKI_ADAPTER", "tmux").lower()
    if mode == "stub":
        reg = AdapterRegistry(agents)
        for name in agents.names():
            reg.set(name, StubAdapter(name))
        return reg
    return AdapterRegistry.tmux_from_registry(agents)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    cfg = settings()
    store = QueueStore(cfg.queue_db_path)
    await store.init()

    agents = AgentRegistry()
    adapters = build_adapters(agents)

    dispatcher = Dispatcher(
        store,
        poll_interval=cfg.dispatch_poll_interval,
        max_retries=cfg.dispatch_max_retries,
    )
    for name in agents.names():
        adapter = adapters.get(name)
        dispatcher.register(name, adapter.deliver)

    log.info("dispatcher ready (mode=%s, agents=%s)", os.getenv("FLOKI_ADAPTER", "tmux"), agents.names())
    await dispatcher.run()


if __name__ == "__main__":
    asyncio.run(main())
