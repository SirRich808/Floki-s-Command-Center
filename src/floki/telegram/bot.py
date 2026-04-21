from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher

from floki.agents import AgentRegistry
from floki.config import settings
from floki.queue import QueueStore
from floki.telegram.auth import ChatIdAllowlistMiddleware
from floki.telegram.handlers import build_router

log = logging.getLogger(__name__)


async def run_bot() -> None:
    cfg = settings()
    store = QueueStore(cfg.queue_db_path)
    await store.init()

    registry = AgentRegistry()

    bot = Bot(token=cfg.bot_token)
    dp = Dispatcher()
    dp.update.middleware(ChatIdAllowlistMiddleware())
    dp.include_router(build_router(store, registry))

    log.info(
        "telegram bot starting — allowed_chat_ids=%s agents=%s",
        cfg.allowed_chat_ids,
        registry.names(),
    )
    await dp.start_polling(bot, handle_signals=True)
