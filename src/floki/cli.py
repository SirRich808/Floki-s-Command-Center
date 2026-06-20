"""Unified CLI. Installed as `floki` via pyproject.toml.

Designed to be shelled out from inside agent sessions:
  floki hive --agent ops --limit 5
  floki memory --agent comms
  floki brief comms > /tmp/comms_brief.md
  floki queue stats

All commands operate on the same SQLite file as the daemons.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from floki.agents import AgentRegistry
from floki.config import settings
from floki.hive import HiveMind
from floki.memory import MemoryInjector, MemoryStore
from floki.queue import QueueStore


async def _cmd_hive(args: argparse.Namespace) -> int:
    hive = HiveMind(settings().queue_db_path)
    events = await hive.recent(agent=args.agent, limit=args.limit)
    if args.json:
        print(json.dumps(
            [e.__dict__ for e in events],
            default=str,
            indent=2,
        ))
        return 0
    if not events:
        print("(no hive activity)")
        return 0
    for e in events:
        detail = f" — {e.detail}" if e.detail else ""
        print(f"{e.created_at}  [{e.agent}] {e.event_type} #{e.envelope_id or '-'}{detail}")
    return 0


async def _cmd_memory(args: argparse.Namespace) -> int:
    store = MemoryStore(settings().queue_db_path)
    registry = AgentRegistry()
    if args.agent not in registry.names():
        print(f"unknown agent: {args.agent}", file=sys.stderr)
        return 2
    items = await store.for_agent(args.agent)
    if args.json:
        print(json.dumps([m.__dict__ for m in items], default=str, indent=2))
        return 0
    if not items:
        print("(no memories)")
        return 0
    for m in items:
        print(f"[{m.category.value}]{f' @{m.scope_agent}' if m.scope_agent else ''}  {m.content}")
    return 0


async def _cmd_brief(args: argparse.Namespace) -> int:
    cfg = settings()
    store = MemoryStore(cfg.queue_db_path)
    registry = AgentRegistry()
    if args.agent not in registry.names():
        print(f"unknown agent: {args.agent}", file=sys.stderr)
        return 2
    injector = MemoryInjector(store, registry, obsidian_root=cfg.obsidian_root)
    md = await injector.build(args.agent)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(md)
        print(f"wrote {args.out}")
    else:
        sys.stdout.write(md)
    return 0


async def _cmd_queue(args: argparse.Namespace) -> int:
    store = QueueStore(settings().queue_db_path)
    hive = HiveMind(settings().queue_db_path)
    pending = await store.pending_count()
    counts = await hive.counts_by_agent()
    failed = await store.list_failed(limit=1000)
    if args.json:
        print(json.dumps(
            {"pending": pending, "failed": len(failed), "hive_counts": counts},
            indent=2,
        ))
    else:
        print(f"pending: {pending}")
        print(f"failed:  {len(failed)}")
        for agent, n in sorted(counts.items()):
            print(f"  {agent}: {n}")
    return 0


async def _cmd_failed(args: argparse.Namespace) -> int:
    store = QueueStore(settings().queue_db_path)
    envs = await store.list_failed(limit=args.limit)
    if args.json:
        print(json.dumps(
            [{"id": e.id, "target_agent": e.target_agent, "payload": e.payload,
              "attempts": e.attempts, "last_error": e.last_error,
              "created_at": e.created_at} for e in envs],
            indent=2,
        ))
        return 0
    if not envs:
        print("(no failed envelopes)")
        return 0
    for e in envs:
        print(f"#{e.id}  [{e.target_agent}] attempts={e.attempts}  err={e.last_error or ''}")
        print(f"    {e.payload[:120]}")
    return 0


async def _cmd_requeue(args: argparse.Namespace) -> int:
    store = QueueStore(settings().queue_db_path)
    ok = await store.requeue_failed(args.envelope_id)
    if not ok:
        print(f"#{args.envelope_id}: not found or not in failed state", file=sys.stderr)
        return 2
    print(f"#{args.envelope_id} requeued")
    return 0


async def _cmd_drop(args: argparse.Namespace) -> int:
    store = QueueStore(settings().queue_db_path)
    ok = await store.drop_envelope(args.envelope_id)
    if not ok:
        print(f"#{args.envelope_id}: not found", file=sys.stderr)
        return 2
    print(f"#{args.envelope_id} dropped")
    return 0


async def _cmd_doctor(args: argparse.Namespace) -> int:
    from floki.doctor import run as run_doctor
    return await run_doctor()


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="floki", description="Floki Command Center CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    h = sub.add_parser("hive", help="query the Hive Mind")
    h.add_argument("--agent", default=None)
    h.add_argument("--limit", type=int, default=20)
    h.add_argument("--json", action="store_true")
    h.set_defaults(func=_cmd_hive)

    m = sub.add_parser("memory", help="show memories visible to an agent")
    m.add_argument("--agent", default="floki")
    m.add_argument("--json", action="store_true")
    m.set_defaults(func=_cmd_memory)

    b = sub.add_parser("brief", help="render the agent's startup .md brief")
    b.add_argument("agent")
    from pathlib import Path
    b.add_argument("--out", type=Path, default=None, help="write to file instead of stdout")
    b.set_defaults(func=_cmd_brief)

    q = sub.add_parser("queue", help="queue + hive summary")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=_cmd_queue)

    f = sub.add_parser("failed", help="list failed envelopes")
    f.add_argument("--limit", type=int, default=50)
    f.add_argument("--json", action="store_true")
    f.set_defaults(func=_cmd_failed)

    rq = sub.add_parser("requeue", help="reset a failed envelope back to queued")
    rq.add_argument("envelope_id", type=int)
    rq.set_defaults(func=_cmd_requeue)

    dr = sub.add_parser("drop", help="delete an envelope")
    dr.add_argument("envelope_id", type=int)
    dr.set_defaults(func=_cmd_drop)

    d = sub.add_parser("doctor", help="run setup healthcheck")
    d.set_defaults(func=_cmd_doctor)

    return p


def main() -> None:
    args = _parser().parse_args()
    rc = asyncio.run(args.func(args))
    sys.exit(rc)


if __name__ == "__main__":
    main()
