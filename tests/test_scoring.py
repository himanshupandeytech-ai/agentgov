"""Scoring is deterministic and ordered by risk."""

from agentgov.detectors import Finding, run_detectors
from agentgov.loader import load_corpus
from agentgov.scoring import posture, score_all, score_finding

PATTERNS = {p["id"]: p for p in load_corpus()["risk_patterns"]["patterns"]}


def test_score_in_range_and_high_severity_scores_more():
    high = Finding("unsupervised_external_write", "high", ["a"], "e")
    base_pattern = PATTERNS["unsupervised_external_write"]
    s = score_finding(high, base_pattern)
    assert 0 <= s <= 100
    low = Finding("unsupervised_external_write", "low", ["a"], "e")
    assert score_finding(high, base_pattern) > score_finding(low, base_pattern)


def test_score_all_sorted_descending():
    agent = {
        "name": "t",
        "nodes": [
            {"id": "web", "consumes_external": True},
            {"id": "act", "external_action": True, "human_in_loop": False},
        ],
        "edges": [{"from": "web", "to": "act"}],
        "oversight": {"kill_switch": False, "audit_log": False},
    }
    scored = score_all(run_detectors(agent), PATTERNS)
    scores = [s["score"] for s in scored]
    assert scores == sorted(scores, reverse=True)


def test_posture_counts_action_nodes_and_paths():
    agent = {
        "name": "t",
        "nodes": [
            {"id": "web", "consumes_external": True},
            {"id": "act", "external_action": True, "human_in_loop": False},
        ],
        "edges": [{"from": "web", "to": "act"}],
        "oversight": {"kill_switch": False, "audit_log": False},
    }
    scored = score_all(run_detectors(agent), PATTERNS)
    pm = posture(agent, scored)
    assert pm["action_nodes"] == 1
    assert pm["untrusted_to_action_paths"] == 1
    assert 0 <= pm["overall_risk"] <= 100
