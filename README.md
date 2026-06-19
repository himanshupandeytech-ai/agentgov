# agentgov

**A static governance auditor for the agent orchestration layer.**

Inspect and METR evaluate the *model*. As enterprises deploy deep agents, risk
shifts to the **orchestration layer** - the tools, edges, permissions, autonomy,
and oversight wiring built *around* the model. Almost nothing audits that.
`agentgov` does: point it at a declarative agent manifest and it emits a
**Governance Audit Report** that maps each structural risk to real obligations in
the **NIST AI RMF**, the **EU AI Act**, and the **Inspect** ecosystem - with the
reasoning a regulator or risk owner needs to act.

> Behavioral/capability testing is out of scope and hands off to
> [Inspect](https://inspect.aisi.org.uk). agentgov audits *structure*, not model
> behavior - it never executes the target agent.

## Quickstart (uv)

No install - run it straight from the repo with [uv](https://docs.astral.sh/uv/):

```bash
uv run agentgov audit demo/agent.yaml            # DESIGN  -> runaway delegation loop
uv run agentgov audit demo/agent_graph.py        # BUILD   -> injection path in the code
uv run agentgov audit demo/trace_langsmith.json  # RUNTIME -> unapproved money transfer
uv run agentgov audit demo/agent_safe.yaml       # CLEAN   -> nothing (controls applied)

uv run agentgov audit demo/agent.yaml --full     # add --full for the reasoning
uv run agentgov audit demo/agent.yaml -o out.md  # or write the report to a file
```

Input type is auto-detected: `.yaml` = manifest, `.py` = LangGraph code, `.json` = run trace.

**Three ways to describe an agent - one per lifecycle phase:**
- **Manifest (`.yaml`)** - what the agent is *meant* to do. For design review.
- **LangGraph code (`.py`)** - what the agent was actually *built* as. Read statically
  (never executed). For a pre-deploy / CI check.
- **Run trace (`.json`)** - what the agent *actually did* on a run. For runtime monitoring
  and audit. The report states what a trace can and can't show (approvals and oversight
  wiring aren't always recorded), so it never over-claims.

Or install as a tool:

```bash
uv tool install .          # then: agentgov audit demo/agent.yaml
```

Run the tests:

```bash
uv run pytest -q
```

## How it works

```
demo/agent.yaml ─▶ loader ─▶ detectors ─▶ report ─▶ Markdown
   (manifest)      (seam)    (engine)   (judgment)
```

- **`loader.py`** - the storage-agnostic seam. Corpus + manifest are YAML today;
  a vector DB (semantic clause search), graph DB (cross-framework relationships),
  or REST API can replace it with **zero change** to detectors or report.
- **`detectors.py`** - static, deterministic risk detectors over the manifest.
  Four checks ship; the corpus is written to extend to more.
- **`corpus/*.yaml`** - the governance knowledge: risk patterns mapped to NIST /
  EU obligations, with the causal reasoning, severity, context-dependence, and
  framework gaps living in data (auditable by a non-programmer reviewer).
- **`report.py`** - composes findings + corpus into the Markdown audit.

### The agent manifest

A manifest is **data**, never code. It declares nodes, their permissions, the
edges between them, and the oversight controls:

```yaml
nodes:
  - id: web_search
    consumes_external: true     # ingests untrusted outside content
    external_action: false
    human_in_loop: false
  - id: send_email
    external_action: true       # irreversible outbound action
    human_in_loop: false        # no approval gate
edges:
  - { from: web_search, to: send_email }
oversight: { kill_switch: false, audit_log: false }
```

## What it detects (v1)

| Pattern | Maps to |
|---|---|
| Unsupervised external write / irreversible action | EU Art. 14(4) · NIST MANAGE-2.3 |
| Prompt-injection → exfiltration path | EU Art. 15 · NIST MEASURE-2.7 |
| Unbounded delegation / self-invocation loop | EU Art. 14(4) · NIST MEASURE-2.6 |
| Missing oversight instrumentation (kill-switch / audit log) | EU Art. 12 · NIST GOVERN-1.4 |

### One issue per lifecycle phase

The demos are chosen so each stage catches a *different*, characteristic problem - the
point being that the layers are not redundant:

| Phase | Run | Catches |
|---|---|---|
| Design (read the plan) | `agentgov audit demo/agent.yaml` | architecture flaw: unbounded delegation loop |
| Build (read the code) | `agentgov audit demo/agent_graph.py` | wiring flaw: untrusted web text reaches the email tool |
| Runtime (watch the run) | `agentgov audit demo/trace_langsmith.json` | behaviour flaw: a funds transfer executed with no approval |
| (control sample) | `agentgov audit demo/agent_safe.yaml` | nothing - controls applied, clean pass |

Add `--full` to any of these to see the reasoning behind the finding.

Each finding in the report carries: evidence → causal chain → severity rationale
→ mapped obligations → **system-card tie** → context-dependence (same finding,
different verdict by deployment) → proportionate control → where the frameworks
fall short.

## Design principles

- **Start thin, expand later.** A small end-to-end slice that works today;
  storage and services are added once they earn their place.
- **Secure by construction.** Static-only (never runs the target agent), offline
  (no network), one pinned dependency (`pyyaml`), `yaml.safe_load` only,
  deterministic output.
- **Reasoning lives in data.** The corpus holds the analysis, so the audit is
  editable and reviewable by a non-programmer, not buried in code.

## Data sources & licensing

The corpus is a curated slice of public material, reused within license:

- **NIST AI RMF 1.0** - [NIST AI 100-1](https://nvlpubs.nist.gov/nistpubs/ai/nist.ai.100-1.pdf),
  [Playbook](https://airc.nist.gov/AI_RMF_Knowledge_Base/Playbook). U.S. Government work, public domain.
- **EU AI Act - Regulation (EU) 2024/1689** - [EUR-Lex](https://eur-lex.europa.eu/eli/reg/2024/1689/oj/eng).
  Reused under the Commission reuse policy (Decision 2011/833/EU); summaries are
  paraphrased - cite EUR-Lex for authoritative wording.
- **Inspect (UK AISI)** - [inspect_ai](https://github.com/UKGovernmentBEIS/inspect_ai),
  [inspect_evals](https://github.com/UKGovernmentBEIS/inspect_evals). MIT.

## Roadmap (out of scope for v1, by design)

- Live LangGraph graph introspection (opt-in; v1 takes a declarative manifest).
- Richer trace support (OpenTelemetry / LangGraph checkpoints; data-flow edges, not just timeline).
- More detectors (PII-to-external paths, over-broad tool scopes) - the corpus is written to extend.
- Corpus backend swap: Postgres + pgvector / graph DB behind the existing loader seam.

## License

MIT - see [LICENSE](LICENSE).
