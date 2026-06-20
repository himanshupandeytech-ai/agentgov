"""Load the governance corpus into Postgres (pgvector) and Neo4j.

Run once after `docker compose up`:

    uv run --extra db python -m agentgov.ingest

Postgres holds obligations (with embeddings of their text) and the controls
catalog. Neo4j holds the graph: RiskPattern -[:VIOLATES]-> Obligation and
Control -[:SATISFIES]-> Obligation, plus RiskPattern -[:MITIGATED_BY]-> Control.
The data is tiny, so this is idempotent: it drops and rebuilds each run.
"""

from __future__ import annotations

from .config import EMBED_DIM, database_url, neo4j_config
from .embed import embed
from .knowledge import YamlKnowledgeStore


def _obligations(store: YamlKnowledgeStore) -> dict[str, dict]:
    """Build obligation records for the whole corpus, keyed by FRAMEWORK:ref.

    Covers every framework entry (not only the ones a detector references), so
    semantic search spans the full corpus.
    """
    fw = store.frameworks()
    obligations: dict[str, dict] = {}

    def add(framework: str, ref: str, title: str, summary: str) -> None:
        key = f"{framework}:{ref}"
        obligations[key] = {
            "key": key, "framework": framework, "ref": ref,
            "title": title, "summary": summary,
            "text": f"{ref} {title}. {summary}",
        }

    for ref, text in fw["nist"].get("subcategories", {}).items():
        add("NIST_AI_RMF", ref, ref, text)
    for ref, meta in fw["eu_ai_act"].get("articles", {}).items():
        add("EU_AI_ACT", ref, meta.get("title", ref), meta.get("summary", ""))
    for ref, text in fw["inspect"].get("categories", {}).items():
        add("INSPECT", ref, ref, text)
    return obligations


def load_postgres(store: YamlKnowledgeStore, obligations: dict[str, dict]) -> int:
    import psycopg
    from pgvector.psycopg import register_vector

    conn = psycopg.connect(database_url())
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    register_vector(conn)
    conn.execute("DROP TABLE IF EXISTS control")
    conn.execute("DROP TABLE IF EXISTS obligation")
    conn.execute(
        f"""CREATE TABLE obligation (
            key text PRIMARY KEY, framework text, ref text,
            title text, summary text, embedding vector({EMBED_DIM}))"""
    )
    conn.execute(
        """CREATE TABLE control (
            key text PRIMARY KEY REFERENCES obligation(key),
            control text, action text, why text)"""
    )
    for o in obligations.values():
        conn.execute(
            "INSERT INTO obligation (key, framework, ref, title, summary, embedding) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (o["key"], o["framework"], o["ref"], o["title"], o["summary"], embed(o["text"])),
        )
    n_controls = 0
    for key, c in store._controls.items():
        if key in obligations:
            conn.execute(
                "INSERT INTO control (key, control, action, why) VALUES (%s, %s, %s, %s)",
                (key, c["control"], c["action"], c["why"]),
            )
            n_controls += 1
    conn.commit()
    conn.close()
    return n_controls


def load_neo4j(store: YamlKnowledgeStore, obligations: dict[str, dict]) -> None:
    from neo4j import GraphDatabase

    uri, user, pwd = neo4j_config()
    driver = GraphDatabase.driver(uri, auth=(user, pwd))
    with driver.session() as s:
        s.run("MATCH (n) DETACH DELETE n")
        for o in obligations.values():
            s.run(
                """MERGE (f:Framework {name:$fw})
                   MERGE (o:Obligation {key:$key})
                   SET o.ref=$ref, o.title=$title, o.summary=$summary
                   MERGE (o)-[:IN]->(f)""",
                fw=o["framework"], key=o["key"], ref=o["ref"],
                title=o["title"], summary=o["summary"],
            )
        for key, c in store._controls.items():
            if key in obligations:
                s.run(
                    """MATCH (o:Obligation {key:$key})
                       MERGE (c:Control {key:$key})
                       SET c.control=$control, c.action=$action, c.why=$why
                       MERGE (c)-[:SATISFIES]->(o)""",
                    key=key, control=c["control"], action=c["action"], why=c["why"],
                )
        for pattern in store.patterns():
            s.run(
                "MERGE (r:RiskPattern {id:$id}) SET r.title=$title, r.severity=$sev",
                id=pattern["id"], title=pattern["title"], sev=pattern.get("severity", ""),
            )
            for t in pattern.get("triggers", []):
                key = f"{t['framework']}:{t['ref']}"
                s.run(
                    """MATCH (r:RiskPattern {id:$id}), (o:Obligation {key:$key})
                       MERGE (r)-[:VIOLATES]->(o)""",
                    id=pattern["id"], key=key,
                )
                s.run(
                    """MATCH (r:RiskPattern {id:$id}), (c:Control {key:$key})
                       MERGE (r)-[:MITIGATED_BY]->(c)""",
                    id=pattern["id"], key=key,
                )
    driver.close()


def main() -> None:
    store = YamlKnowledgeStore()
    obligations = _obligations(store)
    n_controls = load_postgres(store, obligations)
    load_neo4j(store, obligations)
    print(
        f"ingested {len(obligations)} obligations + {n_controls} controls "
        f"into Postgres (pgvector) and Neo4j"
    )


if __name__ == "__main__":
    main()
