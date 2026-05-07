# Knowledge Base Wiki — Index

This is the catalog of maintained knowledge pages. **Read this first.** Every wiki page should appear here under exactly one category. Pages not listed here are orphans — the lint-heal skill will flag them.

---

## Core Concepts

The foundational thesis layer. The project's domain claims and why they hold.

| Page | Type | Confidence | Updated | Role |
|---|---|---|---|---|
| `thesis-map.md` | concept | medium | 2026-04-16 | Core thesis, top-level claim map (working claims with evidence anchors, institutional validation layer) |
| `behavioral-context.md` | concept | — | — | Definition and explanatory core concept |

## Use Cases

Canonical use-case families — what real problems the project's domain addresses.

| Page | Type | Confidence | Updated | Role |
|---|---|---|---|---|
| `use-cases.md` | use-case | medium | 2026-04-20 | Canonical use-case families + mapping |

## Evidence

External proof points, practitioner quotes, market validators.

| Page | Type | Confidence | Updated | Role |
|---|---|---|---|---|
| `evidence-log.md` | evidence | medium | 2026-04-21 | Reusable proof points (append-heavy log) |

## Guardrails

Approved language, constraints, competitive framing — safe-to-publish content rules.

| Page | Type | Confidence | Updated | Role |
|---|---|---|---|---|
| `claims-and-guardrails.md` | guardrail | — | — | Approved language, constraints, public-safe framing |

## Allowlists

Target filters used by scanners and qualification.

| Page | Type | Confidence | Updated | Role |
|---|---|---|---|---|
| `allowlist-organizations.md` | allowlist | high | 2026-04-15 | Tier 1-3 organization targets |
| `allowlist-roles.md` | allowlist | — | — | Role/title filters for qualification |

## Reference

Templates and schemas consumed by other pages + agents.

| Page | Type | Confidence | Updated | Role |
|---|---|---|---|---|
| `TEMPLATE.md` | reference | — | — | Page-creation template + frontmatter schema |
| `voice-models.md` | reference | high | 2026-04-12 | Voice rubric used by the creator skills when drafting |

---

## Coverage Targets

The wiki should continuously improve coverage across these areas. The ingest skill promotes qualified findings to the pages that strengthen these targets. The lint-heal skill computes coverage per target weekly.

- `domain-context` — the project's behavioral context as a category
- `informal-networks` — who-knows-whom signals invisible to formal org charts
- `authority-routing` — who actually decides vs. who's titled
- `decision-intelligence` — how decisions actually flow in the domain
- `adoption-friction` — why pilots stall, where deployment loses momentum
- `knowledge-loss` — SME departures, tribal knowledge, relationship context

---

## Page Role Definitions

- **concept** — foundational ideas that define the thesis. Stable, update carefully.
- **use-case** — named scenario patterns. Grow these actively.
- **evidence** — append-heavy collection of sourced proof points.
- **guardrail** — rules for what to say / not say publicly. Update only with operator approval.
- **allowlist** — scanner + qualification filter lists. Grow from qualified findings.
- **reference** — schemas, templates, internal docs. Edit only when the format itself changes.
- **lint-report** — generated weekly by the lint-heal skill, written to `../lint-heal/reports/`.

---

## Operations

- **Ingest** — `skills/ingest/SKILL.md` — promote qualified findings into these pages.
- **Query** — `qa-agent/query-workflow.md` — answer from wiki first, use raw only for gaps.
- **Lint** — `skills/lint-heal/SKILL.md` — weekly health check.
- **Change log** — `../log.md` — every ingest, angle, lint, and writeback is recorded there in `[YYYY-MM-DD HH:MM] event | title` format.
