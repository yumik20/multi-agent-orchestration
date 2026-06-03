# Multi-Agent Orchestration: Code Samples

[![CI](https://github.com/yumik20/multi-agent-orchestration/actions/workflows/ci.yml/badge.svg)](https://github.com/yumik20/multi-agent-orchestration/actions/workflows/ci.yml)

I run an AI startup as a cofounder. I built a production multi-agent system for daily intelligence gathering, content creation, publishing, contact intelligence, lead generation, and operational monitoring. It runs six specialized agents, 51 skills, 4 MCP servers with 25 tools, 22 scheduled cron jobs, and 17 launchd daemons on a single MacBook.

This repo is a curated subset, about 1,500 lines. Production is about 25,000 lines of Python and JavaScript. **No external Python packages**. It uses stdlib `urllib` for HTTP, `sqlite3` for state, and `subprocess` for orchestration, plus bash and AppleScript. External services are Anthropic, OpenAI, and Google LLM APIs, called through stdlib instead of vendor SDKs. Tests pass: `pytest tests/ -q` runs 105 cases in under 200ms. Design choices are documented in [`decisions/`](decisions/) as ADRs.

### Current system scale (June 2026)

| Metric | Count |
|--------|-------|
| Agents (specialized, each with distinct model) | 6 |
| Skills (SKILL.md-defined workflows) | 51 |
| MCP servers (stdio transport, Python) | 4 |
| MCP tools (callable by any agent at runtime) | 25 |
| Scheduled cron jobs | 22 enabled |
| Launchd daemons (macOS) | 17 active |
| Session files indexed (SQLite) | 3,200+ |
| LinkedIn connections (queryable at runtime) | 9,347 |
| Monthly LLM cost | ~$310 (down from $981 two months prior) |
| Lines of code (production) | ~25,000 |
| External Python packages | 0 |

### What this repo demonstrates, and what it doesn't

It demonstrates operational and system-design depth: MCP tool consolidation across 4 servers, the operator rating eval loop inspired by hou-ren-sou, dual-kill watchdog, error-classifier-driven retries, markdown config as source of truth, output contracts before LLM spend, SQLite session indexing that replaced a 16GB in-memory cache, launchd log evidence for schedule classification, and a schema caching layer for API discovery.

It does not demonstrate algorithmic depth. `assign_overlap_lanes` is a greedy first-fit, the calendar-UI standard. It also does not show the full production system's module-graph, SSE-update, and cron-orchestration concerns. It is not a deployable framework. Names, paths, and source types are sanitized.

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
│  MCP Servers (4 servers, 25 tools, stdio transport)     │
│                                                         │
│  scan-pipeline (7):  run_scan, qualify, smart_dedup,    │
│    weekly_report, cleanup, scan_status, send_email      │
│                                                         │
│  web-intel (9):  detect_platform, extract_embedded,     │
│    wellknown_discover, browser_fetch, discover_api,     │
│    graphql_introspect, x_sign, export_cookies, cache    │
│                                                         │
│  contact-intel (4):  recurring_hosts, company_signals,  │
│    inbox_linkedin_scan, event_history                   │
│                                                         │
│  lead-search (5):  first_degree, connections_at,        │
│    map_brokers, gemini_enrich, warm_path_check          │
│                                                         │
│  23/25 tools run 100% locally (no API cost)             │
│  2 tools call Gemini API (qualify, gemini_enrich)       │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────┴──────────────────────────────┐
│  Data Layer                                             │
│  • SQLite session index (replaces 16GB in-memory cache) │
│  • LinkedIn network (9,347 connections, offline query)  │
│  • AI leader map (509 people, warm-path cross-ref)      │
│  • Schema cache (7-day TTL per discovered API)          │
│  • Calendar EventKit (283 events, recurring host track) │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────┴──────────────────────────────┐
│  Scanners (4 source adapters + headless Chrome)         │
│  Browser-automation + API hybrids, LLM quality          │
│  filtering, HAR capture, anti-bot detection             │
└─────────────────────────────────────────────────────────┘
```

## Why an MCP server?

Month 1, every scanner skill had its own copy of the same loop: read raw scan output, drop URLs seen in the last 30 days, qualify against thesis, write CSV, email. The four JSON dedup files drifted. Tuesday's scan re-qualified URLs Monday's scan had already rejected. A one-line fix had to be made five times, and I kept missing one.

I pulled the loop into an MCP server with seven tools: `run_scan`, `qualify`, `smart_dedup`, `weekly_report`, `cleanup`, `scan_status`, `send_email`. Each scanner went from about 50 lines of duplicated qualify-loop code to about 3 lines calling the MCP. Four JSON dedup caches became one SQLite table queryable across skills.

That first MCP solved the scan problem. The same pattern then applied elsewhere:

- **web-intel** (9 tools): platform detection, anti-bot strategy recommendation, embedded data extraction (Next.js/Redux/GraphQL hydration), headless Chrome with HAR capture, API discovery with schema caching, GraphQL introspection, cookie persistence. 23 of 25 tools run 100% locally with zero API cost.
- **contact-intel** (4 tools): recurring host tracking across calendar events (fuzzy-matched by title similarity), company signal detection (2+ people from same company at different events), email inbox scanning for LinkedIn URLs (reads raw MIME source via AppleScript), event history recall.
- **lead-search** (5 tools): offline cross-reference of 9,347 LinkedIn connections + a 509-person industry map. `first_degree(name)` checks if someone is already connected. `connections_at(company)` finds warm intro paths. `map_brokers()` identifies super-connectors. `gemini_enrich(items, prompt)` runs any research question through Gemini with Google Search grounding, with the agent writing the prompt at runtime. No code changes between M&A, customer, hire, and press searches. `warm_path_check` batches all of the above for a company list.

I picked MCP over a Python library because my skills do not all live in the same runtime. Some are pure Python. Some are bash-orchestrated. Some are LLM-orchestrated and only call code by exec-ing a subprocess. Stdio MCP is the cross-runtime contract that works for all three.

Lesson: **when five things look 80% the same, the 80% is infrastructure, not workflow.**

## Operator-driven skill eval

Six weeks in, I had 22 scheduled jobs running daily and no honest signal on which were producing useful output. Engineering observability said all 22 were healthy by exit code, runtime, and token count. Three were quietly producing junk emails I would skim and delete. The system was running. The system was not working.

Self-grading was not an option. Every "did the agent do its job?" prompt got a confident yes, including on runs that produced obvious garbage. The model cannot see what good looks like in my domain.

I started thinking about the design less like software eval, sample, aggregate, threshold, and more like how a Japanese senior would supervise a junior. The **報告・連絡・相談 (hou-ren-sou)** rhythm of daily report, inform, consult, plus a weekly **振り返り (furikaeri)** retrospective, maps cleanly to what an agent system needs:

- **報告** (daily report): every job logs to `runs.jsonl`. Nothing is invisible.
- **連絡** (daily inform): 18:00 chat message lists today's runs plus carryovers.
- **相談** (daily consult): optional notes per rating capture what I wanted differently.
- **振り返り** (weekly retrospective): Sunday memo aggregates by `(skill, platform)`, surfaces buckets below 3.0★, proposes corrective edits.

Each evening at 18:00, an agent computes the unrated set and sends one chat message per item with an inline 1-5 star keyboard. I tap stars during dinner. 30 seconds. No per-rating confirmations, no free-text prompts. Clicks are acknowledged silently. **Every job must be rated.** Unrated items roll forward, the way a junior's work is reviewed item by item, not via a sampled dashboard.

A bundled scan that hits 4 sources fans out into 4 rateable items, so I can spot "scanner is great on source-a, useless on source-c" instead of seeing one averaged number.

The run record carries an `extra.model_actual` field: which model *actually* executed, not which was configured. When the primary endpoint times out and the fallback dispatcher routes to a backup, that fact lands in the log. The weekly memo can answer "did the publishing skill's quality dip because the skill broke, or because the primary endpoint was down?" Different causes, different owners.

Full rationale in [ADR-002](decisions/002-operator-rating-over-llm-self-eval.md).

## Agent skills inventory (selected)

The system runs about 46 skills across 6 agents. Each skill is a `SKILL.md` file the runtime parses. Frontmatter declares model, MCPs, and trigger phrases. A skill can also include a `scripts/` directory.

| Skill | Role | When | MCPs | Model |
|---|---|---|---|---|
| `scan-source-a/b/c` | daily intelligence gathering | Mon-Sat 08:00 | scan-pipeline, web-intel | flash |
| `morning-intel` | watchlist + market trends | Mon-Sat 10:00 | scan-pipeline, web-intel | flash |
| `creator-blog-daily` | competitor research + write + illustrate + publish + self-QA | Tue-Fri 09:30 | web-intel | gpt-5.5 |
| `creator-social-post` | queue-driven social posting (verbatim, no LLM rewrite) | weekdays | none (launchd) | none |
| `intel-competitive` | competitive scan + memo | Mon/Wed 13:00 | scan-pipeline, web-intel | flash |
| `intel-calendar` | calendar + host network analysis + event attendee lookup | Mon-Sat 07:00 | contact-intel, web-intel | flash |
| `intel-contacts` | contact prioritization + inbox LinkedIn scan | Mon-Fri 14:00 | contact-intel | flash |
| `intel-inbox-scan` | weekly email inbox scan for LinkedIn URLs | Sun 08:00 | contact-intel | flash |
| `manager-noon-checkup` | mid-day status to chat | Mon-Sat 12:00 | scan-pipeline | flash |
| `manager-evening-standup` | full-team digest | daily 18:00 | contact-intel | flash |
| `manager-weekly-strategy` | strategy review + network broker analysis | Sat 10:00 | contact-intel, lead-search | flash |
| `manager-workspace-curation` | weekly KB maintenance + cleanup | Sun 02:00 | none | flash |
| `eval-evening-ratings` | operator rating collection | daily 18:00 | none | flash |
| `km-daily-ingest` | promote qualified findings into wiki | Mon-Sat 10:30 | none | gpt-5.5 |
| `lead-search` | find + enrich + vet + warm-path any lead list | on-demand | lead-search | flash + sonnet |
| `eval-weekly-memo` | Sunday skill-quality memo | Sun 19:00 | none | (no LLM) |
| `kb-daily-ingest` | promote findings to wiki | Mon-Sat 10:30 | none | haiku |
| `kb-weekly-lint` | wiki coverage report | Sun 03:00 | none | (no LLM) |

Three patterns stand out: most manager jobs run on Haiku, not Sonnet. Sonnet is reserved for weekly strategy, where actual judgment is needed. Two skills run with no LLM at all. The weekly memo and lint report are pure Python aggregation. Four scanners share one MCP, which is why the consolidation paid off.

## Product-design choices

Engineering depth alone does not make a multi-agent system usable by an operator. The patterns below cover how the operator interacts with the system: status taxonomies, channel rules, what the run record carries, and when to send an email versus stay silent.

| Pattern | Summary |
|---|---|
| [Show, don't decide](product-design/show-dont-decide.md) | Surface problems, don't auto-fix. Capability drift, model-fallback events, weekly memo proposals: all reported, none silently corrected. |
| [Friction as feature](product-design/friction-as-feature.md) | Every job must be rated. Silence is never approval. Issue dismissal is manual. Friction goes where mistakes compound. |
| [Status taxonomy](product-design/status-taxonomy.md) | 8 categories, not binary ok/fail. The Idle/Stale and Blocked/Error pairs map to different operator actions. |
| [Channel-choice rule](product-design/channel-choice-rule.md) | Chat for synchronous (approvals, alerts). Email for async (digests, reports). Dashboard for status. File-state for audit. |
| [Cost reconciliation UX](product-design/cost-reconciliation.md) | Three numbers (estimated, prepaid consumed, reconciled) plus variance, hero-level. Calibration UI, not a billing system. |
| [Usage classification](product-design/usage-classification.md) | `usage: cron / manual / subprocess / chained / emergency / deprecated` as a queryable manifest field on every skill. |
| [Lifecycle + retention](product-design/lifecycle-and-retention.md) | Three retention layers (mechanical, curated, deprecation-not-deletion). Nothing disappears. Things age explicitly. |

Most of these are the opposite of what an engineer would naturally choose. Engineers optimize for fewer steps and automatic resolution. Operators want to know what is happening and decide what to do about it. Each tradeoff favors operator clarity over engineering convenience.

## Cost-optimization receipts

Numbers I can back up from production:

- **Manager-agent context: 21K → 4.5K tokens per session (79% reduction).** The standup and noon checkup loaded the full agent profile registry. They now load a compressed digest with the same operational signal.
- **Haiku batch size 6 → 20: ~64% fewer API calls per qualify cycle.** Previous size kept the verbose-JSON Gemini fallback under output-token limits. A separate `HAIKU_BATCH_SIZE` for the primary path does not have that constraint.
- **SQLite dedup vs four JSON caches.** Cross-skill queryable in microseconds. No more drift between scanners.
- **URL-shape gate before LLM.** Regex validators drop fabricated `https://example.com/post/abc` URLs, an LLM hallucination pattern, before they enter the dedup table or hit a Haiku batch.
- **Model rotation.** Scanners moved Sonnet → Haiku/Flash via the MCP migration. Lower-stakes manager jobs moved to gpt-4o-mini. Operator rating signal stayed flat through both moves. That data gave me confidence the cost cut was not a quality cut.

Compounding effect: roughly an order-of-magnitude reduction in cost per completed job versus the naive per-row loop the system started with. Lesson: **order matters more than speed.** A microsecond regex check that runs first is more valuable than a millisecond optimization in the model call.

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
