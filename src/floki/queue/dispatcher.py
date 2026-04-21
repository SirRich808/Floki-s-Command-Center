from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from floki.queue.models import Envelope
from floki.queue.store import QueueStore

log = logging.getLogger(__name__)

AgentHandler = Callable[[Envelope], Awaitable[None]]


class Dispatcher:
    """Single-consumer loop. Pulls one Envelope at a time from the Waiting Room
    and pushes it to the registered agent handler.

    Collision prevention:
      * `_global_lock` ensures only one push is in flight across the whole system,
        regardless of how many inputs (Telegram, cron, voice) fire simultaneously.
      * `QueueStore.claim_next` uses BEGIN IMMEDIATE so a second dispatcher would
        still never double-claim.
    """

    def __init__(
        self,
        store: QueueStore,
        poll_interval: float = 0.25,
        max_retries: int = 3,
    ):
        self.store = store
        self.poll_interval = poll_interval
        self.max_retries = max_retries
        self._handlers: dict[str, AgentHandler] = {}
        self._global_lock = asyncio.Lock()
        self._stopped = asyncio.Event()

    def register(self, agent_name: str, handler: AgentHandler) -> None:
        self._handlers[agent_name] = handler

    async def run(self) -> None:
        log.info("dispatcher starting (poll=%.2fs)", self.poll_interval)
        while not self._stopped.is_set():
            env = await self.store.claim_next()
            if env is None:
                try:
                    await asyncio.wait_for(self._stopped.wait(), timeout=self.poll_interval)
                except asyncio.TimeoutError:
                    pass
                continue

            async with self._global_lock:
                await self._deliver(env)

    async def _deliver(self, env: Envelope) -> None:
        handler = self._handlers.get(env.target_agent)
        if handler is None:
            msg = f"no handler registered for agent '{env.target_agent}'"
            log.warning("dropping envelope %s: %s", env.id, msg)
            await self.store.mark_failed(env.id or 0, msg, requeue=False)
            return

        try:
            await handler(env)
        except Exception as e:  # noqa: BLE001 - dispatcher is the safety net
            # env.attempts was incremented to 1 on first claim, so retries_used = attempts - 1.
            requeue = (env.attempts - 1) < self.max_retries
            log.exception("delivery failed for envelope %s (requeue=%s)", env.id, requeue)
            await self.store.mark_failed(env.id or 0, str(e), requeue=requeue)
            return

        await self.store.mark_delivered(env.id or 0)
        log.info("delivered envelope %s -> %s", env.id, env.target_agent)

    def stop(self) -> None:
        self._stopped.set()
