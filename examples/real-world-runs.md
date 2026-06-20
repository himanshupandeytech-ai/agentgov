# agentgov on real public agents

Results of running `agentgov` unmodified against well-known public LangGraph
agents. Each was audited at a pinned commit; nothing in the target repos was
changed.

**Run date: 2026-06-19.** Star counts and commits are as of that date.

---

## gpt-researcher

- Repo: <https://github.com/assafelovic/gpt-researcher> (Apache-2.0)
- Stars: ~27,800
- File: `multi_agents/agents/orchestrator.py`
- Commit: `b364917`

```
$ agentgov audit orchestrator.py

5 finding(s) - High 4, Medium 1, Low 0
```

| # | Severity | Problem | Where | Rule | Fix |
|---|---|---|---|---|---|
| 1 | HIGH | Unsupervised external write / irreversible action | `writer` (orchestrator.py:63 in _create_workflow) | EU Art. 14(4); NIST MANAGE-2.3 | Add a human-approval gate on outbound actions. |
| 2 | HIGH | Unsupervised external write / irreversible action | `publisher` (orchestrator.py:64 in _create_workflow) | EU Art. 14(4); NIST MANAGE-2.3 | Add a human-approval gate on outbound actions. |
| 3 | HIGH | Prompt-injection -> exfiltration path | `researcher` (orchestrator.py:62), `writer` (orchestrator.py:63) | EU Art. 15; NIST MEASURE-2.7 | Isolate/sanitise untrusted tool output before any action node. |
| 4 | HIGH | Prompt-injection -> exfiltration path | `researcher` (orchestrator.py:62), `publisher` (orchestrator.py:64) | EU Art. 15; NIST MEASURE-2.7 | Isolate/sanitise untrusted tool output before any action node. |
| 5 | MEDIUM | Unbounded delegation / self-invocation loop | `human` (orchestrator.py:65), `planner` (orchestrator.py:61) | EU Art. 14(4); NIST MEASURE-2.6 | Declare a max delegation depth / step budget + hard stop. |

---

## react-agent (LangChain official template)

- Repo: <https://github.com/langchain-ai/react-agent> (MIT)
- Stars: ~770
- File: `src/react_agent/graph.py`
- Commit: `ce464dc`

```
$ agentgov audit graph.py

1 finding(s) - High 0, Medium 1, Low 0
```

| # | Severity | Problem | Where | Rule | Fix |
|---|---|---|---|---|---|
| 1 | MEDIUM | Unbounded delegation / self-invocation loop | `call_model` (graph.py:72), `tools` (graph.py:73) | EU Art. 14(4); NIST MEASURE-2.6 | Declare a max delegation depth / step budget + hard stop. |

---

### Reproduce

```bash
# gpt-researcher
curl -sL https://raw.githubusercontent.com/assafelovic/gpt-researcher/b364917/multi_agents/agents/orchestrator.py -o orchestrator.py
uv run agentgov audit orchestrator.py

# react-agent
curl -sL https://raw.githubusercontent.com/langchain-ai/react-agent/ce464dc/src/react_agent/graph.py -o graph.py
uv run agentgov audit graph.py
```

These are illustrative governance findings on real code, not assertions that the
projects are unsafe - each finding names the control and the line to change.
