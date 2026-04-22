# Scan Qualification Workflow

Use this workflow when a scan output may become maintained knowledge.

## Goal

Convert scan findings into durable, auditable knowledge without losing the original raw artifact.

## Steps

1. Preserve the raw artifact in `raw/`.
2. Add the artifact to `raw/ingest-log.md`.
3. Create a qualification record from `schemas/qualification-record.md`.
4. Evaluate:
   - support quality
   - novelty
   - relevance to BehaviorGraph thesis or use cases
   - conflict with approved claims or guardrails
   - duplication with existing wiki pages
5. Assign one disposition:
   - `accepted`
   - `rejected`
   - `deferred`
6. Save the qualification record:
   - `raw/qualified/` for accepted
   - `raw/rejections/` for rejected
7. Update `raw/qualification-log.md`.
8. If accepted, promote the useful synthesis into the best existing wiki page or create a new page only if needed.
9. If a canonical page changes materially, create a writeback record first and snapshot the current page into `wiki/history/`.

## Acceptance Signals

- directly supports an existing thesis, claim, or use case
- adds durable evidence that is likely to recur in future answers
- improves a canonical page instead of fragmenting knowledge

## Rejection Signals

- unsupported or weakly sourced
- off-thesis or irrelevant
- stale, contradicted, or already superseded
- duplicative with no new value
