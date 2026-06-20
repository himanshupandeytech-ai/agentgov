"""KnowledgeStore backed by Postgres (pgvector) and Neo4j.

Same interface as YamlKnowledgeStore, so detectors and report are unchanged. Two
capabilities YAML cannot provide:
  * semantic_match() - nearest obligations to a free-text risk via pgvector
  * resolve() - risk -> obligation -> control by graph traversal in Neo4j

Risk patterns (the detector rules + reasoning) stay in YAML; the regulatory
content (obligations, controls, framework text) is served from the databases.
"""

from __future__ import annotations

from typing import Any

from .config import database_url, neo4j_config
from .embed import embed
from .knowledge import YamlKnowledgeStore

_NIST = "NIST AI RMF 1.0"
_EU = "Regulation (EU) 2024/1689 (EU AI Act)"


class DbKnowledgeStore:
    def __init__(self) -> None:
        import psycopg
        from neo4j import GraphDatabase
        from pgvector.psycopg import register_vector

        self._pg = psycopg.connect(database_url())
        register_vector(self._pg)
        uri, user, pwd = neo4j_config()
        self._neo = GraphDatabase.driver(uri, auth=(user, pwd))
        self._yaml = YamlKnowledgeStore()  # patterns + meta live in YAML

    # -- pattern rules stay in YAML --
    def meta(self) -> dict[str, Any]:
        return self._yaml.meta()

    def patterns(self) -> list[dict[str, Any]]:
        return self._yaml.patterns()

    def pattern(self, pattern_id: str) -> dict[str, Any] | None:
        return self._yaml.pattern(pattern_id)

    # -- regulatory content from Postgres --
    def controls_for(self, framework: str, ref: str) -> dict[str, Any] | None:
        row = self._pg.execute(
            "SELECT control, action, why FROM control WHERE key = %s",
            (f"{framework}:{ref}",),
        ).fetchone()
        return {"control": row[0], "action": row[1], "why": row[2]} if row else None

    def frameworks(self) -> dict[str, Any]:
        rows = self._pg.execute(
            "SELECT framework, ref, title, summary FROM obligation"
        ).fetchall()
        nist = {"framework": _NIST, "subcategories": {}}
        eu = {"regulation": _EU, "articles": {}}
        for framework, ref, title, summary in rows:
            if framework == "NIST_AI_RMF":
                nist["subcategories"][ref] = summary
            elif framework == "EU_AI_ACT":
                eu["articles"][ref] = {"title": title, "summary": summary}
        return {"nist": nist, "eu_ai_act": eu}

    # -- graph traversal in Neo4j --
    def resolve(self, pattern_id: str) -> list[dict[str, Any]]:
        cypher = """
            MATCH (r:RiskPattern {id:$id})-[:VIOLATES]->(o:Obligation)
            OPTIONAL MATCH (c:Control)-[:SATISFIES]->(o)
            RETURN o.key AS key, o.ref AS ref, o.title AS title,
                   c.control AS control, c.action AS action, c.why AS why
        """
        out = []
        with self._neo.session() as s:
            for rec in s.run(cypher, id=pattern_id):
                framework = (rec["key"] or ":").split(":", 1)[0]
                control = (
                    {"control": rec["control"], "action": rec["action"], "why": rec["why"]}
                    if rec["control"]
                    else None
                )
                out.append({"framework": framework, "ref": rec["ref"], "control": control})
        return out

    # -- semantic search (pgvector) --
    def semantic_match(self, text: str, k: int = 3) -> list[dict[str, Any]]:
        vec = "[" + ",".join(repr(x) for x in embed(text)) + "]"
        rows = self._pg.execute(
            """SELECT key, framework, ref, title, 1 - (embedding <=> %s::vector) AS score
               FROM obligation ORDER BY embedding <=> %s::vector LIMIT %s""",
            (vec, vec, k),
        ).fetchall()
        results = []
        for key, framework, ref, title, score in rows:
            c = self.controls_for(framework, ref)
            results.append(
                {
                    "key": key, "framework": framework, "ref": ref, "title": title,
                    "score": round(float(score), 3),
                    "action": c["action"] if c else None,
                }
            )
        return results

    # -- corpus dict the report consumes --
    def as_corpus(self) -> dict[str, Any]:
        controls = {}
        rows = self._pg.execute("SELECT key, control, action, why FROM control").fetchall()
        for key, control, action, why in rows:
            controls[key] = {"control": control, "action": action, "why": why}
        fw = self.frameworks()
        return {
            "risk_patterns": self._yaml._patterns_doc,
            "controls": controls,
            "nist": fw["nist"],
            "eu_ai_act": fw["eu_ai_act"],
        }
