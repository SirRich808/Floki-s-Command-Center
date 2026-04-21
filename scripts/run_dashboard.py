"""Run the Mission Control dashboard (FastAPI + uvicorn)."""
from __future__ import annotations

import asyncio
import logging

import uvicorn

from floki.agents import AgentRegistry
from floki.config import settings
from floki.dashboard import create_app
from floki.hive import HiveMind
from floki.memory import MemoryStore
from floki.queue import QueueStore


async def _warm_store() -> None:
    cfg = settings()
    await QueueStore(cfg.queue_db_path).init()
    await MemoryStore(cfg.queue_db_path).init()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    cfg = settings()

    # Ensure DB/schema exist before the app starts handling requests.
    asyncio.run(_warm_store())

    store = QueueStore(cfg.queue_db_path)
    registry = AgentRegistry()
    hive = HiveMind(cfg.queue_db_path)
    memory = MemoryStore(cfg.queue_db_path)
    app = create_app(store, registry, hive, memory=memory)

    uvicorn.run(
        app,
        host=cfg.dashboard_host,
        port=cfg.dashboard_port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
