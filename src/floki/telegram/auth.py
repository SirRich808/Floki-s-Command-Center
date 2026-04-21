from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from floki.config import settings
from floki.security import verify_pin

log = logging.getLogger(__name__)

# In-memory session: chat_id -> unlock expiry (epoch seconds). War Room access is
# rate-limited by time rather than persisted, so a restart re-requires PIN entry.
_UNLOCKED: dict[int, float] = {}
_UNLOCK_TTL = 60 * 30  # 30 min


def is_unlocked(chat_id: int) -> bool:
    exp = _UNLOCKED.get(chat_id)
    return bool(exp and exp > time.time())


def unlock(chat_id: int, pin: str) -> bool:
    if not verify_pin(pin, settings().pin_hash):
        return False
    _UNLOCKED[chat_id] = time.time() + _UNLOCK_TTL
    return True


def lock(chat_id: int) -> None:
    _UNLOCKED.pop(chat_id, None)


class ChatIdAllowlistMiddleware(BaseMiddleware):
    """Silently drop updates from unauthorized chat IDs.

    Per the architecture: unauthorized IDs must not be acknowledged in any way.
    No error message, no logging at INFO — the sender cannot learn the bot exists.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict], Awaitable[object]],
        event: TelegramObject,
        data: dict,
    ) -> object | None:
        allowed = set(settings().allowed_chat_ids)
        if not allowed:
            log.error("ALLOWED_CHAT_IDS empty — refusing to process updates (set this in .env)")
            return None

        chat_id = _extract_chat_id(event)
        if chat_id is None or chat_id not in allowed:
            log.debug("dropped update from chat_id=%s", chat_id)
            return None

        return await handler(event, data)


def _extract_chat_id(event: TelegramObject) -> int | None:
    if isinstance(event, Update):
        if event.message and event.message.chat:
            return event.message.chat.id
        if event.callback_query and event.callback_query.message:
            return event.callback_query.message.chat.id
        if event.edited_message and event.edited_message.chat:
            return event.edited_message.chat.id
    chat = getattr(event, "chat", None)
    return chat.id if chat else None
