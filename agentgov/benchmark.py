"""Detector accuracy benchmark: precision / recall / F1 over labelled cases.

Run it:

    uv run python -m agentgov.benchmark            # uses benchmark/cases.yaml

Each case carries the pattern ids that should fire. We compare detector output to
those labels, counting findings (not cases) so precision and recall reflect
per-finding accuracy - including the cases designed to test false positives
(a sanitised injection path, a bounded loop).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .detectors import run_detectors


def load_cases(path: str | Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return data["cases"]


def evaluate(cases: list[dict[str, Any]]) -> dict[str, Any]:
    tp = fp = fn = 0
    per_case = []
    for case in cases:
        found = {f.pattern_id for f in run_detectors(case["agent"])}
        expected = set(case.get("expect", []))
        c_tp, c_fp, c_fn = found & expected, found - expected, expected - found
        tp += len(c_tp)
        fp += len(c_fp)
        fn += len(c_fn)
        per_case.append(
            {"name": case["name"], "found": sorted(found), "expected": sorted(expected),
             "false_positives": sorted(c_fp), "false_negatives": sorted(c_fn)}
        )
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "tp": tp, "fp": fp, "fn": fn,
        "precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3),
        "per_case": per_case,
    }


def main() -> None:
    cases_path = Path(__file__).resolve().parent.parent / "benchmark" / "cases.yaml"
    metrics = evaluate(load_cases(cases_path))
    print(f"cases: {len(metrics['per_case'])}")
    print(f"TP={metrics['tp']}  FP={metrics['fp']}  FN={metrics['fn']}")
    print(f"precision={metrics['precision']}  recall={metrics['recall']}  f1={metrics['f1']}")
    for c in metrics["per_case"]:
        flag = "" if not (c["false_positives"] or c["false_negatives"]) else "  <-- MISS"
        print(f"  {c['name']:24} found={c['found']} expected={c['expected']}{flag}")


if __name__ == "__main__":
    main()
