"""The AST reader is deterministic, so we assert the exact derived graph."""

from agentgov.code_import import code_to_agent
from agentgov.detectors import run_detectors

SOURCE = """
from langgraph.graph import START, END, StateGraph

def build():
    b = StateGraph(dict)
    b.add_node("web_search", web_search)
    b.add_node("summarize", summarize)
    b.add_node("send_email", send_email)
    b.add_edge(START, "web_search")
    b.add_edge("web_search", "summarize")
    b.add_edge("summarize", "send_email")
    b.add_edge("send_email", END)
    return b.compile(interrupt_before=["send_email"])
"""


def test_nodes_and_edges_extracted_sentinels_dropped():
    agent = code_to_agent(SOURCE)
    assert [n["id"] for n in agent["nodes"]] == ["web_search", "summarize", "send_email"]
    assert {"from": "web_search", "to": "summarize"} in agent["edges"]
    assert {"from": "summarize", "to": "send_email"} in agent["edges"]
    # START/END must not appear as nodes or edge endpoints.
    assert all(e["from"] not in ("START", "END") for e in agent["edges"])


def test_names_classified_by_keyword():
    by_id = {n["id"]: n for n in code_to_agent(SOURCE)["nodes"]}
    assert by_id["web_search"]["consumes_external"] is True
    assert by_id["send_email"]["external_action"] is True


def test_interrupt_before_credits_human_in_loop():
    by_id = {n["id"]: n for n in code_to_agent(SOURCE)["nodes"]}
    assert by_id["send_email"]["human_in_loop"] is True


def test_approval_gate_clears_write_but_injection_path_remains():
    pattern_ids = {f.pattern_id for f in run_detectors(code_to_agent(SOURCE))}
    # gate credited -> unsupervised write cleared
    assert "unsupervised_external_write" not in pattern_ids
    # gate does not sanitise content -> injection path still flagged
    assert "injection_to_exfiltration" in pattern_ids
    # oversight not inferable from code -> not asserted
    assert "missing_oversight_instrumentation" not in pattern_ids


def test_conditional_edges_dict_targets():
    src = """
b.add_conditional_edges("router", choose, {"a": "tool_a", "b": "tool_b"})
"""
    edges = code_to_agent(src)["edges"]
    assert {"from": "router", "to": "tool_a"} in edges
    assert {"from": "router", "to": "tool_b"} in edges
