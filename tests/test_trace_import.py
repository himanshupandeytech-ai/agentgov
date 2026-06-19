"""Trace import is deterministic, so we assert the exact derived graph."""

from agentgov.detectors import run_detectors
from agentgov.trace_import import langsmith_to_agent


def _trace(*tool_names):
    return {
        "name": "t",
        "runs": [{"id": "0", "name": "root", "run_type": "chain"}]
        + [
            {"id": str(i + 1), "name": n, "run_type": "tool"}
            for i, n in enumerate(tool_names)
        ],
    }


def test_chain_runs_are_skipped_tools_become_nodes():
    agent = langsmith_to_agent(_trace("web_search", "send_email"))
    ids = [n["id"] for n in agent["nodes"]]
    assert ids == ["web_search", "send_email"]  # root chain dropped


def test_tool_names_are_classified_by_keyword():
    agent = langsmith_to_agent(_trace("web_search", "send_email"))
    by_id = {n["id"]: n for n in agent["nodes"]}
    assert by_id["web_search"]["consumes_external"] is True
    assert by_id["send_email"]["external_action"] is True


def test_timeline_edges_connect_calls_in_order():
    agent = langsmith_to_agent(_trace("web_search", "summarize", "send_email"))
    # llm "summarize" also becomes a node; edges chain them in order.
    assert {"from": "web_search", "to": "summarize"} in agent["edges"]
    assert {"from": "summarize", "to": "send_email"} in agent["edges"]


def test_duplicate_tool_names_are_disambiguated():
    agent = langsmith_to_agent(_trace("http_get", "http_get"))
    assert [n["id"] for n in agent["nodes"]] == ["http_get", "http_get#2"]


def test_trace_agent_flags_injection_and_write_but_not_oversight():
    agent = langsmith_to_agent(_trace("web_search", "send_email"))
    pattern_ids = {f.pattern_id for f in run_detectors(agent)}
    assert "unsupervised_external_write" in pattern_ids
    assert "injection_to_exfiltration" in pattern_ids
    # oversight not observable from a trace → not asserted
    assert "missing_oversight_instrumentation" not in pattern_ids
