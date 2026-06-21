"""Quantitative risk scoring and agent posture metrics (the MEASURE function).

Each finding gets a 0-100 score from its pattern's impact x likelihood, nudged by
the detector's contextual severity. Posture metrics summarise the agent as
numbers (action nodes, untrusted->action paths, oversight coverage, loops). This
turns categorical severity into something you can rank, threshold, and trend.
"""

from __future__ import annotations

from typing import Any

from .detectors import Finding, _nodes_by_id


def score_finding(finding: Finding, pattern: dict[str, Any]) -> int:
    """0-100 risk score: impact x likelihood (each 1-5), scaled, severity-nudged."""
    impact = int(pattern.get("impact", 3))
    likelihood = int(pattern.get("likelihood", 3))
    score = impact * likelihood * 4  # 4..100
    if finding.severity == "high":
        score += 15
    elif finding.severity == "low":
        score -= 15
    return max(0, min(100, score))


def posture(agent: dict[str, Any], scored: list[dict[str, Any]]) -> dict[str, Any]:
    """Numeric summary of the agent's risk surface."""
    nodes = list(_nodes_by_id(agent).values())
    action_nodes = [n for n in nodes if n.get("external_action")]
    gated = [n for n in action_nodes if n.get("human_in_loop")]
    injection = [s for s in scored if s["pattern_id"] == "injection_to_exfiltration"]
    loops = [s for s in scored if s["pattern_id"] == "unbounded_delegation_loop"]
    overall = max((s["score"] for s in scored), default=0)
    return {
        "overall_risk": overall,
        "action_nodes": len(action_nodes),
        "action_nodes_gated": f"{len(gated)}/{len(action_nodes)}" if action_nodes else "0/0",
        "untrusted_to_action_paths": len(injection),
        "delegation_loops": len(loops),
        "node_count": len(nodes),
    }


def score_all(findings: list[Finding], patterns: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach a score to each finding (sorted high score first)."""
    out = []
    for f in findings:
        p = patterns.get(f.pattern_id, {})
        out.append({"finding": f, "pattern_id": f.pattern_id, "score": score_finding(f, p)})
    out.sort(key=lambda s: s["score"], reverse=True)
    return out
