from __future__ import annotations

import pytest

from floki.agents import AdapterRegistry, AgentRegistry, StubAdapter
from floki.agents.adapter import TmuxAdapter
from floki.queue.models import Envelope, Source


async def test_stub_adapter_records_delivery() -> None:
    adapter = StubAdapter("comms")
    env = Envelope(source=Source.TELEGRAM, target_agent="comms", payload="hi", id=1)
    await adapter.deliver(env)
    assert adapter.delivered == [env]


async def test_adapter_registry_defaults_to_stub() -> None:
    agents = AgentRegistry()
    reg = AdapterRegistry(agents)
    adapter = reg.get("ops")
    assert isinstance(adapter, StubAdapter)
    assert reg.get("ops") is adapter  # memoized


async def test_tmux_from_registry_wires_sessions() -> None:
    agents = AgentRegistry()
    reg = AdapterRegistry.tmux_from_registry(agents)
    for name, spec in agents.agents.items():
        adapter = reg.get(name)
        assert isinstance(adapter, TmuxAdapter)
        assert adapter.session == spec.terminal_session


async def test_tmux_healthcheck_false_when_tmux_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = TmuxAdapter(session="nope", tmux_bin="definitely-not-a-binary-xyz")
    assert await adapter.healthcheck() is False
