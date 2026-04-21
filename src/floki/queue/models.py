from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Source(str, Enum):
    TELEGRAM = "telegram"
    CRON = "cron"
    VOICE = "voice"
    DASHBOARD = "dashboard"
    AGENT = "agent"


class MessageStatus(str, Enum):
    QUEUED = "queued"
    PUSHING = "pushing"
    DELIVERED = "delivered"
    FAILED = "failed"


class Envelope(BaseModel):
    """A single unit of work moving through the Waiting Room."""

    id: int | None = None
    source: Source
    source_ref: str | None = None
    target_agent: str
    payload: str
    routing_reason: str = "default"
    priority: int = 100
    status: MessageStatus = MessageStatus.QUEUED
    attempts: int = 0
    last_error: str | None = None
    created_at: str | None = None
    claimed_at: str | None = None
    delivered_at: str | None = None

    extra: dict = Field(default_factory=dict, exclude=True)
