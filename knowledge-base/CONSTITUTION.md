# AGENTS.md

# BehaviorGraph KMspace Constitution

This file is the operating constitution for the local BehaviorGraph knowledge workspace.

The goal is to maintain a durable markdown knowledge artifact that compounds in quality over time.

## Scope

This workspace governs:

- ingest of new source material
- qualification of scan outputs
- promotion of raw material into maintained knowledge
- query behavior
- durable writeback
- linting and maintenance

It does not govern day-to-day agent execution outside this `kmspace/` folder.

## Layer Semantics

### `sources/`

Purpose:
- immutable references to source-of-truth material
- source maps, inventories, and canonical file lists

Rules:
- do not rewrite the source truth here into prose pages
- do not treat `sources/` as the answer layer
- if a source changes materially, update the reference map, not the source itself

### `raw/`

Purpose:
- intake buffer for new material
- append-heavy evidence staging area

Rules:
- new materials land here first unless they are already canonical sources
- preserve source phrasing as much as possible
- do not over-clean raw notes
- preserve raw artifacts; do not replace them with cleaned summaries
- every ingest must be logged in `raw/ingest-log.md`
- every qualification decision must be logged in `raw/qualification-log.md`
- accepted qualification records live under `raw/qualified/`
- rejected qualification records live under `raw/rejections/`

### `wiki/`

Purpose:
- maintained reusable knowledge layer

Rules:
- this is the primary answer layer
- every wiki page must follow `wiki/TEMPLATE.md`
- update pages in place instead of creating near-duplicates
- every claim should point to supporting evidence or source paths
- if confidence is low, mark it explicitly
- do not silently overwrite a canonical page; material changes require a paired writeback record
- if a rewrite materially changes interpretation or structure, snapshot the prior page under `wiki/history/`

### `qa-agent/`

Purpose:
- deterministic query and answer workflow

Rules:
- answer from `wiki/` first
- use `raw/` only to supplement unresolved gaps
- if an answer produces durable synthesis, save it back into `wiki/` or `output/`

### `output/`

Purpose:
- durable generated deliverables derived from the wiki

Rules:
- do not treat outputs as primary knowledge unless promoted back into `wiki/`
- every saved output must be logged in `output/writeback-log.md`
- structured writeback records live under `output/records/`

### `lint-heal/`

Purpose:
- quality control for the maintained knowledge layer

Rules:
- lint should check stale pages, weak sourcing, contradictions, broken links, and orphan pages
- healing should propose deterministic fixes before broad rewrites

## Canonical Operating Rules

1. Sources are immutable references.
2. Raw is for intake, not permanent synthesis.
3. Qualification is explicit, auditable, and reversible.
4. Wiki is the maintained knowledge artifact.
5. Durable synthesis belongs on disk, not only in chat.
6. Prefer updating an existing page over creating a new overlapping page.
7. Every meaningful wiki change updates `log.md`.
8. Every new ingest updates `raw/ingest-log.md`.
9. Every qualification decision updates `raw/qualification-log.md`.
10. Every durable saved answer or deliverable updates `output/writeback-log.md`.

## Page Types

Allowed wiki page types:

- `concept`
- `claim-map`
- `use-case-map`
- `evidence-log`
- `glossary`
- `answer-note`

Qualification dispositions:

- `accepted`
- `rejected`
- `deferred`

## Required Page Metadata

Every wiki page should start with simple frontmatter:

```yaml
---
title: ""
type: concept
status: active
updated: YYYY-MM-DD
confidence: high
sources:
  - path/to/source
tags:
  - topic
---
```

Allowed values:

- `status`: `active`, `draft`, `needs-review`, `stale`
- `confidence`: `high`, `medium`, `low`

## Ingest Workflow

When new material arrives:

1. decide if it is canonical source material or raw intake
2. if canonical, add or update a reference in `sources/`
3. if operational evidence, save it in `raw/`
4. record:
   - date
   - source path
   - source type
   - short summary
   - promotion target
in `raw/ingest-log.md`

## Qualification Workflow

For each raw scan artifact that may affect maintained knowledge:

1. preserve the original raw artifact path
2. create a qualification record from `schemas/qualification-record.md`
3. assign one disposition:
   - `accepted`
   - `rejected`
   - `deferred`
4. record the decision in `raw/qualification-log.md`
5. if accepted, save the record under `raw/qualified/`
6. if rejected, save the record under `raw/rejections/`
7. rejection records must include explicit reasons and the evidence or guardrail that caused rejection

## Promotion Workflow

When raw material is mature enough:

1. locate the best existing wiki page
2. update that page in place if the concept already exists
3. create a new wiki page only if the concept does not already have a durable home
4. if updating an existing canonical page, create a writeback record first
5. for material rewrites, snapshot the current page into `wiki/history/`
6. add or update:
   - summary
   - why it matters
   - evidence
   - source paths
   - related pages
7. update `wiki/index.md`
8. append a line to `log.md`

## Query Workflow

When answering a question:

1. start from `wiki/index.md`
2. read the most relevant wiki pages
3. use `sources/` and `raw/` only if the wiki is missing support
4. answer from the maintained knowledge layer whenever possible
5. if the answer creates a reusable synthesis, save it as:
   - update to an existing wiki page, or
   - new `wiki/answer-*.md`, or
   - durable file in `output/`
6. if saving durable knowledge, also create a writeback record

## Writeback Rules

Write back when:

- the answer clarifies a recurring thesis point
- the answer consolidates evidence from multiple pages
- the answer resolves ambiguity that will likely recur
- the answer introduces a durable comparison, framing, or objection-handling pattern

Do not write back when:

- the answer is purely one-off
- the answer is still speculative
- the answer is duplicated elsewhere already

Writeback requirements:

1. create a record from `schemas/writeback-record.md`
2. log it in `output/writeback-log.md`
3. if updating a canonical wiki page, record:
   - target path
   - prior state summary
   - source inputs
   - change intent
   - rollback instruction

## Lint Rules

Check for:

- stale `updated` dates
- missing `sources`
- weak claims without evidence
- pages not linked from `wiki/index.md`
- duplicated concepts across multiple pages
- broken internal file references
- contradiction between wiki claims and approved claims / guardrails
- qualification records missing disposition or rationale
- rejected artifacts missing inspectable reasons
- canonical wiki updates that lack a paired writeback record

## Determinism Rule

Prefer deterministic, inspectable markdown operations:

- file append
- page update
- index update
- log entry

Avoid hidden state, opaque databases, or chat-only memory for anything durable.
