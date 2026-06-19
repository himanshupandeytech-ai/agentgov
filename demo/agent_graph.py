"""Sample deep agent written with LangGraph.

agentgov audits this file STATICALLY (it reads the source, it never runs it). The
graph intentionally wires untrusted web content toward an email action, but also
declares a human-approval gate on the email node via `interrupt_before`. The audit
should therefore:
  - CLEAR the "unsupervised external write" finding (the approval gate is credited), and
  - still RAISE the "prompt-injection -> exfiltration" finding (an approval gate
    does not sanitise the untrusted content flowing into the action).

This file is illustrative; it does not need langgraph installed to be audited.
"""

from langgraph.graph import START, END, StateGraph


def web_search(state):
    """Fetch untrusted content from the open web."""
    return state


def summarize(state):
    """LLM step that summarises the search results."""
    return state


def send_email(state):
    """Outbound, irreversible action: emails the summary to a stakeholder."""
    return state


def build():
    builder = StateGraph(dict)
    builder.add_node("web_search", web_search)
    builder.add_node("summarize", summarize)
    builder.add_node("send_email", send_email)

    builder.add_edge(START, "web_search")
    builder.add_edge("web_search", "summarize")
    builder.add_edge("summarize", "send_email")
    builder.add_edge("send_email", END)

    # Human-approval gate on the outbound action (a control written in code).
    return builder.compile(interrupt_before=["send_email"])


graph = build()
