# Qualification Record Schema

Use this template for any scan artifact that is evaluated for promotion into maintained knowledge.

```yaml
---
qualification_id: q-YYYY-MM-DD-slug
created: YYYY-MM-DD
raw_artifact: raw/path/to/file
source_ref: sources/path/or/external-reference
artifact_type: scan-output
disposition: accepted
proposed_target: wiki/page.md
decided_by: llm-or-human
review_status: final
reason_codes:
  - supported
tags:
  - topic
---
```

Sections:

1. `Artifact Summary`
2. `Qualification Checks`
3. `Decision Rationale`
4. `Target Wiki Page`
5. `Linked Evidence`
6. `Rejection Reason`
7. `Next Action`

Rules:

- `raw_artifact` must point to the preserved raw file
- `disposition` must be one of `accepted`, `rejected`, `deferred`
- rejected records must fill `Rejection Reason`
- accepted records must fill `Target Wiki Page`
