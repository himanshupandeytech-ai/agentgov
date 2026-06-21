"""Policy enforcement and the audit register (the GOVERN function).

The accountable human declares policy in `governance.yaml`: who owns each control,
the score threshold that blocks, and any waivers (with an expiry). agentgov then
*enforces* that policy - it does not invent it. Every scan is appended to an
append-only audit register as evidence.

The tool enforces and records; a named person still owns the risk.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml


def load_policy(path: str | Path) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def _matching_waiver(pattern_id: str, nodes: list[str], waivers: list[dict], today: str) -> dict | None:
    for w in waivers:
        if w.get("pattern") != pattern_id:
            continue
        expires = str(w.get("expires", "")) or None
        if expires and expires < today:
            continue  # expired waiver no longer applies
        node = w.get("node")
        if node and node not in nodes:
            continue
        return w
    return None


def apply_policy(scored: list[dict[str, Any]], policy: dict[str, Any], today: str | None = None) -> dict[str, Any]:
    """Decide pass/block from scores, owners, and waivers."""
    today = today or date.today().isoformat()
    threshold = int(policy.get("block_at_score", 70))
    owners = policy.get("owners", {})
    default_owner = policy.get("default_owner", "unassigned")
    waivers = policy.get("waivers", [])

    blocking, waived = [], []
    for s in scored:
        f = s["finding"]
        rec = {
            "pattern": f.pattern_id, "score": s["score"], "nodes": f.nodes,
            "owner": owners.get(f.pattern_id, default_owner),
        }
        w = _matching_waiver(f.pattern_id, f.nodes, waivers, today)
        if w:
            waived.append({**rec, "waiver_reason": w.get("reason", ""), "expires": str(w.get("expires", ""))})
        elif s["score"] >= threshold:
            blocking.append(rec)
    return {
        "decision": "block" if blocking else "pass",
        "threshold": threshold,
        "blocking": blocking,
        "waived": waived,
    }


def record(entry: dict[str, Any], path: str | Path) -> None:
    """Append one scan record to the audit register (JSON Lines)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def render_decision(target: str, result: dict[str, Any]) -> str:
    """Markdown block summarising the governance decision."""
    out = ["", "## Governance decision", ""]
    mark = "BLOCK ❌" if result["decision"] == "block" else "PASS ✅"
    out.append(f"**{mark}** (policy blocks at risk ≥ {result['threshold']})")
    out.append("")
    if result["blocking"]:
        out.append("**Blocking findings:**")
        for b in result["blocking"]:
            where = ", ".join(b["nodes"]) if b["nodes"] else "-"
            out.append(f"- risk {b['score']} · {b['pattern']} ({where}) · owner: {b['owner']}")
        out.append("")
    if result["waived"]:
        out.append("**Waived (accepted risk):**")
        for w in result["waived"]:
            out.append(f"- {w['pattern']} · owner: {w['owner']} · until {w['expires']} · {w['waiver_reason']}")
        out.append("")
    return "\n".join(out)


def audit_entry(target: str, scored: list[dict[str, Any]], result: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "target": target,
        "decision": result["decision"],
        "threshold": result["threshold"],
        "findings": [{"pattern": s["finding"].pattern_id, "score": s["score"]} for s in scored],
        "blocking": [b["pattern"] for b in result["blocking"]],
        "waived": [w["pattern"] for w in result["waived"]],
    }
