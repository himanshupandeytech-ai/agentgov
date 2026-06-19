"""Loading seam for the governance corpus and the agent manifest.

This module is the storage-agnostic boundary. Today both the corpus and the
agent manifest are YAML; tomorrow `load_corpus` can read from Postgres+pgvector
(semantic clause search), a graph DB (cross-framework relationships), or a REST
API - with zero change to `detectors.py` or `report.py`. The rest of the tool
only ever sees plain dicts.

Security: `yaml.safe_load` only (no arbitrary object construction), and the
agent manifest is *data*, never imported or executed.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml


def _read_packaged(name: str) -> Any:
    """Read a YAML file bundled inside the agentgov.corpus package."""
    text = (files("agentgov.corpus") / name).read_text(encoding="utf-8")
    return yaml.safe_load(text)


def load_corpus() -> dict[str, Any]:
    """Return the governance corpus as plain dicts.

    Swap the body of this function to change the backing store. The returned
    shape is the contract the rest of the tool depends on.
    """
    return {
        "risk_patterns": _read_packaged("risk_patterns.yaml"),
        "nist": _read_packaged("nist.yaml"),
        "eu_ai_act": _read_packaged("eu_ai_act.yaml"),
    }


def load_agent(manifest_path: str | Path) -> dict[str, Any]:
    """Load a declarative agent manifest from disk. Never executed."""
    path = Path(manifest_path)
    if not path.is_file():
        raise FileNotFoundError(f"Agent manifest not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Agent manifest must be a YAML mapping, got {type(data).__name__}")
    return data
