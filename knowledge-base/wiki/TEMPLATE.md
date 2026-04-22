---
title: ""
page_id: ""
type: concept
status: draft
updated: YYYY-MM-DD
confidence: medium
canonical: true
sources:
  - path/to/source
tags:
  - behaviorgraph
coverage_tags:
  - org-context
related_pages:
  - other-page.md
evidence_count: 0
last_lint_date: YYYY-MM-DD
---

# Title

## Summary

One short paragraph answering what this page is about.

## Why It Matters

Why this concept matters for BehaviorGraph, enterprise AI, or content strategy.

## Main Claims

- claim 1
- claim 2
- claim 3

## Evidence

- evidence item with source path
- evidence item with source path

## Qualification Notes

- why this information was accepted into the maintained wiki
- any important exclusions or rejection boundaries

## Use Case Support

- which use cases this page strengthens

## Related Pages

- `other-page.md`

## Open Questions

- unresolved question

## Source Paths

- `path/to/source`

## Change Notes

- YYYY-MM-DD: short description of the most recent material update

---

## Frontmatter field reference

**Required fields:**
- `title` — human-readable page title
- `type` — `concept` | `use-case` | `evidence` | `guardrail` | `allowlist` | `reference` | `lint-report`
- `status` — `draft` | `active` | `stale` | `needs-review` | `deprecated`
- `updated` — YYYY-MM-DD of last material edit (MUST be bumped on any non-cosmetic change)
- `confidence` — `low` | `medium` | `high` (how well-sourced the page is)
- `sources` — list of file paths to source docs backing this page (sources/ or raw/)
- `tags` — freeform tags (e.g., `behaviorgraph`, `enterprise-ai`)

**Optional but recommended (for lint + coverage tracking):**
- `page_id` — short stable slug (kebab-case, e.g., `authority-routing`)
- `canonical` — `true` if this is the canonical page on its topic
- `coverage_tags` — which `wiki/index.md` coverage targets this page contributes to
- `related_pages` — explicit cross-link list (lint will verify these files exist)
- `evidence_count` — number of proof points (updated when Evidence section changes)
- `last_lint_date` — YYYY-MM-DD when `kmspace-lint-heal` last validated this page
