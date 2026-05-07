# Multi-Agent Orchestration: Code Samples

Selected code samples from a production multi-agent system. Six specialized agents handle daily intelligence gathering, content drafting, publishing review, and operational monitoring. The system runs real work — not a research prototype.

The dashboard supervises agents running on the [OpenClaw](https://github.com/openclaw/openclaw) runtime: tracking performance, reconciling LLM costs across providers, and surfacing failure modes without grepping logs.

The production system is ~25,000 lines of Python and JavaScript. This repo is a curated subset — selected files that demonstrate specific patterns, not a deployable framework. Zero external runtime dependencies in any of these patterns (Python stdlib + bash + AppleScript only).

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Dashboard (vanilla JS / Python HTTP server)            │
│  • weekly schedule calendar (overlap-aware lanes)       │
│  • per-provider cost reconciliation + monthly ledger    │
│  • capability conflict detector (config drift alarms)   │
│  • SSE auto-update on workspace file change             │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────┴──────────────────────────────┐
│  Orchestration Server                                   │
│  • cron + launchd schedule reconciliation               │
│  • subprocess wrapper with dual kill rules              │
│  • model-fallback dispatcher                            │
│  • run_tracker → operator rating loop → weekly memo     │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────┴──────────────────────────────┐
│  MCP Server (stdio transport)                           │
│  • cross-skill tools: run_scan, qualify, smart_dedup,   │
│    weekly_report, cleanup, scan_status, send_email      │
│  • 30-day SQLite dedup window                           │
│  • output-contract URL validation before LLM spend      │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────┴──────────────────────────────┐
│  Scanners (4 generic source adapters)                   │
│  Browser-automation + API hybrids, Gemini quality       │
│  filtering, common-schema normalization                 │
└─────────────────────────────────────────────────────────┘
```

## What's in Each Folder

**`mcp-server/`** Stdio-transport MCP server that exposes 7 tools shared across all scanner skills. Demonstrates: subprocess orchestration, parallel execution with stagger, SQLite-backed cross-skill dedup, output-contract enforcement at the qualify boundary, and per-platform success criteria.

**`quality-gates/`** Three independent validators that run in sequence: (1) **output_contract** — URL-shape regex per source-type, drops malformed rows before they enter the dedup table or burn LLM tokens; (2) **artifact_gate** — schema validator that fails loud, never silently mutates, returns tri-state (pass / uncertain / fail); (3) **hallucination_validator** — LLM-judge with three supervision levels and static issue severities the judge can't game.

**`skill-rating-eval/`** Operator-driven skill quality eval. Every skill execution writes to an append-only `runs.jsonl`. Each evening, an agent computes the unrated set (today's runs + carryovers), sends one chat message per item via the messaging app's bot API with a 1-5 star inline keyboard, polls callbacks, batch-records the ratings, and writes a daily digest. Sunday: a weekly memo aggregates by `(skill, platform)`, surfaces buckets below 3.0★, emails the report. The pattern decouples "did the skill run?" from "did it actually help?".

**`model-fallback/`** Bash wrapper that detects the failure pattern "primary model dies in <180s with <200B output" and auto-retries on a configurable fallback model, logging a `model_fallback` event to a structured jsonl for the weekly memo. Catches the pattern where a primary endpoint times out without surfacing a real error.

**`cost-optimization/`** Three independently-deployable patterns: (1) prompt-cache wiring with `cache_control: ephemeral` for Anthropic system prompts; (2) model-aware batch sizing (smaller chunks for verbose JSON-emitting models, larger for terse ones); (3) cross-skill SQLite dedup that lets multiple scanners share a single 30-day "seen URLs" cache. Plus a config-as-source-of-truth pattern that derives runtime model assignments from a markdown table parsed at request time, eliminating hardcoded drift.

**`scan-pipeline/`** Generic source-runner that normalizes outputs from any scanner into a common schema. Gemini-based qualification with deterministic fallback. Demonstrates: per-source success thresholds, dedup-aware batching, and the qualify pipeline's three-stage funnel (URL contract → 30-day dedup → LLM relevance).

**`agent-orchestration/`** The scheduling engine: conflict-free time slots, dual-kill watchdog (absolute timeout AND output-stall detection — agents get a 60s grace warning to flush partial work before a hard kill), and bot operational status classification.

**`dashboard-visualization/`** Single-page dashboard with weekly calendar (overlap-aware lane assignment, live "Now" line), per-provider cost reconciliation across providers, and execution timeline with agent run history.

**`knowledge-base/`** Markdown-first KB with formal ingest, qualification, and promotion pipelines. Layered architecture: immutable `sources/` → `raw/` intake buffer → maintained `wiki/` → durable `output/`. Every signal is explicitly accepted, rejected, or deferred with an audit trail.

## Engineering patterns demonstrated

- **MCP server architecture for tool consolidation.** When five skills duplicated the same `dedup → qualify → write CSV` loop, the duplication moved to one server with seven tools. Each skill became a thin client.
- **Tri-state quality gates.** Pass / uncertain / fail beats boolean. "Uncertain" triggers a soft warning + retry suggestion without blocking the pipeline.
- **Output contract before LLM spend.** Regex-validating URL shape per source-type drops fabricated outputs in microseconds, before they hit the dedup cache or the qualifier model. Gates aren't expensive when they run first.
- **Operator rating loop.** The system can't grade its own quality. A 1-5 star tap from the operator each evening, accumulated weekly, is the only signal that survives "skill ran without errors but produced nothing useful."
- **Source-of-truth config files.** Model assignments live in a markdown table, parsed at request time. Editing the table moves the dashboard. No hardcoded model strings in Python that drift from intent.
- **Dual-kill subprocess wrapper.** Wall-time timeout AND output-stall detector. A 90-min skill that goes silent at minute 4 gets a graceful nudge to save partial work, then a hard kill at minute 5 — not a wasted hour.
- **Cross-skill state sharing via MCP.** A 30-day SQLite dedup window queryable by every scanner. When skill A qualifies a URL, skill B sees it instantly without re-fetching.
- **Model-fallback as infrastructure, not workflow.** When a primary endpoint times out, the dispatcher transparently retries on a fallback and tags the run record with `model_actual`. Operators don't manually escalate; the weekly memo surfaces fallback drift.

## Technical Choices

- Zero external runtime dependencies — Python stdlib + bash + AppleScript
- Markdown-first config (diff-friendly, parseable by both humans and LLMs)
- File-based state (JSON / JSONL / SQLite — inspectable, versionable)
- macOS-native integrations (AppleScript for email, launchd for scheduling)
- Stdio-transport MCP servers (no extra processes, no port conflicts)

## License

Code samples — released for review and reference, not as a deployable framework. Adapt freely.
