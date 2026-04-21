"""Initialize the Waiting Room SQLite database."""
from __future__ import annotations

import asyncio
import logging

from floki.config import settings
from floki.queue import QueueStore


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = settings()
    store = QueueStore(cfg.queue_db_path)
    await store.init()
    print(f"initialized: {cfg.queue_db_path}")


if __name__ == "__main__":
    asyncio.run(main())
