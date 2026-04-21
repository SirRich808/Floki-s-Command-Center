from __future__ import annotations

from dataclasses import dataclass

from floki.config import agents_config


@dataclass(frozen=True)
class AgentSpec:
    name: str
    role: str
    description: str
    prefix_triggers: tuple[str, ...]
    obsidian_vault: str | None
    terminal_session: str


class AgentRegistry:
    """Routing metadata loaded from config/agents.yaml.

    Consumed by:
      - Telegram handlers (prefix routing)
      - Pipecat (Phase 5 — same prefix_triggers feed the voice router)
      - Task auto-assigner (Phase 4)
    """

    def __init__(self) -> None:
        cfg = agents_config()
        self.agents: dict[str, AgentSpec] = {
            a["name"]: AgentSpec(
                name=a["name"],
                role=a["role"],
                description=a["description"],
                prefix_triggers=tuple(t.lower() for t in a.get("prefix_triggers", [])),
                obsidian_vault=a.get("obsidian_vault"),
                terminal_session=a["terminal_session"],
            )
            for a in cfg["agents"]
        }
        self.broadcast_keywords: tuple[str, ...] = tuple(
            k.lower() for k in cfg.get("broadcast_keywords", [])
        )
        self.default_agent = "floki"

    def route(self, text: str) -> tuple[str, str]:
        """Apply the same rule order Pipecat will use in Phase 5:
           1. Keyword (broadcast)
           2. Prefix (explicit agent invocation)
           3. Default (floki triage)

        Returns (agent_name, routing_reason).
        """
        lowered = text.strip().lower()

        for kw in self.broadcast_keywords:
            if kw in lowered:
                return ("floki", f"keyword:{kw}")

        first_token = lowered.split(None, 1)[0].rstrip(",:") if lowered else ""
        for agent in self.agents.values():
            if first_token in agent.prefix_triggers:
                return (agent.name, f"prefix:{first_token}")

        return (self.default_agent, "default")

    def names(self) -> list[str]:
        return list(self.agents.keys())
