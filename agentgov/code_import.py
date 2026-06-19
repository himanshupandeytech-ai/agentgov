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


def _function_ranges(tree: ast.AST) -> list[tuple[int, int, str]]:
    """(start_line, end_line, name) for every function, for line->function lookup."""
    ranges: list[tuple[int, int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = getattr(node, "end_lineno", node.lineno)
            ranges.append((node.lineno, end, node.name))
    return ranges


def _enclosing_function(line: int, ranges: list[tuple[int, int, str]]) -> str | None:
    """Innermost function containing `line` (smallest span wins for nesting)."""
    best: tuple[int, str] | None = None
    for start, end, fn_name in ranges:
        if start <= line <= end:
            span = end - start
            if best is None or span < best[0]:
                best = (span, fn_name)
    return best[1] if best else None


def code_to_agent(
    source: str, name: str = "agent-from-code", filename: str = "<source>"
) -> dict[str, Any]:
    """Parse LangGraph source text into an agent dict for the detectors."""
    tree = ast.parse(source)
    fn_ranges = _function_ranges(tree)

    node_ids: list[str] = []          # preserves declaration order
    edges: list[dict[str, str]] = []
    tool_names: set[str] = set()
    human_nodes: set[str] = set()
    loc: dict[str, int] = {}          # node id -> source line
    toolnode_tools: dict[str, list[str]] = {}  # node id -> tools it wraps (ToolNode)
    unresolved_cond: list[str] = []   # conditional routers with no explicit targets

    def _add_node(nid: str | None, line: int | None = None) -> None:
        if nid and nid not in _SENTINELS:
            if nid not in node_ids:
                node_ids.append(nid)
            if line is not None and nid not in loc:
                loc[nid] = line

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
            nid = _as_name(call.args[0])
            _add_node(nid, call.lineno)
            # If the node's value is ToolNode([...]), remember the tools it wraps
            # so we can classify the node by what those tools do.
            if nid and len(call.args) >= 2 and isinstance(call.args[1], ast.Call):
                inner = call.args[1].func
                inner_name = inner.attr if isinstance(inner, ast.Attribute) else (
                    inner.id if isinstance(inner, ast.Name) else None
                )
                if inner_name == "ToolNode" and call.args[1].args:
                    toolnode_tools[nid] = _string_list(call.args[1].args[0])

        elif fname == "add_edge" and len(call.args) >= 2:
            src, dst = _as_name(call.args[0]), _as_name(call.args[1])
            _add_node(src, call.lineno)
            _add_node(dst, call.lineno)
            if src and dst and src not in _SENTINELS and dst not in _SENTINELS:
                edges.append({"from": src, "to": dst})

        elif fname == "add_conditional_edges" and call.args:
            src = _as_name(call.args[0])
            _add_node(src, call.lineno)
            targets: list[str] = []
            for arg in call.args[1:]:
                if isinstance(arg, ast.Dict):
                    targets += [n for n in (_as_name(v) for v in arg.values) if n]
                else:
                    targets += _string_list(arg)
            for kw in call.keywords:
                if isinstance(kw.value, ast.Dict):
                    targets += [n for n in (_as_name(v) for v in kw.value.values) if n]
            if targets:
                for dst in targets:
                    _add_node(dst)
                    if src and dst not in _SENTINELS and src not in _SENTINELS:
                        edges.append({"from": src, "to": dst})
            elif src and src not in _SENTINELS:
                # No explicit targets (e.g. prebuilt `tools_condition`); resolve later.
                unresolved_cond.append(src)

        elif fname in ("bind_tools", "ToolNode"):
            arg = call.args[0] if call.args else None
            tool_names.update(_string_list(arg) if arg is not None else [])

        elif fname == "compile":
            for kw in call.keywords:
                if kw.arg in ("interrupt_before", "interrupt_after"):
                    human_nodes.update(_string_list(kw.value))

    # Resolve target-less conditional routers: a router with no named targets
    # (the prebuilt `tools_condition` pattern) typically routes to the tool node
    # that already routes back to it. Reconstruct that edge to recover the loop.
    for src in unresolved_cond:
        for e in list(edges):
            if e["to"] == src:
                back = {"from": src, "to": e["from"]}
                if back not in edges:
                    edges.append(back)

    tool_names.update(node_ids)  # nodes are tool-like unless clearly an llm step

    nodes: list[dict[str, Any]] = []
    for nid in node_ids:
        flags = classify_tool(nid)
        # A ToolNode is classified by the tools it wraps, not just its own name.
        for wrapped in toolnode_tools.get(nid, []):
            wf = classify_tool(wrapped)
            flags["external_action"] = flags["external_action"] or wf["external_action"]
            flags["consumes_external"] = flags["consumes_external"] or wf["consumes_external"]
        line = loc.get(nid)
        location = {
            "file": filename,
            "line": line,
            "function": _enclosing_function(line, fn_ranges) if line else None,
        }
        nodes.append(
            {
                "id": nid,
                "kind": "tool" if nid in tool_names else "node",
                "tool": nid,
                "external_action": flags["external_action"],
                "consumes_external": flags["consumes_external"],
                "human_in_loop": nid in human_nodes,
                "location": location,
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
        return code_to_agent(p.read_text(encoding="utf-8"), name=p.stem, filename=str(path))
    except SyntaxError as exc:
        raise ValueError(f"Could not parse {p}: {exc}") from exc
