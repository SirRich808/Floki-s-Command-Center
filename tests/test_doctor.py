from __future__ import annotations

from pathlib import Path

import pytest

from floki.doctor import Level, _check_agents, _check_db, _check_settings
from floki.queue import QueueStore
from floki.memory import MemoryStore
from floki.security import hash_pin


@pytest.fixture
def reset_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    from floki.config import settings as _settings
    monkeypatch.setenv("BOT_TOKEN", "real-token")
    monkeypatch.setenv("ALLOWED_CHAT_IDS", "111,222")
    monkeypatch.setenv("PIN_HASH", hash_pin("4242"))
    _settings.cache_clear()


async def test_settings_check_pass(reset_settings: None) -> None:
    results = await _check_settings()
    levels = [r.level for r in results]
    assert Level.ERR not in levels
    assert any(r.label == "BOT_TOKEN set" for r in results)


async def test_settings_check_flags_missing_pin(monkeypatch: pytest.MonkeyPatch) -> None:
    from floki.config import settings as _settings
    monkeypatch.setenv("BOT_TOKEN", "real-token")
    monkeypatch.setenv("ALLOWED_CHAT_IDS", "111")
    monkeypatch.setenv("PIN_HASH", "")
    _settings.cache_clear()
    results = await _check_settings()
    err_labels = [r.label for r in results if r.level == Level.ERR]
    assert "PIN_HASH" in err_labels


async def test_db_check_reports_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from floki.config import settings as _settings
    monkeypatch.setenv("BOT_TOKEN", "x")
    monkeypatch.setenv("ALLOWED_CHAT_IDS", "1")
    monkeypatch.setenv("PIN_HASH", "x")
    monkeypatch.setenv("QUEUE_DB_PATH", str(tmp_path / "nope.db"))
    _settings.cache_clear()
    results = await _check_db()
    assert results[0].level == Level.ERR


async def test_db_check_reports_full_schema(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db = tmp_path / "q.db"
    await QueueStore(db).init()
    await MemoryStore(db).init()
    from floki.config import settings as _settings
    monkeypatch.setenv("BOT_TOKEN", "x")
    monkeypatch.setenv("ALLOWED_CHAT_IDS", "1")
    monkeypatch.setenv("PIN_HASH", "x")
    monkeypatch.setenv("QUEUE_DB_PATH", str(db))
    _settings.cache_clear()
    results = await _check_db()
    assert results[0].level == Level.OK


def test_agents_check_lists_them() -> None:
    results = _check_agents()
    assert results[0].level == Level.OK
    assert "floki" in results[0].detail
