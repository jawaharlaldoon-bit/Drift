from __future__ import annotations

from drift.adk_app import build_root_agent


def test_adk_graph_has_required_specialists(settings):
    root = build_root_agent(settings)
    assert root.graph is not None
    names = {agent.name for agent in root.graph.nodes}
    assert names == {
        "__START__",
        "TriageAgent",
        "InvestigationAgent",
        "RemediationAgent",
        "ValidationAgent",
    }
    chain = [(edge.from_node.name, edge.to_node.name) for edge in root.graph.edges]
    assert chain == [
        ("__START__", "TriageAgent"),
        ("TriageAgent", "InvestigationAgent"),
        ("InvestigationAgent", "RemediationAgent"),
        ("RemediationAgent", "ValidationAgent"),
    ]
