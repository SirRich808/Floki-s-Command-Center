"""Healthcheck. Run via `floki doctor`.

Exits 0 if no errors, 1 if any check failed. Warnings don't fail the run.
"""
from __future__ import annotations

import asyncio
import shutil
import sys
from dataclasses import dataclass
from enum import Enum

import aiosqlite

from floki.config import agents_config, settings


class Level(str, Enum):
    OK = "ok"
    WARN = "warn"
    ERR = "err"


@dataclass
class Result:
    level: Level
    label: str
    detail: str = ""


_GLYPH = {Level.OK: "✓", Level.WARN: "⚠", Level.ERR: "✗"}
_COLOR = {Level.OK: "\033[32m", Level.WARN: "\033[33m", Level.ERR: "\033[31m"}
_RESET = "\033[0m"


def _emit(r: Result, use_color: bool) -> None:
    glyph = _GLYPH[r.level]
    if use_color:
        glyph = f"{_COLOR[r.level]}{glyph}{_RESET}"
    line = f" {glyph} {r.label}"
    if r.detail:
        line += f"  — {r.detail}"
    print(line)


async def _check_settings() -> list[Result]:
    out: list[Result] = []
    try:
        cfg = settings()
    except Exception as e:  # noqa: BLE001
        return [Result(Level.ERR, ".env load", str(e))]

    out.append(Result(Level.OK, ".env loaded"))

    if not cfg.bot_token or cfg.bot_token.startswith("123456:"):
        out.append(Result(Level.ERR, "BOT_TOKEN", "not set (or still the placeholder)"))
    else:
        out.append(Result(Level.OK, "BOT_TOKEN set"))

    if not cfg.allowed_chat_ids:
        out.append(Result(Level.ERR, "ALLOWED_CHAT_IDS", "empty — bot will drop everything"))
    else:
        out.append(Result(Level.OK, f"ALLOWED_CHAT_IDS: {len(cfg.allowed_chat_ids)} id(s)"))

    if not cfg.pin_hash:
        out.append(Result(Level.ERR, "PIN_HASH", "not set — War Room is wide open"))
    else:
        out.append(Result(Level.OK, "PIN_HASH set"))

    if not cfg.pipecat_ws_secret:
        out.append(Result(Level.WARN, "PIPECAT_WS_SECRET", "not set — voice WS will require PIN cookie only"))
    else:
        out.append(Result(Level.OK, "PIPECAT_WS_SECRET set"))

    if not cfg.daily_room_url:
        out.append(Result(Level.WARN, "DAILY_ROOM_URL", "not set — dashboard won't show War Room button"))
    else:
        out.append(Result(Level.OK, "DAILY_ROOM_URL set"))

    if cfg.obsidian_root is None:
        out.append(Result(Level.WARN, "OBSIDIAN_ROOT", "not set — agent briefs won't include vault content"))
    elif not cfg.obsidian_root.exists():
        out.append(Result(Level.WARN, "OBSIDIAN_ROOT", f"path missing: {cfg.obsidian_root}"))
    else:
        out.append(Result(Level.OK, f"OBSIDIAN_ROOT: {cfg.obsidian_root}"))

    return out


async def _check_db() -> list[Result]:
    out: list[Result] = []
    cfg = settings()
    path = cfg.queue_db_path
    if not path.exists():
        return [Result(Level.ERR, "SQLite DB", f"missing at {path} — run scripts/init_db.py")]

    expected = {"envelopes", "hive_events", "memories", "washer_progress"}
    try:
        async with aiosqlite.connect(path) as db:
            cur = await db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            rows = await cur.fetchall()
        found = {r[0] for r in rows}
        missing = expected - found
        if missing:
            out.append(Result(Level.ERR, "SQLite schema", f"missing tables: {sorted(missing)}"))
        else:
            out.append(Result(Level.OK, f"SQLite schema: {len(expected)} tables present"))
    except Exception as e:  # noqa: BLE001
        out.append(Result(Level.ERR, "SQLite DB", f"open failed: {e}"))
    return out


def _check_agents() -> list[Result]:
    out: list[Result] = []
    try:
        cfg = agents_config()
    except Exception as e:  # noqa: BLE001
        return [Result(Level.ERR, "agents.yaml", str(e))]
    names = [a["name"] for a in cfg.get("agents", [])]
    if not names:
        return [Result(Level.ERR, "agents.yaml", "no agents configured")]
    out.append(Result(Level.OK, f"{len(names)} agents configured", ", ".join(names)))
    return out


def _check_tmux() -> list[Result]:
    out: list[Result] = []
    if shutil.which("tmux") is None:
        out.append(Result(Level.WARN, "tmux", "not installed — TmuxAdapter will fail (use FLOKI_ADAPTER=stub)"))
        return out
    out.append(Result(Level.OK, "tmux installed"))

    import subprocess
    cfg = agents_config()
    for spec in cfg.get("agents", []):
        session = spec["terminal_session"]
        rc = subprocess.run(
            ["tmux", "has-session", "-t", session],
            capture_output=True,
        ).returncode
        if rc != 0:
            out.append(Result(Level.WARN, f"tmux session {session}", "not running — ./scripts/start_sessions.sh"))
    return out


async def run() -> int:
    results: list[Result] = []
    results.extend(await _check_settings())
    results.extend(await _check_db())
    results.extend(_check_agents())
    results.extend(_check_tmux())

    use_color = sys.stdout.isatty()
    for r in results:
        _emit(r, use_color)

    errs = sum(1 for r in results if r.level == Level.ERR)
    warns = sum(1 for r in results if r.level == Level.WARN)
    print()
    print(f"→ {warns} warnings, {errs} errors")
    return 1 if errs else 0


def main() -> None:
    sys.exit(asyncio.run(run()))


if __name__ == "__main__":
    main()
