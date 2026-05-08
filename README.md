# Multi-Agent Orchestration: Code Samples

[![CI](https://github.com/yumik20/multi-agent-orchestration/actions/workflows/ci.yml/badge.svg)](https://github.com/yumik20/multi-agent-orchestration/actions/workflows/ci.yml)

I run a small AI startup as a cofounder. To do that I built a multi-agent system that handles work I'd otherwise need a marketing analyst, a content lead, and an operations manager for: daily intelligence gathering, content drafting, publishing, operational monitoring. Six agents, ~46 skills, ~22 scheduled jobs, running on my laptop every day.

This repo is a curated subset of that system (~1,500 lines). Production is ~25,000 lines of Python and JavaScript. **No external Python packages** (stdlib `urllib` for HTTP, `sqlite3` for state, `subprocess` for orchestration), plus bash and AppleScript. External services: Anthropic, OpenAI, Google LLM APIs, called via stdlib rather than vendor SDKs.

The patterns are tested (`pytest tests/ -q` runs 105 cases in under 200ms). The design choices are documented in [`decisions/`](decisions/) as ADRs.

### What this repo demonstrates, and what it doesn't

It demonstrates operational and system-design depth. MCP tool consolidation. The operator rating eval loop. Dual-kill watchdog. Error-classifier-driven retries. Source-of-truth markdown config. Output-contract-before-LLM-spend.

It does not demonstrate algorithmic depth (`assign_overlap_lanes` is a greedy first-fit, the calendar-UI standard) or large-codebase complexity management (the production system has module-graph, SSE-update, and cron-orchestration concerns this excerpt doesn't fully expose). It is not a deployable framework; names, paths, and source-types are sanitized.

The commit timeline reflects when I built the public sample (a few days), not when the patterns were designed (months of iteration). The ADRs in [`decisions/`](decisions/) are the receipts of that iteration: what failed, what was tried, what was kept.

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

For most of the system's first month, every scanner skill had its own copy of the same loop. Read raw scan output, drop URLs seen in the last 30 days, ask a Haiku batch which ones were on-thesis, write a CSV, send an email. That worked until it didn't.

The first sign was that Tuesday's scan would re-qualify URLs Monday's scan had already rejected. Each skill kept its own JSON dedup file. The four files drifted. The morning email started arriving with duplicates. The fix was a one-line edit per skill, but I had to make it five times in five places, and I kept missing one.

That's when I pulled the loop into an MCP server with seven tools: `run_scan`, `qualify`, `smart_dedup`, `weekly_report`, `cleanup`, `scan_status`, `send_email`. Each scanner skill went from ~50 lines of duplicated qualify-loop code to ~3 lines calling the MCP. The four JSON dedup caches became one SQLite table queryable cross-skill.

I picked MCP specifically (not a Python library) because my skills don't all live in the same runtime. Some are pure Python scripts. Some are bash-orchestrated. Some are LLM-orchestrated and only "call code" by exec-ing a subprocess. Stdio MCP is the cross-runtime contract that works for all three.

Lesson I keep applying since: **when five things look 80% the same, the 80% is infrastructure, not workflow.** Pull it down a layer until it stops being copy-pasted.

## Operator-driven skill eval

Six weeks in, I had 22 scheduled jobs running daily and no honest signal on which ones were producing useful output. Engineering observability said all 22 were "healthy" by exit code, runtime, and token count. Three of them were quietly producing junk emails I'd skim and delete. The system was running. The system wasn't working.

Self-grading wasn't an option. Every "did the agent do its job?" prompt got a confident yes, including on the runs that produced obvious garbage. The model can't see what good looks like in my domain.

I started thinking about the design less like software eval (sample, aggregate, threshold) and more like how a Japanese senior would supervise a junior employee. The **報告・連絡・相談 (hou-ren-sou)** rhythm of daily report, inform, consult, plus a weekly **振り返り (furikaeri)** retrospective. The mental model maps cleanly to what an agent system actually needs:

- **報告 (hou, daily report)**: every job logs to `runs.jsonl`. Nothing is invisible.
- **連絡 (ren, daily inform)**: 18:00 chat message lists today's runs plus carryovers. The operator (me) sees every item, not a sampled subset.
- **相談 (sou, daily consult)**: optional notes per rating capture what I wanted differently. The owner agent reads these into next-week's revisions.
- **振り返り (furikaeri, weekly retrospective)**: Sunday memo aggregates `(skill, platform)` performance, surfaces the bottom of the list, proposes specific corrective edits to the underlying SKILL.md files.

Concretely, the loop. Each evening at 18:00 an agent computes the unrated set: today's runs plus any carryovers. It sends one chat message per item with an inline 1-5 star keyboard. I tap stars during dinner. The whole rating session takes 30 seconds. No per-rating confirmations (clicks acknowledged silently), no free-text prompts. Friction is the problem.

A bundled scan that hits 4 sources fans out into 4 rateable items, so I can spot "scanner is great on source-a, useless on source-c" instead of one averaged number that hides the per-source signal. **Every job must be rated.** Unrated items roll forward. There is no "skip this one." Same as how a junior's work is reviewed item by item in their manager's 1:1, not via a sampled dashboard. Carryover discipline is the value.

A subtlety that matters operationally: the run record carries an `extra.model_actual` field that captures which model *actually* executed, not which model is configured. When the primary endpoint times out and the fallback dispatcher quietly routes to a backup, that fact lands in the log. The weekly memo can answer "did the publishing skill's quality dip because the skill broke, or because the primary model endpoint was down?" Different fixes, different ownership.

Full design rationale in [ADR-002](decisions/002-operator-rating-over-llm-self-eval.md).

## Agent skills inventory (selected)

The system runs ~46 skills across 6 agents. Each skill is a `SKILL.md` file the runtime parses (frontmatter declares model, MCPs, trigger phrases) plus an optional `scripts/` directory of Python helpers. Below is a representative slice with generic role labels.

| Skill | Role | When it runs | MCPs used | Model class |
|---|---|---|---|---|
| `scan-source-a` | daily intelligence gathering | Mon-Sat 08:00 | scan-pipeline | flash / haiku |
| `scan-source-b` | discussion-feed surveillance | Mon-Sat 08:00 | scan-pipeline | flash / haiku |
| `scan-source-c` | newsletter-style longform | Mon-Sat 08:00 | scan-pipeline | flash / haiku |
| `morning-intel` | watchlist sweep | Mon-Sat 10:00 | none | haiku |
| `creator-blog-publish` | end-to-end article publish + self-QA | Mon/Wed/Fri 09:30 | none | gpt-4.1 |
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

Three things worth noting. **Most "manager" jobs run on Haiku, not Sonnet.** Sonnet is reserved for the weekly strategy review where actual judgment is needed. Daily checkups are template-shaped; cheap models suffice and the difference compounds across 5×/week. **Two skills run with no LLM at all.** The weekly skill-rating memo and the wiki lint report are pure Python aggregation. There's no model in the world that joins JSONL files better than `csv.DictReader`. **Scanners share an MCP.** Four scanners all call `scan-pipeline`'s tools. That's why the consolidation paid off.

## Product-design choices

Engineering depth alone doesn't make a multi-agent system usable by an operator. The patterns below are the ones I made about *how the operator interacts with the system*. Most aren't visible in the code samples; they live in status taxonomies, channel rules, what the run record carries, when to send an email vs. silence.

| Pattern | Summary |
|---|---|
| [Show, don't decide](product-design/show-dont-decide.md) | Surface problems to the operator. Don't auto-fix. Capability drift, model-fallback events, weekly memo proposals: all reported, none silently corrected. |
| [Friction as feature](product-design/friction-as-feature.md) | Every job must be rated. Silence is never approval. Issue dismissal is manual. Friction goes where mistakes compound. |
| [Status taxonomy](product-design/status-taxonomy.md) | 8 categories (Running, Scheduled, Completed, Idle, Blocked, Error, Stale, Unknown), not binary ok/fail. The Idle/Stale and Blocked/Error pairs alone are worth the granularity. |
| [Channel-choice rule](product-design/channel-choice-rule.md) | Chat for synchronous (approvals, alerts). Email for asynchronous (digests, reports). Dashboard for status. File-state for audit. Mixing them wastes attention. |
| [Cost reconciliation UX](product-design/cost-reconciliation.md) | Three numbers (estimated, prepaid consumed, reconciled) plus variance, hero-level. Calibration UI, not a billing system. |
| [Usage classification](product-design/usage-classification.md) | `usage: cron / manual / subprocess / chained / emergency / deprecated` as a queryable manifest field on every skill. |
| [Lifecycle + retention](product-design/lifecycle-and-retention.md) | Three retention layers (mechanical, curated, deprecation-not-deletion). Nothing disappears. Things age explicitly. |

The meta-pattern: a lot of these are the opposite of what an engineer would naturally choose. Engineers optimize for fewer steps, automatic resolution, fewer confirmations. Operators want to know what's happening and decide what to do about it. Each tradeoff trades engineering efficiency for operator clarity.

## Cost-optimization receipts

Numbers I can back up from running this in production.

- **Manager-agent context compression: 21K tokens to 4.5K per session (79% reduction).** The daily standup and noon checkup used to load the full agent profile registry; they now load a 4.5K compressed digest with the same operational signal.
- **Haiku batch size 6 to 20: ~64% fewer API calls per qualify cycle.** Previous size kept the verbose-JSON Gemini fallback path under output-token limits; a separate `HAIKU_BATCH_SIZE` for the primary path doesn't have that constraint.
- **SQLite dedup vs four JSON caches.** Cross-skill queryable in microseconds. No more drift between scanners. No more rewrite-the-whole-file-on-every-update.
- **URL-shape gate before LLM.** Regex validators run in microseconds and drop fabricated `https://example.com/post/abc` URLs (an LLM hallucination pattern) before they enter the 30-day dedup table or hit a Haiku batch.
- **Model rotation.** Scanners moved Sonnet to Haiku/Flash via the MCP migration. Lower-stakes manager jobs moved to gpt-4o-mini. The operator rating signal stayed flat through both moves. That's the data that gave me confidence the cost cut wasn't a quality cut.

Compounding effect: roughly an order-of-magnitude reduction in cost-per-completed-job vs. the naive per-row loop the system started with. The bigger lesson: **order matters more than speed.** A microsecond regex check that runs first is more valuable than a millisecond optimization in the model call. Push cheap checks earlier.

## Folders

| Folder | What it shows |
|---|---|
| [`mcp-server/`](mcp-server/) | Stdio-transport MCP server with 7 tools shared across scanner skills. Subprocess orchestration, parallel execution with stagger, SQLite-backed cross-skill dedup. |
| [`quality-gates/`](quality-gates/) | Three validators in increasing cost order: `output_contract` (URL regex, microseconds), `artifact_gate` (schema validator, tri-state), `hallucination_validator` (LLM judge, static issue severities). |
| [`skill-rating-eval/`](skill-rating-eval/) | The operator rating loop. `run_tracker.py`, `compute_unrated_jobs.py`, `record_ratings.py`, `build_weekly_memo.py`. |
| [`model-fallback/`](model-fallback/) | Bash wrapper that catches the silent-death pattern (primary dies in <180s with <200B output), retries on a fallback model, logs the fallback for the weekly memo. |
| [`cost-optimization/`](cost-optimization/) | Prompt-cache wiring with `cache_control: ephemeral`, model-aware batch sizing, cross-skill SQLite dedup, markdown-table-as-config. |
| [`scan-pipeline/`](scan-pipeline/) | Generic cross-source qualification. Normalizes per-scanner CSV schemas. LLM qualification with deterministic keyword fallback. |
| [`agent-orchestration/`](agent-orchestration/) | Scheduling engine with conflict-free time slots and the dual-kill watchdog (absolute timeout AND output-stall detection). |
| [`dashboard-visualization/`](dashboard-visualization/) | Single-page dashboard with overlap-aware weekly calendar, per-provider cost reconciliation, agent run history. |
| [`knowledge-base/`](knowledge-base/) | Markdown-first KB. Layered: immutable `sources/`, `raw/` intake, maintained `wiki/`, durable `output/`. Every signal accepted, rejected, or deferred with audit trail. |
| [`error-handling/`](error-handling/) | `error_classifier.py` categorizes LLM exceptions (network, timeout, rate_limit, auth, model, parse, unknown) with deterministic retry decisions. `retry_with_backoff.py` applies them. Replaces "try 3 times with a fixed sleep" with a policy that doesn't waste calls on auth errors. |
| [`decisions/`](decisions/) | Five ADRs covering the major design choices: MCP over a shared library, operator rating over LLM self-eval, SQLite over JSON, dual-kill over single timeout, markdown table over YAML. Each ADR captures the production iteration that drove the decision. |
| [`tests/`](tests/) | Pytest suite (105 cases, <200ms). CI workflow runs on every push plus a leakage-scan grep that fails the build if a forbidden token reappears. |

## Engineering patterns

Ordered roughly by operational impact.

- **Operator rating loop as first-class infrastructure.** The system can't grade its own quality. A 1-5 star tap each evening, accumulated weekly, is the only signal that survives "skill ran without errors but produced junk."
- **MCP server for tool consolidation.** When N skills duplicate the same loop, the duplication is infrastructure. Pull it into one server. Each skill becomes a thin client.
- **Output contract before LLM spend.** Cheap checks first. Microsecond regex drops fabricated outputs before they hit the LLM pipeline.
- **Model fallback as infrastructure, not workflow.** When a primary endpoint times out, the dispatcher retries on a fallback and tags the run record. Operators don't manually escalate; the weekly memo surfaces fallback drift.
- **Source-of-truth config files.** Model assignments live in a markdown table parsed at request time. Editing the table moves the dashboard. No hardcoded model strings drifting from intent.
- **Dual-kill subprocess wrapper.** Wall-time timeout AND output-stall detector. A 90-min skill that goes silent at minute 4 gets killed at minute 5 with a graceful flush, not at minute 90 after burning the full window.
- **Cross-skill state sharing via MCP.** Four scanners share one 30-day dedup window. When skill A qualifies a URL, skill B sees it instantly.
- **Tri-state quality gates.** Pass / uncertain / fail. "Uncertain" triggers a soft warning plus retry suggestion. Boolean gates produce too many false positives that block real work.

## License

Code samples released for review and reference, not as a deployable framework. Adapt freely.
