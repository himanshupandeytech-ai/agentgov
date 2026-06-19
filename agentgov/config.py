"""Runtime configuration - which knowledge backend to use.

Default is the offline YAML corpus, so the tool always runs with no infrastructure.
Set AGENTGOV_BACKEND=db (with the docker-compose stack up) to use the databases
once that backend is wired.
"""

from __future__ import annotations

import os


def backend() -> str:
    return os.environ.get("AGENTGOV_BACKEND", "yaml").lower()
