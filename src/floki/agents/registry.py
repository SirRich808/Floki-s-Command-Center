from __future__ import annotations

import re
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


@dataclass(frozen=True)
class LogicRule:
    pattern: re.Pattern[str]
    target: str
    reason: str


class AgentRegistry:
    """Routing metadata loaded from config/agents.yaml.

    Consumed by:
      - Telegram handlers (prefix routing)
      - Pipecat voice WS (Phase 5 — same rules drive the voice router)
      - Task auto-assigner (Phase 4 dashboard)

    Rule order (all outside the LLM context):
      1. Keyword   — broadcast words → floki
      2. Prefix    — "Comms, ..." → comms
      3. Logic     — regex rules from YAML (pinned/JSON-driven routes)
      4. Default   — floki triage
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
        self.logic_rules: tuple[LogicRule, ...] = tuple(
            LogicRule(
                pattern=re.compile(r["pattern"]),
                target=r["target"],
                reason=r.get("reason", f"logic:{r['target']}"),
            )
            for r in cfg.get("logic_rules", [])
        )
        self.default_agent = "floki"

    def route(self, text: str) -> tuple[str, str]:
        """Returns (agent_name, routing_reason)."""
        stripped = text.strip()
        lowered = stripped.lower()

        for kw in self.broadcast_keywords:
            if kw in lowered:
                return ("floki", f"keyword:{kw}")

        first_token = lowered.split(None, 1)[0].rstrip(",:") if lowered else ""
        for agent in self.agents.values():
            if first_token in agent.prefix_triggers:
                return (agent.name, f"prefix:{first_token}")

        for rule in self.logic_rules:
            if rule.pattern.search(stripped) and rule.target in self.agents:
                return (rule.target, rule.reason)

        return (self.default_agent, "default")

    def names(self) -> list[str]:
        return list(self.agents.keys())
