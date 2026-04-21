from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod

from floki.memory.models import MemoryCategory, MemoryDraft
from floki.memory.store import MemoryStore

log = logging.getLogger(__name__)


class Washer(ABC):
    """Extracts MemoryDrafts from a raw user utterance.

    GeminiWasher (future) subclasses this and calls Gemini Flash for
    pinned/decaying/insight classification with full conversation context.
    The contract stays the same so the Washer can be swapped without
    touching the store or the run loop.
    """

    @abstractmethod
    async def extract(self, payload: str, target_agent: str) -> list[MemoryDraft]: ...


class HeuristicWasher(Washer):
    """Regex-based washer. Covers the 'always-pinned' facts the user will
    state in natural language and tags everything else as decaying context
    so the DB doesn't grow unbounded. Ships today; GeminiWasher can replace
    it later for nuance + insight generation.
    """

    # Each entry: (compiled regex, format-string that references captured groups, category)
    PINNED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
        (re.compile(r"(?i)\bmy name is ([A-Z][\w\-']+(?:\s+[A-Z][\w\-']+)?)"),
         "User's name: {0}."),
        (re.compile(r"(?i)\bi(?:'m| am) (\w+(?:\s+\w+)?)(?:,| from| years old)"),
         "User identity: {0}."),
        (re.compile(r"(?i)\bi live (?:in|at) ([^.!?\n]+)"),
         "User lives in {0}."),
        (re.compile(r"(?i)\bmy (?:business|company|brand) is ([^.!?\n]+)"),
         "User's business: {0}."),
        (re.compile(r"(?i)\bmy (?:wife|husband|partner|spouse) is ([A-Z][\w\-']+)"),
         "User's partner: {0}."),
        (re.compile(r"(?i)\bremember (?:that )?([^.!?\n]+)"),
         "User asked to remember: {0}."),
    ]

    DEFAULT_DECAY_DAYS = 14

    async def extract(self, payload: str, target_agent: str) -> list[MemoryDraft]:
        drafts: list[MemoryDraft] = []
        matched_any = False

        for pattern, template in self.PINNED_PATTERNS:
            for match in pattern.finditer(payload):
                matched_any = True
                content = template.format(*(g.strip() for g in match.groups()))
                drafts.append(
                    MemoryDraft(
                        category=MemoryCategory.PINNED,
                        content=content,
                        scope_agent=None,
                    )
                )

        if not matched_any and payload.strip():
            drafts.append(
                MemoryDraft(
                    category=MemoryCategory.DECAYING,
                    content=payload.strip(),
                    scope_agent=target_agent,
                    decay_days=self.DEFAULT_DECAY_DAYS,
                )
            )

        return drafts


async def run_wash_pass(
    store: MemoryStore,
    washer: Washer,
    batch: int = 100,
) -> int:
    """Process up to `batch` unwashed envelopes. Returns drafts persisted."""
    persisted = 0
    for envelope_id, payload, target_agent in await store.unwashed_envelopes(limit=batch):
        try:
            drafts = await washer.extract(payload, target_agent)
            for draft in drafts:
                await store.insert(draft, source_envelope=envelope_id)
                persisted += 1
        except Exception:  # noqa: BLE001 - washer is best-effort
            log.exception("wash failed for envelope %s", envelope_id)
        await store.mark_washed(envelope_id)
    return persisted
