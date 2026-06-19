"""Render findings + corpus into a Markdown Governance Audit Report.

For each finding the full report composes, from the corpus, the causal chain,
severity rationale, mapped obligations (NIST + EU), the system-card tie,
context-dependence, the proportionate control, and where the frameworks fall
short. The cover states the thesis and its falsifiability condition. A short
summary view (render_summary) is the default; the full view is opt-in.
"""

from __future__ import annotations

from typing import Any

from .detectors import SEVERITY_ORDER, Finding


def _patterns_index(corpus: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {p["id"]: p for p in corpus["risk_patterns"]["patterns"]}


def _format_chain(template: str, context: dict[str, str]) -> str:
    try:
        return template.format(**context)
    except (KeyError, IndexError):
        return template


def _render_finding(idx: int, finding: Finding, pattern: dict[str, Any], agent: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    sev = finding.severity.upper()
    lines.append(f"### {idx}. [{sev}] {pattern['title']}")
    if finding.nodes:
        lines.append(f"**Where:** `{'`, `'.join(finding.nodes)}`")
    lines.append("")
    lines.append(f"**Evidence.** {finding.evidence}")
    lines.append("")
    lines.append(f"**Causal chain.** {_format_chain(pattern['causal_chain'], finding.context)}")
    lines.append("")
    lines.append(
        f"**Why this severity.** Trustworthiness property at stake: "
        f"_{pattern['trustworthiness_property']}_. Ranked **{sev}** for this agent "
        f"because the deployment context below determines the obligation it triggers."
    )
    lines.append("")

    # Mapped obligations.
    lines.append("**Mapped obligations.**")
    for trig in pattern.get("triggers", []):
        lines.append(
            f"- **{trig['framework'].replace('_', ' ')} - {trig['ref']}:** {trig['obligation']}"
        )
    lines.append("")

    # System-card fluency: tie a finding to the wrapped model's published card.
    card = (agent.get("model") or {}).get("system_card")
    if card:
        note = card.get("note")
        url = card.get("url")
        if note:
            lines.append(f"**System-card tie.** {note}" + (f" (see {url})" if url else ""))
            lines.append("")

    # Judgment: context-dependence.
    ctx = pattern.get("context_dependence", {})
    if ctx:
        lines.append("**Context-dependence (same evidence, different verdict).**")
        lines.append(f"- _Low-stakes:_ {ctx.get('low', '-')}")
        lines.append(f"- _High-stakes:_ {ctx.get('high', '-')}")
        lines.append("")

    lines.append(f"**Proportionate control.** {pattern['proportionate_control']}")
    lines.append("")
    lines.append(f"**Where the frameworks fall short.** {pattern['framework_gap']}")
    lines.append("")
    return lines


def _refs_short(pattern: dict[str, Any]) -> str:
    parts = []
    for t in pattern.get("triggers", []):
        fw = "EU" if t["framework"] == "EU_AI_ACT" else "NIST"
        parts.append(f"{fw} {t['ref']}")
    return "; ".join(parts)


def render_summary(agent: dict[str, Any], findings: list[Finding], corpus: dict[str, Any]) -> str:
    """Short report: one row per finding. The default view for day-to-day use."""
    patterns = _patterns_index(corpus)
    model = agent.get("model") or {}
    out: list[str] = []

    out.append(f"# Governance Audit - {agent.get('name', 'unnamed agent')}")
    bits = []
    if model.get("name"):
        bits.append(f"model: {model['name']}")
    bits.append(f"input: {agent.get('source', 'manifest')}")
    out.append("_" + " | ".join(bits) + "_")
    out.append("")

    counts = {"high": 0, "medium": 0, "low": 0}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    out.append(
        f"**{len(findings)} finding(s)** - "
        f"High {counts['high']}, Medium {counts['medium']}, Low {counts['low']}"
    )
    out.append("")

    if not findings:
        out.append("No orchestration-layer risks detected. ✅")
        out.append("")
        return "\n".join(out)

    out.append("| # | Severity | Problem | Where | Rule | Fix |")
    out.append("|---|---|---|---|---|---|")
    ranked = sorted(findings, key=lambda f: SEVERITY_ORDER.get(f.severity, 99))
    for i, f in enumerate(ranked, 1):
        p = patterns.get(f.pattern_id, {})
        where = "`" + "`, `".join(f.nodes) + "`" if f.nodes else "-"
        out.append(
            f"| {i} | {f.severity.upper()} | {p.get('title', f.pattern_id)} | "
            f"{where} | {_refs_short(p)} | {p.get('fix_short', '-')} |"
        )
    out.append("")
    out.append("_Run with `--full` for the reasoning behind each finding._")
    out.append("")
    return "\n".join(out)


def render_markdown(agent: dict[str, Any], findings: list[Finding], corpus: dict[str, Any]) -> str:
    patterns = _patterns_index(corpus)
    meta = corpus["risk_patterns"].get("meta", {})
    model = agent.get("model") or {}

    out: list[str] = []
    out.append(f"# Governance Audit Report - {agent.get('name', 'unnamed agent')}")
    out.append("")
    if model.get("name"):
        out.append(f"**Wrapped model:** {model['name']}")
    out.append(f"**Auditor:** agentgov (static orchestration-layer audit)")
    if agent.get("source") == "trace":
        out.append("")
        out.append(
            "> **Input: run trace.** This audit is built from a recorded run, so it "
            "reflects what the agent actually did. Two limits apply: human approvals "
            "are not always recorded (recorded actions are treated as unsupervised), "
            "and the run is modelled as a timeline (an earlier untrusted-input call "
            "shares context with a later action call). Oversight instrumentation is "
            "not observable from a trace and is not assessed."
        )
    elif agent.get("source") == "code":
        out.append("")
        out.append(
            "> **Input: source code (static).** Built by reading the LangGraph code "
            "without executing it - a proactive, pre-deploy check. Approval gates "
            "declared in code (interrupt_before/after) are credited. Limit: only "
            "structure written literally is visible; a graph built dynamically is "
            "partly invisible, which is what the runtime trace layer backstops."
        )
    out.append("")

    # Cover: thesis + scope + falsifiability.
    out.append("## Thesis & scope")
    out.append(f"> {meta.get('thesis', '')}")
    out.append("")
    out.append(f"**Scope.** {meta.get('scope_note', '')}")
    out.append("")
    out.append(f"**What would change my mind.** {meta.get('falsifiability', '')}")
    out.append("")

    # Summary table by severity.
    counts = {"high": 0, "medium": 0, "low": 0}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    out.append("## Summary")
    out.append("")
    out.append("| Severity | Count |")
    out.append("|---|---|")
    for sev in ("high", "medium", "low"):
        out.append(f"| {sev.capitalize()} | {counts.get(sev, 0)} |")
    out.append("")
    if not findings:
        out.append("_No orchestration-layer risks detected by the current pattern set._")
        out.append("")

    # Ranked findings.
    if findings:
        out.append("## Findings (ranked by severity)")
        out.append("")
        ranked = sorted(findings, key=lambda f: SEVERITY_ORDER.get(f.severity, 99))
        for i, finding in enumerate(ranked, 1):
            pattern = patterns.get(finding.pattern_id)
            if pattern is None:
                continue
            out.extend(_render_finding(i, finding, pattern, agent))

    # Frameworks appendix: the corpus as a reference table.
    out.append("## Frameworks referenced")
    out.append("")
    nist = corpus.get("nist", {})
    eu = corpus.get("eu_ai_act", {})
    out.append(f"**{nist.get('framework', 'NIST AI RMF')}** - public domain (U.S. Gov work).")
    for ref, text in (nist.get("subcategories") or {}).items():
        out.append(f"- `{ref}` - {text}")
    out.append("")
    out.append(f"**{eu.get('regulation', 'EU AI Act')}** - EUR-Lex reuse policy (Dec. 2011/833/EU).")
    for ref, body in (eu.get("articles") or {}).items():
        out.append(f"- `{ref}` ({body.get('title', '')}) - {body.get('summary', '')}")
    out.append("")
    out.append(
        "_Behavioral/capability testing is out of scope and hands off to Inspect "
        "(https://inspect.aisi.org.uk). agentgov audits structure, not model behavior._"
    )
    out.append("")
    return "\n".join(out)
