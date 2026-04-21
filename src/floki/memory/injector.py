from __future__ import annotations

from pathlib import Path

from floki.agents import AgentRegistry
from floki.memory.models import MemoryCategory
from floki.memory.store import MemoryStore


class MemoryInjector:
    """Builds the .md blob that gets stuffed at the top of an agent's session.

    Layers (top → bottom in the output file):
      1. Pinned memories   (global truths: name, address, business)
      2. Insights          (AI-deduced preferences)
      3. Agent-scoped decaying memories (recent context)
      4. Obsidian vault for this agent (Comms → Communications/, Ops → Finance/, …)
    """

    def __init__(
        self,
        store: MemoryStore,
        registry: AgentRegistry,
        obsidian_root: Path | None,
    ):
        self.store = store
        self.registry = registry
        self.obsidian_root = Path(obsidian_root) if obsidian_root else None

    async def build(self, agent_name: str) -> str:
        memories = await self.store.for_agent(agent_name)
        pinned = [m for m in memories if m.category == MemoryCategory.PINNED]
        insights = [m for m in memories if m.category == MemoryCategory.INSIGHT]
        decaying = [m for m in memories if m.category == MemoryCategory.DECAYING]

        parts: list[str] = [f"# Floki memory brief for `{agent_name}`", ""]

        if pinned:
            parts.append("## Pinned facts")
            parts.extend(f"- {m.content}" for m in pinned)
            parts.append("")

        if insights:
            parts.append("## Insights")
            parts.extend(f"- {m.content}" for m in insights)
            parts.append("")

        if decaying:
            parts.append("## Recent context")
            parts.extend(f"- {m.content}" for m in decaying[:25])
            parts.append("")

        vault_md = self._read_vault(agent_name)
        if vault_md:
            parts.append("## Obsidian vault")
            parts.append(vault_md)

        return "\n".join(parts).strip() + "\n"

    def _read_vault(self, agent_name: str) -> str:
        if not self.obsidian_root or not self.obsidian_root.exists():
            return ""
        spec = self.registry.agents.get(agent_name)
        if not spec or not spec.obsidian_vault:
            return ""
        vault = self.obsidian_root / spec.obsidian_vault
        if not vault.exists():
            return ""

        chunks: list[str] = []
        for md in sorted(vault.rglob("*.md")):
            try:
                text = md.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if not text:
                continue
            rel = md.relative_to(vault)
            chunks.append(f"### {rel}\n\n{text}")
        return "\n\n".join(chunks)
