# Writeback Record Schema

Use this template for any durable answer, canonical wiki update, or reversal.

```yaml
---
writeback_id: wb-YYYY-MM-DD-slug
created: YYYY-MM-DD
target_path: wiki/or/output/path
mode: update
source_answer: chat-or-query-reference
source_inputs:
  - wiki/page.md
prior_snapshot: wiki/history/page--YYYYMMDD.md
decided_by: llm-or-human
review_status: final
reversible: true
---
```

Sections:

1. `Intent`
2. `Change Summary`
3. `Source Inputs`
4. `Why Durable`
5. `Rollback Instruction`
6. `Resulting Paths`

Rules:

- every canonical wiki update should have a writeback record
- `prior_snapshot` should be `n/a` only when the target is newly created
- `Rollback Instruction` should state the exact file to restore or the exact deletion to perform
