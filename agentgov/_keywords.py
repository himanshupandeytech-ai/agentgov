"""Shared, auditable keyword classification for tool/node names.

Both the trace reader and the code reader infer a node's capability from its name
(e.g. `send_email` acts on the outside world; `web_search` ingests untrusted
content). Kept deliberately simple and in one place so a reviewer can audit and
extend the word lists without touching detector logic.
"""

from __future__ import annotations

# A node whose name implies it performs an outbound / irreversible action.
ACTION_WORDS = (
    "send", "email", "post", "write", "delete", "exec", "execute", "payment",
    "pay", "create", "update", "deploy", "transfer", "insert", "put", "publish",
)

# A node whose name implies it ingests untrusted outside content.
INPUT_WORDS = (
    "search", "browse", "fetch", "get", "retriev", "web", "scrape", "read",
    "crawl", "load_url", "lookup", "http",
)


def classify_tool(name: str) -> dict[str, bool]:
    """Return capability flags inferred from a tool/node name."""
    low = name.lower()
    return {
        "external_action": any(w in low for w in ACTION_WORDS),
        "consumes_external": any(w in low for w in INPUT_WORDS),
    }
