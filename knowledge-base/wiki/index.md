# enterprise AI Wiki — Index

This is the catalog of maintained knowledge pages. **Read this first.** Every wiki page should appear here under exactly one category. Pages not listed here are orphans — `kmspace-lint-heal` will flag them.

---

## Core Concepts

The foundational thesis layer. What enterprise AI is and why it exists.

| Page | Type | Confidence | Updated | Role |
|---|---|---|---|---|
| `thesis-map.md` | concept | medium | 2026-04-16 | Core thesis, top-level claim map (3 working claims, evidence-anchored, plus institutional validation layer) |
| `behavioral-context.md` | concept | — | — | Definition and explanatory core concept |

## Use Cases

Canonical use-case families — what real problems enterprise AI solves.

| Page | Type | Confidence | Updated | Role |
|---|---|---|---|---|
| `use-cases.md` | use-case | medium | 2026-04-20 | Canonical use-case families + mapping (now includes adoption-friction patterns around delegated agent identity and dependency without context transfer) |

## Evidence

External proof points, practitioner quotes, market validators, litigation signals.

| Page | Type | Confidence | Updated | Role |
|---|---|---|---|---|
| `evidence-log.md` | evidence | medium | 2026-04-21 | Reusable proof points (30 entries, now including Anthropic managed-agents evidence on runtime control infrastructure from 2026-04-21 morning findings) |

## Guardrails

Approved language, constraints, competitive framing — safe-to-publish content rules.

| Page | Type | Confidence | Updated | Role |
|---|---|---|---|---|
| `claims-and-guardrails.md` | guardrail | — | — | Approved language, constraints, public-safe framing |

## Allowlists

Target filters used by scanners (Matt) and qualification (kmspace-ingest).

| Page | Type | Confidence | Updated | Role |
|---|---|---|---|---|
| `allowlist-companies.md` | allowlist | high | 2026-04-15 | Tier 1-3 company targets (Snowflake added 2026-04-15 after governed-data partnership signal) |
| `allowlist-job-titles.md` | allowlist | — | — | Role/title filters for qualification |

## Reference

Templates and schemas consumed by other pages + agents.

| Page | Type | Confidence | Updated | Role |
|---|---|---|---|---|
| `TEMPLATE.md` | reference | — | — | Page-creation template + frontmatter schema |
| `voice-models.md` | reference | high | 2026-04-12 | Voice rubric — Levie / Mollick / Grant; Tommy picks one per post |

---

## Coverage Targets

The wiki should continuously improve coverage across these areas. `kmspace-ingest` promotes qualified findings to the pages that strengthen these targets. `kmspace-lint-heal` computes coverage per target weekly.

- `org-context` — organizational behavioral context as a category
- `informal-networks` — who-knows-whom signals invisible to org charts
- `authority-routing` — who actually decides vs. who's titled
- `decision-intelligence` — how enterprise decisions actually flow
- `workforce-intelligence` — behavioral vs. analytical HR signals
- `enterprise-ai-context-layer` — LEAD as the missing layer
- `ai-governance-adjacency` — litigation, audits, governance pressure
- `adoption-friction` — why AI pilots stall at 12 users, 95% failure rates
- `knowledge-loss` — SME departures, tribal knowledge, relationship context
- `onboarding-gap` — new hires vs. invisible internal work

---

## Page Role Definitions

- **concept** — foundational ideas that define the thesis. Stable, update carefully.
- **use-case** — named scenario patterns for content + outreach. Grow these actively.
- **evidence** — append-heavy collection of sourced proof points.
- **guardrail** — rules for what to say / not say publicly. Update only with Yumi approval.
- **allowlist** — scanner + qualification filter lists. Grow from qualified findings.
- **reference** — schemas, templates, internal docs. Edit only when the format itself changes.
- **lint-report** — generated weekly by `kmspace-lint-heal`, written to `../lint-heal/reports/`.

---

## Operations

- **Ingest** — `skills/kmspace-ingest/SKILL.md` — promote qualified findings into these pages.
- **Query** — `qa-agent/query-workflow.md` — answer from wiki first, use raw only for gaps.
- **Lint** — `skills/kmspace-lint-heal/SKILL.md` — weekly Sunday 3 AM PT health check.
- **Change log** — `../log.md` — every ingest, angle, lint, and writeback is recorded there in `[YYYY-MM-DD HH:MM] event | title` format.
