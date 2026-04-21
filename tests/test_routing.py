from __future__ import annotations

from floki.agents import AgentRegistry


def test_prefix_routing() -> None:
    r = AgentRegistry()
    agent, reason = r.route("Comms, draft a reply to mom")
    assert agent == "comms"
    assert reason.startswith("prefix:")


def test_keyword_broadcast_routes_to_floki() -> None:
    r = AgentRegistry()
    agent, reason = r.route("Everyone give me a status update")
    assert agent == "floki"
    assert reason.startswith("keyword:")


def test_default_routes_to_floki() -> None:
    r = AgentRegistry()
    agent, reason = r.route("what's on my plate today?")
    assert agent == "floki"
    assert reason == "default"


def test_prefix_with_colon() -> None:
    r = AgentRegistry()
    agent, _ = r.route("Ops: log expense $42 lunch")
    assert agent == "ops"
