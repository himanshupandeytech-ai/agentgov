"""Runtime configuration - which knowledge backend to use.

Default is the offline YAML corpus, so the tool always runs with no infrastructure.
Set AGENTGOV_BACKEND=db (with the docker-compose stack up) to use the databases
once that backend is wired.
"""

from __future__ import annotations

import os


def backend() -> str:
    return os.environ.get("AGENTGOV_BACKEND", "yaml").lower()


def database_url() -> str:
    return os.environ.get(
        "DATABASE_URL", "postgresql://agentgov:agentgov@localhost:55432/governance"
    )


def neo4j_config() -> tuple[str, str, str]:
    return (
        os.environ.get("NEO4J_URI", "bolt://localhost:17688"),
        os.environ.get("NEO4J_USER", "neo4j"),
        os.environ.get("NEO4J_PASSWORD", "agentgovpass"),
    )


# Embedding model: small, local, offline. 384-dim vectors.
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBED_DIM = 384
