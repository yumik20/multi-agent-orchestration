# Decisions

Architecture Decision Records (ADRs) — one per major design choice that wasn't obvious. Each captures the actual production iteration that drove the decision: what failed, what was tried, what was kept, and what we'd do differently in retrospect.

The single-shot commit history of this repo can hide the iteration that produced these patterns. The ADRs are the iteration's receipts.

| ADR | Decision |
|---|---|
| [001](001-mcp-over-shared-library.md) | MCP server over a shared Python library for cross-skill tools |
| [002](002-operator-rating-over-llm-self-eval.md) | Operator rating loop over LLM self-evaluation |
| [003](003-sqlite-over-json-dedup.md) | SQLite over JSON files for the dedup cache |
| [004](004-dual-kill-over-single-timeout.md) | Dual-kill watchdog (output stall AND wall-time) over a single absolute timeout |
| [005](005-markdown-config-over-yaml.md) | Markdown table config over YAML for runtime model assignments |

## Format

```
# ADR-NNN: <one-line decision>

## Context
What was happening, what hurt.

## Options considered
What we looked at and rejected.

## Decision
What we picked and why.

## Consequences
What we now have to live with.

## What we'd do differently
Honest retrospective.
```
