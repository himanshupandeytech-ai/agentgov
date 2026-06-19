"""The knowledge layer: resolve a risk to obligations, controls, and actions.

`KnowledgeStore` is the single seam between agentgov's checks and the governance
knowledge. Today the backing store is YAML (`YamlKnowledgeStore`); a database
backend (Postgres + pgvector for semantic clause search, Neo4j for the
risk -> obligation -> control graph) can implement the same interface later with
no change to the detectors or the report.

The interface is intentionally small:
  * pattern(pattern_id)      -> the risk pattern record
  * controls_for(ref)        -> the catalog control/action/why for an obligation
  * resolve(pattern_id)      -> obligations each joined to its control + action
"""

from __future__ import annotations

from importlib.resources import files
from typing import Any, Protocol

import yaml


def _read_packaged(name: str) -> Any:
    text = (files("agentgov.corpus") / name).read_text(encoding="utf-8")
    return yaml.safe_load(text)


class KnowledgeStore(Protocol):
    def pattern(self, pattern_id: str) -> dict[str, Any] | None: ...
    def controls_for(self, framework: str, ref: str) -> dict[str, Any] | None: ...
    def resolve(self, pattern_id: str) -> list[dict[str, Any]]: ...
    def frameworks(self) -> dict[str, Any]: ...


class YamlKnowledgeStore:
    """KnowledgeStore backed by the packaged YAML corpus."""

    def __init__(self) -> None:
        self._patterns_doc = _read_packaged("risk_patterns.yaml")
        self._controls = _read_packaged("controls.yaml").get("controls", {})
        self._nist = _read_packaged("nist.yaml")
        self._eu = _read_packaged("eu_ai_act.yaml")
        self._by_id = {p["id"]: p for p in self._patterns_doc["patterns"]}

    def meta(self) -> dict[str, Any]:
        return self._patterns_doc.get("meta", {})

    def patterns(self) -> list[dict[str, Any]]:
        return self._patterns_doc["patterns"]

    def pattern(self, pattern_id: str) -> dict[str, Any] | None:
        return self._by_id.get(pattern_id)

    def controls_for(self, framework: str, ref: str) -> dict[str, Any] | None:
        return self._controls.get(f"{framework}:{ref}")

    def resolve(self, pattern_id: str) -> list[dict[str, Any]]:
        """Each mapped obligation, joined to its catalog control + action."""
        pattern = self.pattern(pattern_id)
        if not pattern:
            return []
        resolved: list[dict[str, Any]] = []
        for trig in pattern.get("triggers", []):
            control = self.controls_for(trig["framework"], trig["ref"])
            resolved.append({**trig, "control": control})
        return resolved

    def frameworks(self) -> dict[str, Any]:
        return {"nist": self._nist, "eu_ai_act": self._eu}

    def as_corpus(self) -> dict[str, Any]:
        return {
            "risk_patterns": self._patterns_doc,
            "controls": self._controls,
            "nist": self._nist,
            "eu_ai_act": self._eu,
        }


def get_store(backend: str = "yaml") -> KnowledgeStore:
    """Return a KnowledgeStore. 'yaml' is offline; 'db' uses Postgres + Neo4j."""
    if backend == "yaml":
        return YamlKnowledgeStore()
    if backend == "db":
        from .db_store import DbKnowledgeStore

        return DbKnowledgeStore()
    raise NotImplementedError(f"unknown backend '{backend}'")
