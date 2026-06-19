"""Command-line entrypoint: `agentgov audit <manifest.yaml>`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .detectors import run_detectors
from .code_import import load_code
from .loader import load_agent, load_corpus
from .report import render_markdown, render_summary
from .trace_import import load_trace


def _cmd_audit(args: argparse.Namespace) -> int:
    path = args.manifest
    low = path.lower()
    try:
        if args.code or low.endswith(".py"):
            agent = load_code(path)            # build / pre-deploy layer
        elif args.trace or low.endswith(".json"):
            agent = load_trace(path)           # runtime / audit layer
        else:
            agent = load_agent(path)           # design layer (manifest)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    corpus = load_corpus()
    findings = run_detectors(agent)
    render = render_markdown if args.full else render_summary
    report = render(agent, findings, corpus)

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"wrote {len(findings)} finding(s) to {args.output}", file=sys.stderr)
    else:
        print(report)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentgov",
        description="Static governance auditor for the agent orchestration layer.",
    )
    parser.add_argument("--version", action="version", version=f"agentgov {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    audit = sub.add_parser(
        "audit", help="Audit an agent manifest (.yaml), LangGraph code (.py), or a trace (.json)."
    )
    audit.add_argument(
        "manifest",
        help="Path to an agent manifest (.yaml), LangGraph source (.py), or run trace (.json).",
    )
    audit.add_argument(
        "--code", action="store_true",
        help="Force treating the input as LangGraph source (auto-detected for .py).",
    )
    audit.add_argument(
        "--trace", action="store_true",
        help="Force treating the input as a LangSmith-style trace (auto-detected for .json).",
    )
    audit.add_argument(
        "--full", action="store_true",
        help="Show the full reasoning for each finding (default is a short table).",
    )
    audit.add_argument(
        "-o", "--output", help="Write the Markdown report to a file instead of stdout."
    )
    audit.set_defaults(func=_cmd_audit)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
