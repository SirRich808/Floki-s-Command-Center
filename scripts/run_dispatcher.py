"""Run the single-consumer dispatcher.

In Phase 2 this stubs each agent as a log-print handler. Phase 1 wires real
terminal sessions (tmux / iTerm pipes) in as AgentHandlers.
"""
from __future__ import annotations

import asyncio
import logging

from floki.agents import AgentRegistry
from floki.config import settings
from floki.queue import QueueStore
from floki.queue.dispatcher import Dispatcher
from floki.queue.models import Envelope

log = logging.getLogger(__name__)


def _stub_handler(agent_name: str):
    async def handle(env: Envelope) -> None:
        log.info("[%s] received #%s (%s): %s", agent_name, env.id, env.routing_reason, env.payload)
        await asyncio.sleep(0)
    return handle


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    cfg = settings()
    store = QueueStore(cfg.queue_db_path)
    await store.init()

    registry = AgentRegistry()
    dispatcher = Dispatcher(
        store,
        poll_interval=cfg.dispatch_poll_interval,
        max_retries=cfg.dispatch_max_retries,
    )
    for name in registry.names():
        dispatcher.register(name, _stub_handler(name))

    await dispatcher.run()


if __name__ == "__main__":
    asyncio.run(main())
