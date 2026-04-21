from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MemoryCategory(str, Enum):
    PINNED = "pinned"       # persists forever across all agents
    DECAYING = "decaying"   # fades after `decay_days`
    INSIGHT = "insight"     # AI-deduced preference / observation


@dataclass
class MemoryDraft:
    """What a Washer produces before persistence."""
    category: MemoryCategory
    content: str
    scope_agent: str | None = None
    decay_days: int | None = None


@dataclass
class Memory:
    id: int
    category: MemoryCategory
    scope_agent: str | None
    content: str
    source_envelope: int | None
    decay_days: int | None
    created_at: str
