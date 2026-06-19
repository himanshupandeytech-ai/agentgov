"""The knowledge layer resolves risks to obligations and catalog controls."""

from agentgov.knowledge import YamlKnowledgeStore, get_store


def test_store_loads_patterns_and_controls():
    store = YamlKnowledgeStore()
    assert store.pattern("unsupervised_external_write") is not None
    assert store.controls_for("EU_AI_ACT", "Article 14(4)") is not None


def test_resolve_joins_obligation_to_control_and_action():
    store = YamlKnowledgeStore()
    resolved = store.resolve("unsupervised_external_write")
    assert resolved, "expected at least one mapped obligation"
    control = next(r["control"] for r in resolved if r["ref"] == "Article 14(4)")
    assert "approval" in control["action"].lower()
    assert control["why"]


def test_every_trigger_has_a_catalog_entry():
    # Each obligation referenced by a pattern should resolve to a control.
    store = YamlKnowledgeStore()
    missing = []
    for pattern in store.patterns():
        for trig in pattern.get("triggers", []):
            if store.controls_for(trig["framework"], trig["ref"]) is None:
                missing.append(f"{trig['framework']}:{trig['ref']}")
    assert not missing, f"controls catalog missing entries: {missing}"


def test_full_report_renders_control_and_action():
    from agentgov.detectors import run_detectors
    from agentgov.loader import load_corpus
    from agentgov.report import render_markdown

    agent = {
        "name": "t",
        "nodes": [{"id": "transfer_funds", "external_action": True, "human_in_loop": False}],
        "edges": [],
        "oversight": {"kill_switch": False, "audit_log": False},
    }
    corpus = load_corpus()
    md = render_markdown(agent, run_detectors(agent), corpus)
    assert "Required control and action." in md
    assert "approval" in md.lower()


def test_unknown_backend_raises():
    try:
        get_store("nonsense")
    except NotImplementedError:
        return
    raise AssertionError("expected NotImplementedError for an unknown backend")
