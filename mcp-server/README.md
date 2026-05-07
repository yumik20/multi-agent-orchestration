# MCP Server: Cross-Skill Tool Consolidation

Stdio-transport MCP server that exposes seven tools shared across scanner skills. Before this existed, each scanner reimplemented the same `dedup → qualify → email` loop with subtle drift. The MCP centralizes the loop in one place.

## Tools

| Tool | Description |
|---|---|
| `run_scan` | Execute scans across N sources in parallel with random stagger. SQLite run-tracking, per-source timeouts, partial-success aggregation. |
| `qualify` | Three-stage funnel on raw scan output: URL contract → 30-day dedup → LLM relevance. Returns qualified + unqualified CSVs and dedup stats. |
| `smart_dedup` | Given a list of URLs, returns which were already seen by ANY scan in the rolling 30-day window. Lets cross-skill flows avoid re-fetching. |
| `weekly_report` | Roll up the past 7 days of qualified results, dedup by URL, return a single CSV plus summary numbers. |
| `cleanup` | Delete scan artifacts older than the retention window (default 31 days). Also prunes the dedup table. |
| `scan_status` | Query SQLite run history. Filter by run_group, today-only flag, or platform. |
| `send_email` | Mail.app AppleScript wrapper that attaches a CSV and sends the result. |

## Files

- `mcp_server.py` — main server. ~700 lines. Implements all seven tools. Stdio JSON-RPC. The dedup primitive (SQLite, 30-day window) is inline; the URL-shape validators it calls live in [`../quality-gates/output_contract.py`](../quality-gates/output_contract.py).

## Why a server, not a library

Skills live in different language runtimes (some Python, some bash-orchestrated). An MCP server with stdio transport works for all of them, runs as a subprocess (no port conflicts, no stale daemon), and lets each skill stay thin.

## Design choices

**Output contract before LLM call.** A regex check that takes microseconds runs before any 30¢ Haiku batch. Drops fabricated `https://example.com/post/abc` URLs (an LLM hallucination pattern) before they're qualified, deduped, or stored.

**SQLite dedup, not JSON.** The previous JSON cache was rewritten on every update; with thousands of URLs across four sources, that became a bottleneck. SQLite with `PRAGMA journal_mode=WAL` writes incrementally, queries with platform/recency indices in microseconds.

**Per-source success thresholds.** Some sources reliably yield 8 qualified rows, others 5. The thresholds live in `MIN_ROWS = {"source-a": 8, "source-b": 8, "source-c": 5, ...}` and inform the partial / success / failure classification per run.

**Parallel execution with stagger.** Scanners launch in parallel (independent Chrome windows / API clients) but with 10–20s random stagger to avoid thundering-herd browser launches.
