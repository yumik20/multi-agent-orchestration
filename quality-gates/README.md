# Quality Gates: Three Independent Validators

Three validators that run in increasing cost order. Cheap structural checks happen first; expensive LLM judges happen last and only on what survived.

```
raw output
    │
    ▼ [output_contract]   regex URL-shape check     ~microseconds
    │
    ▼ [artifact_gate]     schema validator          ~milliseconds
    │
    ▼ [hallucination]     LLM-judge tri-state       ~seconds, $$
    │
    ▼ ship
```

## Files

- `output_contract.py` — per-source URL-shape regex; drops malformed rows before they hit the dedup table or the LLM. Microseconds per call.
- `artifact_gate.py` — declarative schema validator for structured agent outputs. Marker-based opt-in (only files with `class: <known>` frontmatter validate). Tri-state: pass / uncertain / fail.
- `hallucination_validator.py` — LLM-judge with three supervision levels (NORMAL / STRICT / PARANOID), four issue categories with static severities the judge can't game, and a 0.3 hard floor below which results always fail.

## Design choices

**Cheap checks first.** A URL regex takes microseconds; a Haiku batch costs cents. Run cheap checks first so expensive checks only see clean inputs.

**Tri-state, never boolean.** Pass / uncertain / fail. "Uncertain" lets the pipeline keep moving with a warning + retry suggestion instead of a hard block. Boolean gates produce too many false positives that block real work.

**Marker-based opt-in for the artifact gate.** Validation only fires when the artifact's frontmatter declares a class (`class: blog-draft`). Files without the marker pass silently — never accidentally validate a config file because its path matched a pattern.

**Static severities the judge can't game.** Hallucination categories have fixed weights — `unverifiable_claim: 0.4`, `contradicted_by_tool_results: 0.6`, etc. The judge can identify issues but can't decide their severity. Prevents "I'm 90% confident this is fine" loophole.

**Fail-loud, never silently mutate.** Gates report verdicts. Callers decide whether to retry, escalate, or override. The gate is not the policy enforcement point.
