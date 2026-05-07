# Cost Optimization Patterns

Three independently-deployable patterns plus one config approach. Together they take a typical scanner pipeline from "single sequential LLM-call-per-row" to "batched + cached + dedup-aware."

## What's here

- `prompt_cache.py` — wires Anthropic `cache_control: ephemeral` onto stable system prompts. Cached portion gets ~90% input-token discount on subsequent calls within 5 minutes. Forward-compatible: silently no-ops when the cached prefix is below the model's minimum cacheable size (Haiku needs ≥2048 tokens; Sonnet ≥1024). The same file shows model-aware batch sizing built on top of the cached call (verbose JSON-emitting fallback models stay at 6 items/call to avoid response truncation; terse-array models scale to 20 items/call — on the production workload, drops API call count from 14 → 5 per qualify cycle, ~64% fewer calls, ~25–30% net token reduction).
- `sqlite_dedup.py` — replaces a JSON-file dedup cache with a SQLite-backed 30-day rolling window. WAL-mode incremental writes, indexed lookups in microseconds, queryable cross-skill via an MCP tool.
- `agent_models_md.py` — config-as-source-of-truth: parse a markdown table at request time to derive runtime model assignments. Editing the markdown moves the system. No hardcoded model strings to drift from intent.

## The compounding effect

These layer:

```
raw row
  │
  ▼  smart_dedup     ← if URL seen in last 30 days, skip entirely
  │                   ~50% reduction on a typical morning scan
  │
  ▼  output_contract ← drop malformed URLs before LLM
  │                   ~5% reduction on hallucinated rows
  │
  ▼  batch_qualify   ← 20-row Haiku batches instead of 6
  │                   ~64% fewer API calls vs naive per-row
  │
  ▼  prompt_cache    ← cached system prefix when system grows past minimum
                       ~90% off the prefix on repeat calls within 5 min
```

A scanner that previously made 50 sequential per-row Sonnet calls now makes 3 batched Haiku calls with a cached system prefix. The cost-per-finished-job improvement is order-of-magnitude.

## Operational lesson

The biggest single win wasn't any one pattern — it was **pushing the cheap checks earlier in the pipeline**. URL-shape regex at microseconds runs before dedup at milliseconds runs before LLM batches at seconds. Each stage's output is smaller, so the next stage costs less. Order matters more than speed of any individual stage.
