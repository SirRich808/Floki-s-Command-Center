from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from floki.agents import AgentRegistry
from floki.dashboard import create_app
from floki.dashboard.auth import create_session, SESSION_COOKIE
from floki.hive import HiveMind
from floki.queue import QueueStore
from floki.security import hash_pin


@pytest.fixture
async def wired(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db = tmp_path / "q.db"
    store = QueueStore(db)
    await store.init()
    registry = AgentRegistry()
    hive = HiveMind(db)

    # Isolate settings() cache with a known PIN + WS secret.
    from floki.config import settings as _settings
    _settings.cache_clear()
    monkeypatch.setenv("BOT_TOKEN", "dummy")
    monkeypatch.setenv("ALLOWED_CHAT_IDS", "1")
    monkeypatch.setenv("PIN_HASH", hash_pin("4242"))
    monkeypatch.setenv("PIPECAT_WS_SECRET", "ws-secret-xyz")
    monkeypatch.setenv("QUEUE_DB_PATH", str(db))
    _settings.cache_clear()

    app = create_app(store, registry, hive)
    client = TestClient(app)
    try:
        yield store, registry, hive, client
    finally:
        client.close()
        _settings.cache_clear()


def _auth(client: TestClient) -> None:
    token = create_session()
    client.cookies.set(SESSION_COOKIE, token)


async def test_index_unauthed_shows_login(wired) -> None:
    _, _, _, client = wired
    r = client.get("/")
    assert r.status_code == 200
    assert "FLOKI // WAR ROOM" in r.text


async def test_login_success_sets_cookie_and_redirects(wired) -> None:
    _, _, _, client = wired
    r = client.post("/login", data={"pin": "4242"}, follow_redirects=False)
    assert r.status_code == 303
    assert SESSION_COOKIE in r.cookies


async def test_login_rejects_bad_pin(wired) -> None:
    _, _, _, client = wired
    r = client.post("/login", data={"pin": "wrong"}, follow_redirects=False)
    assert r.status_code == 401


async def test_api_status_requires_auth(wired) -> None:
    _, _, _, client = wired
    r = client.get("/api/status")
    assert r.status_code == 401


async def test_api_tasks_enqueues_and_routes(wired) -> None:
    store, _, _, client = wired
    _auth(client)
    r = client.post("/api/tasks", json={"payload": "Comms, draft a reply"})
    assert r.status_code == 200
    body = r.json()
    assert body["agent"] == "comms"
    assert body["routing_reason"].startswith("prefix:")
    assert body["envelope_id"] > 0
    assert await store.pending_count() == 1


async def test_voice_route_accepts_ws_secret_without_cookie(wired) -> None:
    store, _, _, client = wired
    r = client.post(
        "/api/voice/route?key=ws-secret-xyz",
        json={"transcript": "log expense $25 coffee", "enqueue": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["agent"] == "ops"  # matches logic rule
    assert body["routing_reason"].startswith("logic:")
    assert await store.pending_count() == 1


async def test_voice_route_rejects_missing_auth(wired) -> None:
    _, _, _, client = wired
    r = client.post(
        "/api/voice/route",
        json={"transcript": "hello", "enqueue": False},
    )
    assert r.status_code == 401


async def test_pipecat_ws_round_trip(wired) -> None:
    store, _, _, client = wired
    with client.websocket_connect("/ws/pipecat?key=ws-secret-xyz") as ws:
        ws.send_text(json.dumps({"transcript": "Ops: log expense $5 lunch"}))
        msg = ws.receive_json()
        assert msg["agent"] == "ops"
        assert msg["routing_reason"].startswith("prefix:")
        assert "envelope_id" in msg
    assert await store.pending_count() == 1


async def test_pipecat_ws_rejects_bad_key(wired) -> None:
    _, _, _, client = wired
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/pipecat?key=nope"):
            pass
