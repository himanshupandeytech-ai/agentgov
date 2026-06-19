"""Detectors are deterministic, so they are cheap to test exactly."""

from agentgov.detectors import (
    Finding,
    run_detectors,
    detect_injection_to_exfiltration,
    detect_missing_oversight,
    detect_unbounded_delegation_loop,
    detect_unsupervised_external_write,
)


def _agent(**overrides):
    base = {
        "name": "t",
        "nodes": [
            {"id": "web", "consumes_external": True, "external_action": False, "human_in_loop": False},
            {"id": "act", "consumes_external": False, "external_action": True, "human_in_loop": False},
        ],
        "edges": [{"from": "web", "to": "act"}],
        "oversight": {"kill_switch": False, "audit_log": False},
    }
    base.update(overrides)
    return base


def test_unsupervised_external_write_flags_unapproved_action():
    findings = detect_unsupervised_external_write(_agent())
    assert [f.pattern_id for f in findings] == ["unsupervised_external_write"]
    assert findings[0].nodes == ["act"]


def test_human_in_loop_clears_unsupervised_write():
    agent = _agent(
        nodes=[{"id": "act", "external_action": True, "human_in_loop": True}],
        edges=[],
    )
    assert detect_unsupervised_external_write(agent) == []


def test_injection_path_detected_through_intermediate_node():
    findings = detect_injection_to_exfiltration(_agent())
    assert len(findings) == 1
    assert findings[0].nodes == ["web", "act"]


def test_no_injection_path_when_disconnected():
    agent = _agent(edges=[])
    assert detect_injection_to_exfiltration(agent) == []


def test_missing_oversight_is_high_when_agent_acts_externally():
    findings = detect_missing_oversight(_agent())
    assert findings[0].severity == "high"
    assert "kill-switch" in findings[0].evidence


def test_missing_oversight_is_medium_without_external_action():
    agent = _agent(nodes=[{"id": "x", "external_action": False}])
    findings = detect_missing_oversight(agent)
    assert findings[0].severity == "medium"


def test_run_detectors_orders_high_before_medium():
    severities = [f.severity for f in run_detectors(_agent())]
    assert severities == sorted(severities, key={"high": 0, "medium": 1, "low": 2}.get)


def test_delegation_cycle_detected_when_unbounded():
    agent = _agent(
        nodes=[{"id": "a"}, {"id": "b"}],
        edges=[{"from": "a", "to": "b"}, {"from": "b", "to": "a"}],
    )
    findings = detect_unbounded_delegation_loop(agent)
    assert len(findings) == 1
    assert findings[0].pattern_id == "unbounded_delegation_loop"
    assert set(findings[0].nodes) == {"a", "b"}


def test_declared_limit_clears_delegation_loop():
    agent = _agent(
        nodes=[{"id": "a"}, {"id": "b"}],
        edges=[{"from": "a", "to": "b"}, {"from": "b", "to": "a"}],
        limits={"max_delegation_depth": 2},
    )
    assert detect_unbounded_delegation_loop(agent) == []


def test_acyclic_graph_has_no_delegation_finding():
    assert detect_unbounded_delegation_loop(_agent()) == []  # demo graph is a DAG


def test_governed_agent_produces_no_findings():
    """The controls in the safe demo must clear every detector."""
    governed = {
        "name": "governed",
        "nodes": [
            {"id": "web", "consumes_external": True, "external_action": False},
            {"id": "sum", "consumes_external": False, "external_action": False},
            {"id": "act", "external_action": True, "human_in_loop": True},
        ],
        "edges": [{"from": "web", "to": "sum"}],
        "oversight": {"kill_switch": True, "audit_log": True},
    }
    assert run_detectors(governed) == []
