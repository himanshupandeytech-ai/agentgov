"""Guard detector accuracy: the benchmark must stay at perfect precision/recall."""

from pathlib import Path

from agentgov.benchmark import evaluate, load_cases

CASES = Path(__file__).resolve().parent.parent / "benchmark" / "cases.yaml"


def test_benchmark_precision_recall_perfect():
    metrics = evaluate(load_cases(CASES))
    assert metrics["fp"] == 0, f"false positives: {metrics['per_case']}"
    assert metrics["fn"] == 0, f"false negatives: {metrics['per_case']}"
    assert metrics["precision"] == 1.0
    assert metrics["recall"] == 1.0


def test_sanitiser_blocks_injection_finding():
    cases = {c["name"]: c for c in load_cases(CASES)}
    metrics = evaluate([cases["injection_but_sanitised"]])
    assert metrics["fp"] == 0  # taint analysis must not flag a sanitised path
