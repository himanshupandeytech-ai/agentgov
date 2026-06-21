"""Policy enforcement: thresholds, waivers (incl. expiry), and the audit register."""

import json

from agentgov.detectors import Finding
from agentgov.governance import apply_policy, audit_entry, record, render_decision


def _scored(pattern_id, score, nodes=("n",)):
    return {"finding": Finding(pattern_id, "high", list(nodes), "e"), "score": score, "pattern_id": pattern_id}


def test_high_score_blocks():
    res = apply_policy([_scored("injection_to_exfiltration", 95)], {"block_at_score": 70})
    assert res["decision"] == "block"
    assert res["blocking"][0]["pattern"] == "injection_to_exfiltration"


def test_below_threshold_passes():
    res = apply_policy([_scored("missing_oversight_instrumentation", 32)], {"block_at_score": 70})
    assert res["decision"] == "pass"


def test_active_waiver_clears_block():
    policy = {
        "block_at_score": 70,
        "waivers": [{"pattern": "injection_to_exfiltration", "reason": "accepted", "expires": "2099-01-01"}],
    }
    res = apply_policy([_scored("injection_to_exfiltration", 95)], policy, today="2026-06-19")
    assert res["decision"] == "pass"
    assert res["waived"][0]["pattern"] == "injection_to_exfiltration"


def test_expired_waiver_does_not_apply():
    policy = {
        "block_at_score": 70,
        "waivers": [{"pattern": "injection_to_exfiltration", "reason": "old", "expires": "2025-01-01"}],
    }
    res = apply_policy([_scored("injection_to_exfiltration", 95)], policy, today="2026-06-19")
    assert res["decision"] == "block"


def test_owner_assigned_to_blocking_finding():
    policy = {"block_at_score": 70, "owners": {"injection_to_exfiltration": "security-team"}}
    res = apply_policy([_scored("injection_to_exfiltration", 95)], policy)
    assert res["blocking"][0]["owner"] == "security-team"


def test_audit_register_appends_jsonl(tmp_path):
    scored = [_scored("injection_to_exfiltration", 95)]
    res = apply_policy(scored, {"block_at_score": 70})
    log = tmp_path / "audit.jsonl"
    record(audit_entry("demo.py", scored, res), log)
    record(audit_entry("demo.py", scored, res), log)
    lines = log.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["decision"] == "block"


def test_render_decision_contains_verdict():
    res = apply_policy([_scored("injection_to_exfiltration", 95)], {"block_at_score": 70})
    assert "BLOCK" in render_decision("demo.py", res)
