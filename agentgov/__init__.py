"""agentgov - static governance auditor for the agent orchestration layer.

Inspect/METR evaluate the *model*. agentgov audits the *system built around it*:
the tools, edges, permissions, and oversight wiring of a deep agent - and maps
each structural risk to real obligations in NIST AI RMF, the EU AI Act, and the
Inspect ecosystem.

Input is a declarative YAML manifest (never executed), the governance corpus is
YAML, and output is a Markdown report. The corpus is loaded through a single seam
(loader.py), so a vector/graph/relational DB can replace the YAML backing later
with no change to the detectors or report.
"""

__version__ = "0.1.0"
