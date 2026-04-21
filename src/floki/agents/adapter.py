from __future__ import annotations

import asyncio
import logging
import shlex
import shutil
from abc import ABC, abstractmethod

from floki.agents.registry import AgentRegistry
from floki.queue.models import Envelope

log = logging.getLogger(__name__)


class AgentAdapter(ABC):
    """Abstract bridge between the dispatcher and a running agent.

    The Elephant Agent protocol: any new OSS agent framework (Aider, Goose,
    Claude Code, a bespoke OpenClaw fork) becomes usable by writing one
    subclass here. The dispatcher never changes.
    """

    @abstractmethod
    async def deliver(self, env: Envelope) -> None: ...

    async def healthcheck(self) -> bool:
        return True


class StubAdapter(AgentAdapter):
    """Log-only adapter. Used in tests and before real terminals are wired."""

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.delivered: list[Envelope] = []

    async def deliver(self, env: Envelope) -> None:
        self.delivered.append(env)
        log.info(
            "[stub:%s] #%s (%s): %s",
            self.agent_name,
            env.id,
            env.routing_reason,
            env.payload,
        )


class TmuxAdapter(AgentAdapter):
    """Deliver envelopes to a tmux session running the agent's terminal.

    Uses load-buffer / paste-buffer so multi-line payloads don't need shell
    escaping. Sends Enter via `send-keys C-m` after paste.
    """

    def __init__(self, session: str, tmux_bin: str = "tmux"):
        self.session = session
        self.tmux_bin = tmux_bin

    async def healthcheck(self) -> bool:
        if shutil.which(self.tmux_bin) is None:
            return False
        rc, _, _ = await self._run(self.tmux_bin, "has-session", "-t", self.session)
        return rc == 0

    async def deliver(self, env: Envelope) -> None:
        buf_name = f"floki-{env.id or 'x'}"
        rc, _, err = await self._run(
            self.tmux_bin, "load-buffer", "-b", buf_name, "-",
            stdin=env.payload.encode("utf-8"),
        )
        if rc != 0:
            raise RuntimeError(f"tmux load-buffer failed: {err}")

        rc, _, err = await self._run(
            self.tmux_bin, "paste-buffer", "-d", "-b", buf_name, "-t", self.session
        )
        if rc != 0:
            raise RuntimeError(f"tmux paste-buffer failed: {err}")

        rc, _, err = await self._run(self.tmux_bin, "send-keys", "-t", self.session, "C-m")
        if rc != 0:
            raise RuntimeError(f"tmux send-keys failed: {err}")

    async def _run(self, *argv: str, stdin: bytes | None = None) -> tuple[int, bytes, bytes]:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE if stdin is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate(input=stdin)
        if proc.returncode != 0:
            log.debug("tmux cmd failed (%s): %s", shlex.join(argv), err.decode(errors="replace"))
        return (proc.returncode or 0, out, err)


class AdapterRegistry:
    """Map agent_name -> AgentAdapter. Falls back to StubAdapter for unregistered."""

    def __init__(self, agents: AgentRegistry):
        self.agents = agents
        self._adapters: dict[str, AgentAdapter] = {}

    def set(self, agent_name: str, adapter: AgentAdapter) -> None:
        self._adapters[agent_name] = adapter

    def get(self, agent_name: str) -> AgentAdapter:
        if agent_name not in self._adapters:
            self._adapters[agent_name] = StubAdapter(agent_name)
        return self._adapters[agent_name]

    @classmethod
    def tmux_from_registry(cls, agents: AgentRegistry) -> "AdapterRegistry":
        """Build a registry that targets each agent's tmux session from agents.yaml."""
        reg = cls(agents)
        for spec in agents.agents.values():
            reg.set(spec.name, TmuxAdapter(session=spec.terminal_session))
        return reg
