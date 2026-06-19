"""Build an agent picture from a real run trace instead of a hand-written manifest.

Why this exists: a hand-written manifest reflects what the author *says* the agent
does. A trace reflects what it *actually did* on a run - which tools fired, in what
order. We convert a LangSmith-style export into the exact same dict shape the
detectors already consume, so nothing downstream changes.

Honest limits (a trace cannot show everything):
  * Whether a human approved an action out-of-band is usually not recorded, so we
    treat recorded actions as unsupervised unless the trace says otherwise.
  * A trace is a timeline of calls, not a data-flow graph. We model it as a
    timeline: an earlier untrusted-input call shares the agent's context with a
    later action call, so we connect them in order. That is a heuristic, and the
    report says so.
  * Oversight instrumentation (kill-switch / audit log) is not observable from a
    trace, so we omit it rather than guess - the oversight detector then skips.

These limits are a feature for a governance tool: we never claim more than the
evidence supports.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ._keywords import classify_tool


def langsmith_to_agent(data: dict[str, Any]) -> dict[str, Any]:
    """Convert a LangSmith-style trace export into an agent dict for the detectors.

    Expected shape: ``{"name": ..., "runs": [ {id, name, run_type, ...}, ... ]}``
    where ``run_type`` is one of ``tool`` / ``llm`` / ``chain``. Runs are taken in
    listed order as the execution timeline.
    """
    runs = data.get("runs", [])
    nodes: list[dict[str, Any]] = []
    timeline_ids: list[str] = []
    used: set[str] = set()

    for run in runs:
        run_type = run.get("run_type")
        if run_type not in ("tool", "llm"):
            continue  # skip the chain/agent wrapper runs; keep tool + llm calls
        base = run.get("name", "node")
        node_id = base
        suffix = 1
        while node_id in used:  # disambiguate repeated tool names
            suffix += 1
            node_id = f"{base}#{suffix}"
        used.add(node_id)

        node: dict[str, Any] = {"id": node_id, "kind": run_type, "tool": base}
        if run_type == "tool":
            node.update(classify_tool(base))
        else:
            node.update({"external_action": False, "consumes_external": False})
        node["human_in_loop"] = bool(run.get("human_in_loop", False))
        nodes.append(node)
        timeline_ids.append(node_id)

    # Timeline edges: connect each call to the next in execution order.
    edges = [
        {"from": a, "to": b} for a, b in zip(timeline_ids, timeline_ids[1:])
    ]

    agent: dict[str, Any] = {
        "name": data.get("name", "agent-from-trace"),
        "source": "trace",
        "nodes": nodes,
        "edges": edges,
        # No `oversight` key on purpose: not observable from a trace.
    }
    model = data.get("model")
    if model:
        agent["model"] = model
    return agent


def load_trace(path: str | Path) -> dict[str, Any]:
    """Read a LangSmith-style trace JSON file and return an agent dict."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Trace file not found: {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Trace file must be a JSON object with a 'runs' array.")
    return langsmith_to_agent(data)
