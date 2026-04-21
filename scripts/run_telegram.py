"""Run the Telegram bot. Entry point for `launchd` in Phase 6."""
from __future__ import annotations

import asyncio
import logging

from floki.telegram.bot import run_bot


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
