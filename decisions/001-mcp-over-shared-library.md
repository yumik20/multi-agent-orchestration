# ADR-001: MCP server over a shared Python library for cross-skill tools

**Status:** accepted  
**Date:** 2026-04 (the migration); revised 2026-05 (added cross-skill `smart_dedup` tool)

## Context

For most of the system's first month, every scanner skill kept its own copy of the same loop: read raw scan output → drop URLs we'd seen in the last 30 days → ask a Haiku batch which ones were on-thesis → write a CSV → send an email.

That worked until the JSON dedup files diverged. Tuesday's scan re-qualified URLs Monday's scan had already rejected because each skill maintained its own seen-URLs file. The fix was a one-line edit per skill — but I had to make it five times in five places, and I kept missing one.

Each skill was also using slightly different Haiku batch sizes (some 6, some 10, one accidentally still 15) because someone had tuned a single skill once and forgotten the others.

Two real problems:
1. Duplicated logic that drifted whenever one copy was tuned.
2. State (the dedup cache) that should have been one shared store, fragmented across five files.

## Options considered

**Option A: Shared Python library.** Add a `_shared/` module the scanner skills import. Cleanest in pure-Python land. But the skills don't all live in the same runtime — some are bash-orchestrated, some are LLM-orchestrated and only "call code" by exec-ing a subprocess. A Python library would force everything into a Python entry-point and re-introduce subprocess wrappers everywhere.

**Option B: HTTP service.** Expose the loop as a small FastAPI service the skills curl. Cross-runtime, but adds: a long-lived process to manage, a port to claim, an auth layer if it's ever exposed beyond localhost, and lifecycle complexity (what restarts it? what happens during a scan if it's down?).

**Option C: MCP server with stdio transport.** Each skill spawns the server as a subprocess, sends JSON-RPC over stdin, reads stdout. No long-lived process, no port, runs anywhere a subprocess can be spawned. Cross-runtime by definition.

## Decision

Option C. Built one MCP server with seven tools (`run_scan`, `qualify`, `smart_dedup`, `weekly_report`, `cleanup`, `scan_status`, `send_email`). Each scanner skill went from ~50 lines of duplicated qualify-loop code to ~3 lines calling the MCP. The four JSON dedup caches became one SQLite table, queryable cross-skill.

The deciding factor was the cross-runtime requirement. A Python library would have made the bash-orchestrated and LLM-orchestrated skills second-class citizens. MCP is the contract that works for all three.

## Consequences

- **Skills became thin clients.** The qualify pipeline lives in one place; tuning the Haiku batch size moves all four scanners at once.
- **Cross-skill state.** When skill A qualifies a URL, skill B sees it instantly via `smart_dedup`. The previous architecture made this conceptually possible but operationally clumsy.
- **One more layer.** A skill failure now requires checking both the skill and the MCP. In practice this hasn't been a real cost — MCP errors surface with stack traces in the skill's stderr and the scan-pipeline state.db gives a queryable history.
- **Tool consolidation revealed dead code.** Three of the seven tools (`scan_status`, `weekly_report`, `cleanup`) were registered but never called from any skill until ~2 weeks later. Once they existed, wiring them to launchd crons was a one-day rollout instead of a from-scratch build.

## What we'd do differently

- **Build the MCP first when there's a second skill.** I waited until there were five duplicated copies before consolidating. The cost of the duplication was visible at three.
- **Plan the dedup migration.** Moving four JSON files into one SQLite table required a one-shot replay of historical URLs. I did this manually; a `--migrate-from-json` flag on the MCP would have been cleaner.

## Lesson named

When five things look 80% the same, the 80% is infrastructure, not workflow. Pull it down a layer until it stops being copy-pasted.
