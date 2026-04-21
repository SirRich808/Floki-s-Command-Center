from __future__ import annotations

import argparse
import asyncio
import json
import sys
from io import StringIO
from pathlib import Path

import pytest

from floki.cli import _cmd_brief, _cmd_hive, _cmd_memory, _cmd_queue
from floki.hive import HiveMind
from floki.memory import MemoryCategory, MemoryDraft, MemoryStore
from floki.queue import Envelope, QueueStore, Source


@pytest.fixture
async def wired_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db = tmp_path / "q.db"
    await QueueStore(db).init()
    await MemoryStore(db).init()

    from floki.config import settings as _settings
    monkeypatch.setenv("BOT_TOKEN", "dummy")
    monkeypatch.setenv("ALLOWED_CHAT_IDS", "1")
    monkeypatch.setenv("QUEUE_DB_PATH", str(db))
    _settings.cache_clear()
    return db


async def test_cli_queue_json(wired_db: Path, capsys: pytest.CaptureFixture[str]) -> None:
    store = QueueStore(wired_db)
    await store.enqueue(Envelope(source=Source.TELEGRAM, target_agent="ops", payload="x"))

    await _cmd_queue(argparse.Namespace(json=True))
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["pending"] == 1


async def test_cli_hive_text(wired_db: Path, capsys: pytest.CaptureFixture[str]) -> None:
    hive = HiveMind(wired_db)
    await hive.record("comms", "delivered", envelope_id=1, detail="drafted")

    await _cmd_hive(argparse.Namespace(agent=None, limit=10, json=False))
    out = capsys.readouterr().out
    assert "comms" in out and "delivered" in out


async def test_cli_memory_unknown_agent_returns_error(
    wired_db: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = await _cmd_memory(argparse.Namespace(agent="not-a-real-agent", json=False))
    assert rc == 2


async def test_cli_brief_writes_file(
    wired_db: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = MemoryStore(wired_db)
    await store.insert(MemoryDraft(category=MemoryCategory.PINNED, content="User is Richard."))

    out = tmp_path / "ops.md"
    rc = await _cmd_brief(argparse.Namespace(agent="ops", out=out))
    assert rc == 0
    text = out.read_text()
    assert "User is Richard." in text
    assert "ops" in text
