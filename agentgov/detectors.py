"""Static risk detectors over a declarative agent manifest.

Each detector reads the manifest's nodes/edges/permissions and emits Findings. No
model calls, no network, no execution of the target agent - fully deterministic.

The detectors only structure evidence; the corpus holds the reasoning. Manifest
shape (see demo/agent.yaml):

    nodes:
      - id: web_search
        kind: tool
        consumes_external: true      # ingests untrusted outside content
        external_action: false       # performs an outbound/irreversible action
        human_in_loop: false
    edges:
      - {from: web_search, to: send_email}
    oversight: {kill_switch: false, audit_log: false}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


@dataclass
class Finding:
    """One detected risk, linked to a corpus pattern by `pattern_id`."""

    pattern_id: str
    severity: str
    nodes: list[str]
    evidence: str
    # Values substituted into the corpus `causal_chain` template.
    context: dict[str, str] = field(default_factory=dict)


def _nodes_by_id(agent: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {n["id"]: n for n in agent.get("nodes", [])}


def _adjacency(agent: dict[str, Any]) -> dict[str, list[str]]:
    adj: dict[str, list[str]] = {n["id"]: [] for n in agent.get("nodes", [])}
    for edge in agent.get("edges", []):
        src, dst = edge["from"], edge["to"]
        adj.setdefault(src, []).append(dst)
        adj.setdefault(dst, [])  # ensure dst is a key even if it has no out-edges
    return adj


def _reachable(start: str, adj: dict[str, list[str]]) -> set[str]:
    """Nodes reachable from `start` following directed edges (excludes start)."""
    seen: set[str] = set()
    stack = list(adj.get(start, []))
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        stack.extend(adj.get(node, []))
    return seen


def detect_unsupervised_external_write(agent: dict[str, Any]) -> list[Finding]:
    """A node performs an external/irreversible action with no human approval."""
    findings: list[Finding] = []
    for node in agent.get("nodes", []):
        if node.get("external_action") and not node.get("human_in_loop"):
            action = node.get("tool") or node.get("id")
            findings.append(
                Finding(
                    pattern_id="unsupervised_external_write",
                    severity="high",
                    nodes=[node["id"]],
                    evidence=(
                        f"Node '{node['id']}' performs external action "
                        f"('{action}') with human_in_loop=false."
                    ),
                    context={"node": node["id"], "action": str(action)},
                )
            )
    return findings


def detect_injection_to_exfiltration(agent: dict[str, Any]) -> list[Finding]:
    """A path runs from an untrusted-input node to an external-action node."""
    nodes = _nodes_by_id(agent)
    adj = _adjacency(agent)
    findings: list[Finding] = []
    sources = [nid for nid, n in nodes.items() if n.get("consumes_external")]
    for src in sources:
        for dst in _reachable(src, adj):
            if nodes.get(dst, {}).get("external_action"):
                findings.append(
                    Finding(
                        pattern_id="injection_to_exfiltration",
                        severity="high",
                        nodes=[src, dst],
                        evidence=(
                            f"Untrusted input at '{src}' reaches external-action "
                            f"node '{dst}' via a directed path."
                        ),
                        context={"src": src, "dst": dst},
                    )
                )
    return findings


def _find_cycle(adj: dict[str, list[str]]) -> list[str]:
    """Return one directed cycle as an ordered node list, or [] if acyclic."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in adj}
    stack: list[str] = []

    def visit(node: str) -> list[str]:
        color[node] = GRAY
        stack.append(node)
        for nxt in adj.get(node, []):
            if color.get(nxt, WHITE) == GRAY:  # back-edge → cycle
                return stack[stack.index(nxt):] + [nxt]
            if color.get(nxt, WHITE) == WHITE:
                found = visit(nxt)
                if found:
                    return found
        color[node] = BLACK
        stack.pop()
        return []

    for start in adj:
        if color[start] == WHITE:
            cycle = visit(start)
            if cycle:
                return cycle
    return []


def detect_unbounded_delegation_loop(agent: dict[str, Any]) -> list[Finding]:
    """A delegation cycle exists with no declared depth/step budget."""
    limits = agent.get("limits", {}) or {}
    if limits.get("max_delegation_depth") or limits.get("max_steps"):
        return []  # bounded → not a finding
    cycle = _find_cycle(_adjacency(agent))
    if not cycle:
        return []
    # High if the cycle can reach an external-action node, else medium.
    nodes = _nodes_by_id(agent)
    acts = any(nodes.get(n, {}).get("external_action") for n in cycle)
    return [
        Finding(
            pattern_id="unbounded_delegation_loop",
            severity="high" if acts else "medium",
            nodes=cycle,
            evidence=(
                f"Directed cycle {' → '.join(cycle)} with no declared "
                f"max_delegation_depth or max_steps."
            ),
            context={"cycle": " → ".join(cycle)},
        )
    ]


def detect_missing_oversight(agent: dict[str, Any]) -> list[Finding]:
    """Kill-switch and/or audit logging absent. Higher severity if agent acts.

    If the manifest has no `oversight` key at all (e.g. built from a trace, where
    oversight is not observable), we cannot assess it and skip - absence of
    evidence is not evidence of absence.
    """
    if "oversight" not in agent:
        return []
    oversight = agent.get("oversight", {}) or {}
    missing = []
    if not oversight.get("kill_switch"):
        missing.append("kill-switch")
    if not oversight.get("audit_log"):
        missing.append("audit logging")
    if not missing:
        return []
    acts_externally = any(n.get("external_action") for n in agent.get("nodes", []))
    return [
        Finding(
            pattern_id="missing_oversight_instrumentation",
            severity="high" if acts_externally else "medium",
            nodes=[],
            evidence=f"Agent declares no {' and no '.join(missing)}.",
            context={"missing": " and no ".join(missing)},
        )
    ]


DETECTORS = (
    detect_unsupervised_external_write,
    detect_injection_to_exfiltration,
    detect_unbounded_delegation_loop,
    detect_missing_oversight,
)


def run_detectors(agent: dict[str, Any]) -> list[Finding]:
    """Run all detectors and return findings ranked by severity (high first)."""
    findings: list[Finding] = []
    for detector in DETECTORS:
        findings.extend(detector(agent))
    findings.sort(key=lambda f: SEVERITY_ORDER.get(f.severity, 99))
    return findings
