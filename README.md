# Multi-Agent Orchestration: Code Samples

I run a small AI startup as a solo founder. To do that I built a multi-agent system that handles the work I'd otherwise need a marketing analyst, a content lead, and an operations manager for: daily intelligence gathering, content drafting, publishing, and operational monitoring. Six specialized agents, ~46 skills, ~22 scheduled jobs, running on my laptop every day.

This repo is selected code from that system. It's not a framework you can install. It's the load-bearing patterns I've kept iterating on for several months because they actually work in production.

The dashboard supervises agents running on the [OpenClaw](https://github.com/openclaw/openclaw) runtime: tracking performance, reconciling LLM costs across providers, and surfacing failure modes without me grepping logs. Production system is ~25,000 lines of Python and JavaScript. Zero external runtime dependencies — Python stdlib + bash + AppleScript only.

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
│  Browser-automation + API hybrids, LLM quality          │
│  filtering, common-schema normalization                 │
└─────────────────────────────────────────────────────────┘
```

## Why an MCP server?

For most of the system's first month, every scanner skill had its own copy of the same loop: read raw scan output, drop URLs we'd seen in the last 30 days, ask a Haiku batch which ones were on-thesis, write a CSV, send an email. That worked until it didn't.

The first sign was that Tuesday's scan would re-qualify URLs Monday's scan had already rejected. Each skill kept its own JSON dedup file; the four files drifted; the morning email started arriving with duplicates. The fix was a one-line edit per skill — but I had to make it five times, in five places, and I kept missing one.

That's when I pulled the loop into an MCP server with seven tools (`run_scan`, `qualify`, `smart_dedup`, `weekly_report`, `cleanup`, `scan_status`, `send_email`). Each scanner skill went from ~50 lines of duplicated qualify-loop code to ~3 lines calling the MCP. The four JSON dedup caches became one SQLite table queryable cross-skill.

I picked MCP specifically (not a Python library) because my skills don't all live in the same runtime. Some are pure Python scripts. Some are bash-orchestrated. Some are LLM-orchestrated and only "call code" by exec-ing a subprocess. Stdio MCP is the cross-runtime contract that works for all three.

The lesson I keep applying since: **when five things look 80% the same, the 80% is infrastructure, not workflow.** Pull it down a layer until it stops being copy-pasted.

## Operator-driven skill eval

Six weeks in, I had 22 scheduled jobs running daily and no honest signal on which ones were producing useful output. Engineering observability — exit codes, runtime, token counts — said all 22 were "healthy." But three of them were quietly producing junk emails I'd skim and delete. The system was running; the system wasn't working.

Self-grading wasn't an option. Every "did the agent do its job?" prompt I tried got a confident yes, including on the runs that produced obvious garbage. The model can't see what good looks like in my domain.

So I built a rating loop where I'm the judge:

1. **Every skill execution writes to `runs.jsonl`** — a single append-only log shared across all skills. The `run_tracker.py` helper handles `start_run` / `finish_run` with millisecond-precision job IDs.
2. **Each evening at 18:00, an agent computes the unrated set** — today's runs plus any carryovers from previous days. A bundled scan that hits 4 sources fans out into 4 rateable items (so I can spot "scanner is great on source-a, useless on source-c" instead of one averaged number that hides the per-source signal).
3. **It sends one chat message per item with an inline 1-5 star keyboard.** I tap stars during dinner. The whole rating session takes 30 seconds. There are no per-rating confirmations — clicks are acknowledged silently — and no free-text prompts. Friction is the whole problem.
4. **Sunday at 19:00, a weekly memo aggregates** ratings by `(skill, platform)`, surfaces buckets below 3.0★, and emails me a digest with the worst performers and the operator notes I left on them.

A subtlety that matters: the run record carries an `extra.model_actual` field — which model *actually* ran, not which model is configured. When the primary endpoint times out and the fallback dispatcher quietly routes the run to a backup model, that fact lands in the log. The weekly memo then answers a question I couldn't answer before: "did the publishing skill's quality dip because the skill broke, or because the primary model endpoint was down?" Different fixes; different ownership.

This loop is the most operationally useful thing I've built. It catches what every other layer of monitoring misses.

## Agent skills inventory (selected)

The system runs ~46 skills across 6 agents. Each skill is a `SKILL.md` file the runtime parses (frontmatter declares model, MCPs, trigger phrases) plus an optional `scripts/` directory of Python helpers. Below is a representative slice — generic role labels, not the specific agent names from production:

| Skill | Role | When it runs | MCPs used | Model class |
|---|---|---|---|---|
| `scan-source-a` | daily intelligence gathering, qualified candidate emails | Mon-Sat 08:00 | scan-pipeline | flash / haiku |
| `scan-source-b` | discussion-feed surveillance, signal extraction | Mon-Sat 08:00 | scan-pipeline | flash / haiku |
| `scan-source-c` | newsletter-style longform monitoring | Mon-Sat 08:00 | scan-pipeline | flash / haiku |
| `morning-intel` | watchlist sweep across known names + topics | Mon-Sat 10:00 | — | haiku |
| `creator-blog-publish` | end-to-end article publish with self-QA gates | Mon/Wed/Fri 09:30 | — | gpt-4.1 |
| `creator-thread-post` | weekly social thread + curated digest email | Sat 13:20 | — | gpt-4.1-mini |
| `intel-competitive` | competitive scan + structured memo | Mon/Wed 13:00 | scan-pipeline | flash |
| `intel-calendar` | daily calendar review, change-only summary | Mon-Sat 07:00 | — | flash |
| `intel-contacts` | contact prioritization + re-engagement candidates | Mon-Fri 14:00 | — | flash |
| `manager-noon-checkup` | mid-day operational status to chat | Mon-Sat 12:00 | — | haiku |
| `manager-evening-standup` | full-team digest of the day's work | daily 18:00 | — | haiku |
| `manager-weekly-strategy` | Friday strategy review against goals | Fri 10:00 | — | sonnet |
| `manager-workspace-curation` | weekly knowledge base maintenance | Sun 02:00 | — | haiku |
| `eval-evening-ratings` | operator rating collection + daily digest | daily 18:00 | — | flash |
| `eval-weekly-memo` | Sunday skill-quality memo | Sun 19:00 | — | (no LLM — pure Python) |
| `kb-daily-ingest` | promote qualified findings to maintained wiki | Mon-Sat 10:30 | — | haiku |
| `kb-weekly-lint` | wiki coverage + drift report | Sun 03:00 | — | (no LLM — pure Python) |

Three things worth noting from this table:

- **Most "manager" jobs run on Haiku, not Sonnet.** Sonnet is reserved for the weekly strategy review where actual judgment is needed. Daily checkups are template-shaped; cheap models are sufficient and the cost difference compounds across 5×/week.
- **Two skills run with no LLM at all.** The weekly skill-rating memo and the wiki lint report are pure Python aggregation. There's no model in the world that joins JSONL files better than `csv.DictReader`.
- **Scanners share an MCP.** Four scanners all call `scan-pipeline`'s tools. That's why the consolidation paid off.

## Cost-optimization receipts

Numbers I can actually back up from running this in production:

- **Manager-agent context compression**: 21K tokens → 4.5K tokens per session (79% reduction). The daily standup and noon checkup sessions used to load the full agent profile registry; they now load a 4.5K compressed digest with the same operational signal.
- **Haiku batch size 6 → 20**: ~64% fewer API calls per qualify cycle on the morning scan. The previous batch size was set to keep the verbose-JSON Gemini fallback path under output-token limits; a separate `HAIKU_BATCH_SIZE` for the primary path doesn't have that constraint.
- **SQLite dedup vs four JSON caches**: cross-skill queryable in microseconds, no more drift between scanners, no more rewrite-the-whole-file-on-every-update.
- **URL-shape gate before LLM**: regex validators run in microseconds and drop fabricated `https://example.com/post/abc` URLs (an LLM hallucination pattern) before they enter the 30-day dedup table or hit a Haiku batch. Gates aren't expensive when they run first.
- **Model rotation**: scanners moved Sonnet → Haiku/Flash via the MCP migration; lower-stakes manager jobs moved to gpt-4o-mini. The operator rating signal stayed flat through both moves — that's the data that gave me confidence the cost cut wasn't a quality cut.

The compounding effect of all four (dedup-aware batching, prompt cache, URL gate, model routing) is roughly an order-of-magnitude reduction in cost-per-completed-job vs. the naive per-row loop the system started with. The bigger lesson: **order matters more than speed.** A microsecond regex check that runs first is more valuable than a millisecond optimization in the model call. Pushing cheap checks earlier in the pipeline beats making expensive checks faster.

## What's in Each Folder

**`mcp-server/`** Stdio-transport MCP server with the seven tools shared across scanner skills. Demonstrates: subprocess orchestration, parallel execution with stagger, SQLite-backed cross-skill dedup, output-contract enforcement at the qualify boundary, per-platform success thresholds.

**`quality-gates/`** Three independent validators in increasing cost order. (1) **output_contract** — URL-shape regex per source-type, drops malformed rows in microseconds before LLM spend. (2) **artifact_gate** — schema validator, marker-based opt-in, tri-state verdicts (pass / uncertain / fail). (3) **hallucination_validator** — LLM judge with three supervision levels and static issue severities the judge can't game.

**`skill-rating-eval/`** The operator rating loop described above. Five files: `run_tracker.py` (start/finish helpers), `compute_unrated_jobs.py` (today + carryover), `record_ratings.py` (write ratings.jsonl, regenerate daily digest), `build_weekly_memo.py` (Sunday aggregator + email), and a README that explains the design.

**`model-fallback/`** Bash wrapper that catches the silent-death pattern (primary model dies in <180s with <200B output), auto-retries on a configurable fallback model, and logs a `model_fallback` event for the weekly memo to surface.

**`cost-optimization/`** Four patterns: prompt-cache wiring with `cache_control: ephemeral`, model-aware batch sizing, cross-skill SQLite dedup, and the markdown-table-as-config pattern (model assignments live in a markdown table parsed at request time — editing the markdown moves the dashboard, no hardcoded drift).

**`scan-pipeline/`** Generic cross-source qualification pipeline that normalizes per-scanner CSV schemas into one shape, then runs the unified set through the qualify funnel. LLM-based qualification with deterministic keyword-overlap fallback so the pipeline never blocks on the qualifier being available.

**`agent-orchestration/`** Scheduling engine: conflict-free time slots, dual-kill watchdog (absolute timeout AND output-stall detection — agents get a 60s grace warning to flush partial work before a hard kill), bot operational status classification.

**`dashboard-visualization/`** Single-page dashboard with weekly calendar (overlap-aware lane assignment, live "Now" line), per-provider cost reconciliation, execution timeline with agent run history.

**`knowledge-base/`** Markdown-first KB with formal ingest, qualification, and promotion pipelines. Layered architecture: immutable `sources/` → `raw/` intake → maintained `wiki/` → durable `output/`. Every signal explicitly accepted, rejected, or deferred with an audit trail.

## Engineering patterns demonstrated

Ordered roughly by operational impact:

- **Operator rating loop as first-class infrastructure.** The system can't grade its own quality. A 1-5 star tap each evening, accumulated weekly, is the only signal that survives "skill ran without errors but produced junk."
- **MCP server for tool consolidation.** When N skills duplicate the same loop, the duplication is infrastructure. Pull it into one server; each skill becomes a thin client.
- **Output contract before LLM spend.** Cheap checks first. A regex that runs in microseconds drops fabricated outputs before they hit the LLM pipeline.
- **Model-fallback as infrastructure, not workflow.** When a primary endpoint times out, the dispatcher transparently retries on a fallback and tags the run record. Operators don't manually escalate; the weekly memo surfaces fallback drift.
- **Source-of-truth config files.** Model assignments live in a markdown table, parsed at request time. Editing the table moves the dashboard. No hardcoded model strings drifting from intent.
- **Dual-kill subprocess wrapper.** Wall-time timeout AND output-stall detector. A 90-min skill that goes silent at minute 4 gets killed at minute 5 with a graceful flush — not at minute 90 after burning the full window.
- **Cross-skill state sharing via MCP.** Four scanners share one 30-day dedup window. When skill A qualifies a URL, skill B sees it instantly.
- **Tri-state quality gates.** Pass / uncertain / fail. "Uncertain" triggers a soft warning + retry suggestion. Boolean gates produce too many false positives that block real work.

## Technical Choices

- Zero external runtime dependencies — Python stdlib + bash + AppleScript
- Markdown-first config (diff-friendly, parseable by humans and LLMs both)
- File-based state (JSON / JSONL / SQLite — inspectable, versionable, survives a process restart)
- macOS-native integrations (AppleScript for email, launchd for scheduling)
- Stdio-transport MCP servers (no extra processes, no port conflicts, works across language runtimes)

## License

Code samples — released for review and reference, not as a deployable framework. Adapt freely.
