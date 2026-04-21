from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, Form, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel

from floki.agents import AgentRegistry
from floki.config import settings
from floki.dashboard.auth import (
    SESSION_COOKIE,
    SESSION_TTL,
    create_session,
    drop_session,
    is_valid_session,
    require_session,
    require_session_or_ws_secret,
    verify_pin_attempt,
)
from floki.dashboard.templates import LOGIN_HTML, dashboard_html
from floki.hive import HiveMind
from floki.memory import MemoryStore
from floki.queue import Envelope, QueueStore, Source

log = logging.getLogger(__name__)


class TaskIn(BaseModel):
    payload: str
    source: Source = Source.DASHBOARD


class VoiceIn(BaseModel):
    transcript: str
    enqueue: bool = True


def create_app(
    store: QueueStore,
    registry: AgentRegistry,
    hive: HiveMind,
    memory: MemoryStore | None = None,
) -> FastAPI:
    app = FastAPI(title="Floki Command Center", version="0.1.0")

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> Response:
        token = request.cookies.get(SESSION_COOKIE)
        if not is_valid_session(token):
            return HTMLResponse(LOGIN_HTML.replace("__ERR__", ""))
        return HTMLResponse(dashboard_html(settings().daily_room_url))

    @app.post("/login", response_class=HTMLResponse)
    async def login(pin: str = Form(...)) -> Response:
        if not verify_pin_attempt(pin):
            return HTMLResponse(LOGIN_HTML.replace("__ERR__", "PIN rejected."), status_code=401)
        token = create_session()
        resp = RedirectResponse(url="/", status_code=303)
        resp.set_cookie(
            SESSION_COOKIE,
            token,
            max_age=SESSION_TTL,
            httponly=True,
            samesite="lax",
        )
        return resp

    @app.post("/logout")
    async def logout(request: Request) -> Response:
        drop_session(request.cookies.get(SESSION_COOKIE))
        resp = RedirectResponse(url="/", status_code=303)
        resp.delete_cookie(SESSION_COOKIE)
        return resp

    @app.get("/api/status", dependencies=[Depends(require_session)])
    async def api_status() -> dict:
        pending = await store.pending_count()
        counts = await hive.counts_by_agent()
        return {
            "pending": pending,
            "counts": counts,
            "agents": [
                {"name": a.name, "role": a.role, "description": a.description}
                for a in registry.agents.values()
            ],
        }

    @app.get("/api/hive", dependencies=[Depends(require_session)])
    async def api_hive(agent: str | None = None, limit: int = 20) -> dict:
        if agent and agent not in registry.names():
            raise HTTPException(404, f"unknown agent '{agent}'")
        limit = max(1, min(limit, 200))
        events = await hive.recent(agent=agent, limit=limit)
        return {
            "events": [
                {
                    "id": e.id,
                    "envelope_id": e.envelope_id,
                    "agent": e.agent,
                    "event_type": e.event_type,
                    "detail": e.detail,
                    "created_at": e.created_at,
                }
                for e in events
            ]
        }

    @app.get("/api/memory", dependencies=[Depends(require_session)])
    async def api_memory(agent: str = "floki", limit: int = 50) -> dict:
        if memory is None:
            return {"counts": {}, "items": []}
        if agent not in registry.names():
            raise HTTPException(404, f"unknown agent '{agent}'")
        items = await memory.for_agent(agent)
        counts = await memory.counts_by_category()
        return {
            "counts": counts,
            "items": [
                {
                    "id": m.id,
                    "category": m.category.value,
                    "scope_agent": m.scope_agent,
                    "content": m.content,
                    "created_at": m.created_at,
                }
                for m in items[:limit]
            ],
        }

    @app.post("/api/tasks", dependencies=[Depends(require_session)])
    async def api_create_task(task: TaskIn) -> dict:
        """Task auto-assigner (Phase 4 dashboard surface).

        Current implementation reuses the router for deterministic assignment.
        A future Gemini-backed classifier plugs in here without changing the
        HTTP contract.
        """
        agent, reason = registry.route(task.payload)
        env = Envelope(
            source=task.source,
            target_agent=agent,
            payload=task.payload,
            routing_reason=reason,
        )
        envelope_id = await store.enqueue(env)
        return {"envelope_id": envelope_id, "agent": agent, "routing_reason": reason}

    @app.post("/api/voice/route")
    async def api_voice_route(
        request: Request,
        payload: VoiceIn,
        key: str | None = None,
    ) -> JSONResponse:
        """Pipecat calls this per transcript. Auth via session cookie OR PIPECAT_WS_SECRET."""
        require_session_or_ws_secret(request, key)
        agent, reason = registry.route(payload.transcript)
        body: dict = {"agent": agent, "routing_reason": reason}
        if payload.enqueue:
            env = Envelope(
                source=Source.VOICE,
                target_agent=agent,
                payload=payload.transcript,
                routing_reason=reason,
            )
            body["envelope_id"] = await store.enqueue(env)
        return JSONResponse(body)

    @app.websocket("/ws/pipecat")
    async def ws_pipecat(ws: WebSocket, key: str | None = None) -> None:
        """Long-lived router WS for Pipecat.

        Protocol (JSON):
          in:  {"transcript": "Comms, draft this", "enqueue": true}
          out: {"agent": "comms", "routing_reason": "prefix:comms", "envelope_id": 42}
        """
        expected = settings().pipecat_ws_secret
        if expected and (not key or key != expected):
            await ws.close(code=4401)
            return
        await ws.accept()
        try:
            while True:
                msg = await ws.receive_json()
                transcript = (msg.get("transcript") or "").strip()
                if not transcript:
                    await ws.send_json({"error": "empty transcript"})
                    continue
                agent, reason = registry.route(transcript)
                body: dict = {"agent": agent, "routing_reason": reason}
                if msg.get("enqueue", True):
                    env = Envelope(
                        source=Source.VOICE,
                        target_agent=agent,
                        payload=transcript,
                        routing_reason=reason,
                    )
                    body["envelope_id"] = await store.enqueue(env)
                await ws.send_json(body)
        except WebSocketDisconnect:
            return

    return app
