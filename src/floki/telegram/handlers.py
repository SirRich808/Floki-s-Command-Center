from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from floki.agents import AgentRegistry
from floki.config import settings
from floki.hive import HiveMind
from floki.memory import MemoryCategory, MemoryStore
from floki.queue import Envelope, QueueStore, Source
from floki.telegram.auth import is_unlocked, lock, unlock

log = logging.getLogger(__name__)


def build_router(
    store: QueueStore,
    registry: AgentRegistry,
    hive: HiveMind,
    memory: MemoryStore | None = None,
) -> Router:
    router = Router(name="floki-telegram")

    @router.message(Command("start"))
    async def on_start(message: Message) -> None:
        await message.answer(
            "Floki online. Send `/pin <code>` to unlock the War Room.\n"
            "Once unlocked: `/dashboard` for Mission Control, or just talk to me.",
            parse_mode=None,
        )

    @router.message(Command("pin"))
    async def on_pin(message: Message, command: CommandObject) -> None:
        pin = (command.args or "").strip()
        if not pin:
            await message.answer("Usage: /pin <code>")
            return
        if unlock(message.chat.id, pin):
            await message.answer("Unlocked. War Room access granted for 30 min.")
        else:
            await message.answer("PIN rejected.")

    @router.message(Command("lock"))
    async def on_lock(message: Message) -> None:
        lock(message.chat.id)
        await message.answer("Locked.")

    @router.message(Command("dashboard"))
    async def on_dashboard(message: Message) -> None:
        if not is_unlocked(message.chat.id):
            await message.answer("Locked. `/pin <code>` first.", parse_mode=None)
            return
        url = settings().dashboard_tunnel_url or "(DASHBOARD_TUNNEL_URL not set)"
        await message.answer(f"Mission Control: {url}")

    @router.message(Command("status"))
    async def on_status(message: Message) -> None:
        if not is_unlocked(message.chat.id):
            await message.answer("Locked. `/pin <code>` first.", parse_mode=None)
            return
        pending = await store.pending_count()
        counts = await hive.counts_by_agent()
        breakdown = ", ".join(f"{a}={n}" for a, n in sorted(counts.items())) or "(no activity)"
        await message.answer(
            f"Waiting Room: {pending} pending\nHive Mind: {breakdown}",
            parse_mode=None,
        )

    @router.message(Command("memory"))
    async def on_memory(message: Message, command: CommandObject) -> None:
        if not is_unlocked(message.chat.id):
            await message.answer("Locked. `/pin <code>` first.", parse_mode=None)
            return
        if memory is None:
            await message.answer("Memory store not wired.")
            return
        agent = (command.args or "floki").strip().lower()
        if agent not in registry.names():
            await message.answer(f"Unknown agent. Options: {', '.join(registry.names())}")
            return
        items = await memory.for_agent(agent)
        if not items:
            await message.answer(f"No memories for {agent}.")
            return
        pinned = [m for m in items if m.category == MemoryCategory.PINNED]
        others = [m for m in items if m.category != MemoryCategory.PINNED]
        lines = [f"Pinned ({len(pinned)}):"]
        lines.extend(f"  • {m.content}" for m in pinned[:10])
        if others:
            lines.append(f"\nContext ({len(others)}):")
            lines.extend(f"  • [{m.category.value}] {m.content[:80]}" for m in others[:10])
        await message.answer("\n".join(lines), parse_mode=None)

    @router.message(Command("hive"))
    async def on_hive(message: Message, command: CommandObject) -> None:
        if not is_unlocked(message.chat.id):
            await message.answer("Locked. `/pin <code>` first.", parse_mode=None)
            return
        agent = (command.args or "").strip().lower() or None
        if agent and agent not in registry.names():
            await message.answer(f"Unknown agent. Options: {', '.join(registry.names())}")
            return
        events = await hive.recent(agent=agent, limit=10)
        if not events:
            await message.answer("Hive Mind: nothing recent.")
            return
        lines = [f"#{e.envelope_id or '-'} [{e.agent}] {e.event_type} — {e.created_at}" for e in events]
        await message.answer("\n".join(lines), parse_mode=None)

    @router.message()
    async def on_message(message: Message) -> None:
        if not is_unlocked(message.chat.id):
            await message.answer("Locked. `/pin <code>` first.", parse_mode=None)
            return

        text = (message.text or message.caption or "").strip()
        if not text:
            return

        agent, reason = registry.route(text)
        env = Envelope(
            source=Source.TELEGRAM,
            source_ref=str(message.chat.id),
            target_agent=agent,
            payload=text,
            routing_reason=reason,
        )
        envelope_id = await store.enqueue(env)
        log.info("enqueued envelope %s -> %s (%s)", envelope_id, agent, reason)

        await message.answer(
            f"Queued -> {agent} [{reason}] (#{envelope_id})",
            parse_mode=None,
        )

    return router
