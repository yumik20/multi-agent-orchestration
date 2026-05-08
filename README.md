# Multi-Agent Orchestration: Code Samples

[![CI](https://github.com/yumik20/multi-agent-orchestration/actions/workflows/ci.yml/badge.svg)](https://github.com/yumik20/multi-agent-orchestration/actions/workflows/ci.yml)

I run a small AI startup as a cofounder. To do that I built a multi-agent system that handles work I'd otherwise need a marketing analyst, a content lead, and an operations manager for: daily intelligence gathering, content drafting, publishing, operational monitoring. Six agents, ~46 skills, ~22 scheduled jobs, running on my laptop every day.

This repo is a curated subset (~1,500 lines). Production is ~25,000 lines of Python and JavaScript. **No external Python packages** (stdlib `urllib` for HTTP, `sqlite3` for state, `subprocess` for orchestration), plus bash and AppleScript. External services: Anthropic, OpenAI, Google LLM APIs, called via stdlib rather than vendor SDKs. Tests pass (`pytest tests/ -q` runs 105 cases in under 200ms). Design choices are documented in [`decisions/`](decisions/) as ADRs.

### What this repo demonstrates, and what it doesn't

It demonstrates operational and system-design depth: MCP tool consolidation, the operator rating eval loop, dual-kill watchdog, error-classifier-driven retries, source-of-truth markdown config, output-contract-before-LLM-spend.

It does not demonstrate algorithmic depth (`assign_overlap_lanes` is a greedy first-fit, the calendar-UI standard) or large-codebase complexity management (the production system has module-graph, SSE-update, and cron-orchestration concerns this excerpt doesn't fully expose). It is not a deployable framework; names, paths, and source-types are sanitized.

The commit timeline reflects when I built the public sample, not when the patterns were designed. The ADRs in [`decisions/`](decisions/) are the iteration receipts.

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

Month 1, every scanner skill had its own copy of the same loop: read raw scan output, drop URLs seen in the last 30 days, qualify against thesis, write CSV, email. The four JSON dedup files drifted; Tuesday's scan re-qualified URLs Monday's scan had already rejected. The fix was a one-line edit, but I had to make it five times in five places, and I kept missing one.

I pulled the loop into an MCP server with seven tools (`run_scan`, `qualify`, `smart_dedup`, `weekly_report`, `cleanup`, `scan_status`, `send_email`). Each scanner went from ~50 lines of duplicated qualify-loop code to ~3 lines calling the MCP. Four JSON dedup caches became one SQLite table queryable cross-skill.

I picked MCP over a Python library because my skills don't all live in the same runtime. Some are pure Python. Some are bash-orchestrated. Some are LLM-orchestrated and only "call code" by exec-ing a subprocess. Stdio MCP is the cross-runtime contract that works for all three.

Lesson: **when five things look 80% the same, the 80% is infrastructure, not workflow.**

## Operator-driven skill eval

Six weeks in, I had 22 scheduled jobs running daily and no honest signal on which were producing useful output. Engineering observability said all 22 were "healthy" by exit code, runtime, and token count. Three were quietly producing junk emails I'd skim and delete. The system was running. The system wasn't working.

Self-grading wasn't an option. Every "did the agent do its job?" prompt got a confident yes, including on runs that produced obvious garbage. The model can't see what good looks like in my domain.

I started thinking about the design less like software eval (sample, aggregate, threshold) and more like how a Japanese senior would supervise a junior. The **報告・連絡・相談 (hou-ren-sou)** rhythm of daily report, inform, consult, plus a weekly **振り返り (furikaeri)** retrospective. Maps cleanly to what an agent system actually needs:

- **報告** (daily report): every job logs to `runs.jsonl`. Nothing is invisible.
- **連絡** (daily inform): 18:00 chat message lists today's runs plus carryovers.
- **相談** (daily consult): optional notes per rating capture what I wanted differently.
- **振り返り** (weekly retrospective): Sunday memo aggregates by `(skill, platform)`, surfaces buckets below 3.0★, proposes corrective edits.

Each evening at 18:00, an agent computes the unrated set and sends one chat message per item with an inline 1-5 star keyboard. I tap stars during dinner. 30 seconds. No per-rating confirmations (clicks acknowledged silently), no free-text prompts. **Every job must be rated.** Unrated items roll forward; same as how a junior's work is reviewed item by item, not via a sampled dashboard.

A bundled scan that hits 4 sources fans out into 4 rateable items, so I can spot "scanner is great on source-a, useless on source-c" instead of one averaged number.

The run record carries an `extra.model_actual` field: which model *actually* executed, not which was configured. When the primary endpoint times out and the fallback dispatcher routes to a backup, that fact lands in the log. The weekly memo can answer "did the publishing skill's quality dip because the skill broke, or because the primary endpoint was down?" Different fixes, different ownership.

Full rationale in [ADR-002](decisions/002-operator-rating-over-llm-self-eval.md).

## Agent skills inventory (selected)

The system runs ~46 skills across 6 agents. Each skill is a `SKILL.md` file the runtime parses (frontmatter declares model, MCPs, trigger phrases) plus an optional `scripts/` directory.

| Skill | Role | When | MCPs | Model |
|---|---|---|---|---|
| `scan-source-a/b/c` | daily intelligence gathering | Mon-Sat 08:00 | scan-pipeline | flash / haiku |
| `morning-intel` | watchlist sweep | Mon-Sat 10:00 | none | haiku |
| `creator-blog-publish` | end-to-end publish + self-QA | Mon/Wed/Fri 09:30 | none | gpt-4.1 |
| `creator-thread-post` | weekly social thread | Sat 13:20 | none | gpt-4.1-mini |
| `intel-competitive` | competitive scan + memo | Mon/Wed 13:00 | scan-pipeline | flash |
| `intel-calendar` | daily calendar review | Mon-Sat 07:00 | none | flash |
| `intel-contacts` | contact prioritization | Mon-Fri 14:00 | none | flash |
| `manager-noon-checkup` | mid-day status to chat | Mon-Sat 12:00 | none | haiku |
| `manager-evening-standup` | full-team digest | daily 18:00 | none | haiku |
| `manager-weekly-strategy` | Friday strategy review | Fri 10:00 | none | sonnet |
| `manager-workspace-curation` | weekly KB maintenance | Sun 02:00 | none | haiku |
| `eval-evening-ratings` | operator rating collection | daily 18:00 | none | flash |
| `eval-weekly-memo` | Sunday skill-quality memo | Sun 19:00 | none | (no LLM) |
| `kb-daily-ingest` | promote findings to wiki | Mon-Sat 10:30 | none | haiku |
| `kb-weekly-lint` | wiki coverage report | Sun 03:00 | none | (no LLM) |

Three patterns from this table: most "manager" jobs run on Haiku, not Sonnet (Sonnet is reserved for weekly strategy where actual judgment is needed); two skills run with no LLM at all (the weekly memo and lint report are pure Python aggregation); four scanners share one MCP (which is why the consolidation paid off).

## Product-design choices

Engineering depth alone doesn't make a multi-agent system usable by an operator. The patterns below are about *how the operator interacts with the system*: status taxonomies, channel rules, what the run record carries, when to send an email vs. silence.

| Pattern | Summary |
|---|---|
| [Show, don't decide](product-design/show-dont-decide.md) | Surface problems, don't auto-fix. Capability drift, model-fallback events, weekly memo proposals: all reported, none silently corrected. |
| [Friction as feature](product-design/friction-as-feature.md) | Every job must be rated. Silence is never approval. Issue dismissal is manual. Friction goes where mistakes compound. |
| [Status taxonomy](product-design/status-taxonomy.md) | 8 categories, not binary ok/fail. The Idle/Stale and Blocked/Error pairs map to different operator actions. |
| [Channel-choice rule](product-design/channel-choice-rule.md) | Chat for synchronous (approvals, alerts). Email for async (digests, reports). Dashboard for status. File-state for audit. |
| [Cost reconciliation UX](product-design/cost-reconciliation.md) | Three numbers (estimated, prepaid consumed, reconciled) plus variance, hero-level. Calibration UI, not a billing system. |
| [Usage classification](product-design/usage-classification.md) | `usage: cron / manual / subprocess / chained / emergency / deprecated` as a queryable manifest field on every skill. |
| [Lifecycle + retention](product-design/lifecycle-and-retention.md) | Three retention layers (mechanical, curated, deprecation-not-deletion). Nothing disappears. Things age explicitly. |

Most of these are the opposite of what an engineer would naturally choose. Engineers optimize for fewer steps and automatic resolution. Operators want to know what's happening and decide what to do about it. Each tradeoff trades engineering efficiency for operator clarity.

## Cost-optimization receipts

Numbers I can back up from production:

- **Manager-agent context: 21K → 4.5K tokens per session (79% reduction).** The standup and noon checkup loaded the full agent profile registry; they now load a compressed digest with the same operational signal.
- **Haiku batch size 6 → 20: ~64% fewer API calls per qualify cycle.** Previous size kept the verbose-JSON Gemini fallback under output-token limits; a separate `HAIKU_BATCH_SIZE` for the primary path doesn't have that constraint.
- **SQLite dedup vs four JSON caches.** Cross-skill queryable in microseconds. No more drift between scanners.
- **URL-shape gate before LLM.** Regex validators drop fabricated `https://example.com/post/abc` URLs (an LLM hallucination pattern) before they enter the dedup table or hit a Haiku batch.
- **Model rotation.** Scanners moved Sonnet → Haiku/Flash via the MCP migration. Lower-stakes manager jobs moved to gpt-4o-mini. Operator rating signal stayed flat through both moves: the data that gave me confidence the cost cut wasn't a quality cut.

Compounding effect: roughly an order-of-magnitude reduction in cost-per-completed-job vs. the naive per-row loop the system started with. Lesson: **order matters more than speed.** A microsecond regex check that runs first is more valuable than a millisecond optimization in the model call.

## Folders

| Folder | What it shows |
|---|---|
| [`mcp-server/`](mcp-server/) | Stdio MCP server with 7 tools shared across scanner skills. SQLite-backed cross-skill dedup. |
| [`quality-gates/`](quality-gates/) | Three validators in cost order: `output_contract` (URL regex), `artifact_gate` (schema, tri-state), `hallucination_validator` (LLM judge with static issue severities). |
| [`skill-rating-eval/`](skill-rating-eval/) | The operator rating loop: `run_tracker.py`, `compute_unrated_jobs.py`, `record_ratings.py`, `build_weekly_memo.py`. |
| [`model-fallback/`](model-fallback/) | Bash wrapper that catches the silent-death pattern (primary dies in <180s with <200B output) and retries on a fallback. |
| [`cost-optimization/`](cost-optimization/) | Prompt-cache wiring, model-aware batch sizing, cross-skill SQLite dedup, markdown-table-as-config. |
| [`scan-pipeline/`](scan-pipeline/) | Generic cross-source qualification. Normalizes per-scanner CSV schemas. LLM qualification with deterministic keyword fallback. |
| [`agent-orchestration/`](agent-orchestration/) | Scheduling engine + dual-kill watchdog (absolute timeout AND output-stall detection). |
| [`dashboard-visualization/`](dashboard-visualization/) | Single-page dashboard: overlap-aware weekly calendar, cost reconciliation, run history. |
| [`knowledge-base/`](knowledge-base/) | Markdown-first KB. Layered: `sources/` → `raw/` intake → `wiki/` → `output/`. Every signal accepted, rejected, or deferred with audit trail. |
| [`error-handling/`](error-handling/) | `error_classifier.py` categorizes LLM exceptions with deterministic retry per category. Replaces "try 3 times with a fixed sleep" with a policy that doesn't waste calls on auth errors. |
| [`product-design/`](product-design/) | Seven product-design patterns from the production system (status taxonomy, channel rules, friction-as-feature, etc.). |
| [`decisions/`](decisions/) | Five ADRs covering MCP-over-library, operator-rating-over-self-eval, SQLite-over-JSON, dual-kill-over-single-timeout, markdown-over-YAML. |
| [`tests/`](tests/) | Pytest suite (105 cases, <200ms). CI runs on every push plus a leakage-scan grep. |

## License

Code samples released for review and reference, not as a deployable framework. Adapt freely.
