"""Build an agent picture by reading LangGraph source code - without running it.

This is the proactive, pre-deploy layer: it audits what the developer actually
wrote, before the agent ever executes, so it can run as a CI gate. We parse the
source with Python's `ast` module and never import or execute it - reading the
code of an untrusted agent must not run that code.

We recognise the common LangGraph construction calls:
    builder.add_node("web_search", web_search)
    builder.add_edge("web_search", "summarize")
    builder.add_conditional_edges("router", choose, {"a": "tool_a", "b": "tool_b"})
    builder.compile(interrupt_before=["send_email"])   # a human-approval gate
The compiled approval gate is rewarded: nodes named in interrupt_before/after get
human_in_loop=true, so a control written in code clears the matching finding.

Honest limit (stated in the report): the AST sees structure declared *literally*.
A graph built dynamically (in a loop, or from variables) is only partly visible -
which is exactly why the runtime trace layer still matters.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from ._keywords import classify_tool

# Names that mark graph entry/exit, not real nodes.
_SENTINELS = {"START", "END", "__start__", "__end__"}


def _as_name(node: ast.AST) -> str | None:
    """Resolve an AST arg to a string: a literal, or a variable/function name."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _string_list(node: ast.AST) -> list[str]:
    if isinstance(node, (ast.List, ast.Tuple)):
        return [n for n in (_as_name(e) for e in node.elts) if n]
    return []


def code_to_agent(source: str, name: str = "agent-from-code") -> dict[str, Any]:
    """Parse LangGraph source text into an agent dict for the detectors."""
    tree = ast.parse(source)

    node_ids: list[str] = []          # preserves declaration order
    edges: list[dict[str, str]] = []
    tool_names: set[str] = set()
    human_nodes: set[str] = set()

    def _add_node(nid: str | None) -> None:
        if nid and nid not in _SENTINELS and nid not in node_ids:
            node_ids.append(nid)

    for call in ast.walk(tree):
        if not isinstance(call, ast.Call):
            continue
        func = call.func
        fname = func.attr if isinstance(func, ast.Attribute) else (
            func.id if isinstance(func, ast.Name) else None
        )
        if fname is None:
            continue

        if fname == "add_node" and call.args:
            _add_node(_as_name(call.args[0]))

        elif fname == "add_edge" and len(call.args) >= 2:
            src, dst = _as_name(call.args[0]), _as_name(call.args[1])
            _add_node(src)
            _add_node(dst)
            if src and dst and src not in _SENTINELS and dst not in _SENTINELS:
                edges.append({"from": src, "to": dst})

        elif fname == "add_conditional_edges" and call.args:
            src = _as_name(call.args[0])
            _add_node(src)
            targets: list[str] = []
            for arg in call.args[1:]:
                if isinstance(arg, ast.Dict):
                    targets += [n for n in (_as_name(v) for v in arg.values) if n]
                else:
                    targets += _string_list(arg)
            for kw in call.keywords:
                if isinstance(kw.value, ast.Dict):
                    targets += [n for n in (_as_name(v) for v in kw.value.values) if n]
            for dst in targets:
                _add_node(dst)
                if src and dst not in _SENTINELS and src not in _SENTINELS:
                    edges.append({"from": src, "to": dst})

        elif fname in ("bind_tools", "ToolNode"):
            arg = call.args[0] if call.args else None
            tool_names.update(_string_list(arg) if arg is not None else [])

        elif fname == "compile":
            for kw in call.keywords:
                if kw.arg in ("interrupt_before", "interrupt_after"):
                    human_nodes.update(_string_list(kw.value))

    tool_names.update(node_ids)  # nodes are tool-like unless clearly an llm step

    nodes: list[dict[str, Any]] = []
    for nid in node_ids:
        flags = classify_tool(nid)
        nodes.append(
            {
                "id": nid,
                "kind": "tool" if nid in tool_names else "node",
                "tool": nid,
                "external_action": flags["external_action"],
                "consumes_external": flags["consumes_external"],
                "human_in_loop": nid in human_nodes,
            }
        )

    return {
        "name": name,
        "source": "code",
        "nodes": nodes,
        "edges": edges,
        # No `oversight` key: not reliably inferable from source -> detector skips.
    }


def load_code(path: str | Path) -> dict[str, Any]:
    """Read a LangGraph .py file (statically) and return an agent dict."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Code file not found: {p}")
    try:
        return code_to_agent(p.read_text(encoding="utf-8"), name=p.stem)
    except SyntaxError as exc:
        raise ValueError(f"Could not parse {p}: {exc}") from exc
