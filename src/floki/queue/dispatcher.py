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

    Backoff:
      Failed-but-retryable envelopes are scheduled with exponential backoff
      (base * 2^(attempts-1), capped at backoff_max). Set base=0 to disable
      (useful in tests).
    """

    def __init__(
        self,
        store: QueueStore,
        poll_interval: float = 0.25,
        max_retries: int = 3,
        backoff_base: float = 2.0,
        backoff_max: float = 60.0,
    ):
        self.store = store
        self.poll_interval = poll_interval
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max
        self._handlers: dict[str, AgentHandler] = {}
        self._global_lock = asyncio.Lock()
        self._stopped = asyncio.Event()

    def register(self, agent_name: str, handler: AgentHandler) -> None:
        self._handlers[agent_name] = handler

    async def run(self) -> None:
        log.info("dispatcher starting (poll=%.2fs, max_retries=%d)", self.poll_interval, self.max_retries)
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
        log.info("dispatcher stopped")

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
            retries_used = env.attempts - 1
            requeue = retries_used < self.max_retries
            delay = self._backoff_for(env.attempts) if requeue else None
            log.exception(
                "delivery failed for envelope %s (requeue=%s, delay=%ss)",
                env.id, requeue, delay,
            )
            await self.store.mark_failed(
                env.id or 0, str(e), requeue=requeue, retry_after_seconds=delay,
            )
            return

        await self.store.mark_delivered(env.id or 0)
        log.info("delivered envelope %s -> %s", env.id, env.target_agent)

    def _backoff_for(self, attempts: int) -> float:
        if self.backoff_base <= 0:
            return 0.0
        return min(self.backoff_base * (2 ** max(0, attempts - 1)), self.backoff_max)

    def stop(self) -> None:
        self._stopped.set()
