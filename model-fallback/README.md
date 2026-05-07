# Model-Fallback Dispatcher

A bash wrapper around any agent runtime call. Detects the failure pattern "primary model dies in <180s with <200B output" and auto-retries on a configurable fallback model, logging a `model_fallback` event to a structured JSONL.

## Why this exists

A primary endpoint going dark doesn't always surface a real error. The agent runtime returns "exit code 1, no output" and the operator manually restarts with a different model. By the third manual escalation in a week, you've lost three afternoons.

The wrapper makes fallback **infrastructure**, not workflow:
- Detects the dead-fast-with-no-output signature deterministically
- Retries on the fallback model
- Tags the run record so the weekly memo can spot fallback drift ("creator agent fell back 4× this week — primary endpoint is unhealthy")

## Usage

```bash
~/workspace/skills/_shared/dispatch_with_fallback.sh \
    creator anthropic/claude-sonnet-4-6 \
    "Run the publishing flow for post 'X'…"
```

If primary dies in <180s with <200B output, retries on `anthropic/claude-sonnet-4-6` and appends to `~/workspace/skills/_shared/runs/YYYY-MM/fallbacks.jsonl`:

```json
{
  "event": "model_fallback",
  "agent": "creator",
  "fallback_model": "anthropic/claude-sonnet-4-6",
  "primary_started": "2026-05-06T14:23:18Z",
  "primary_runtime_s": 117,
  "primary_output_bytes": 0,
  "primary_exit": 1,
  "fallback_started": "2026-05-06T14:25:15Z",
  "fallback_finished": "2026-05-06T14:46:40Z",
  "fallback_exit": 0,
  "reason": "exit=1 runtime=117s output=0B",
  "message_preview": "Run the publishing flow for post 'X'..."
}
```

## Tunable thresholds

| Env var | Default | Purpose |
|---|---|---|
| `PRIMARY_MIN_RUNTIME_SEC` | 180 | Below this + no output = treat as dead |
| `PRIMARY_MIN_OUTPUT_BYTES` | 200 | Output below this = no output |

## Why this signature, not something fancier

A "real" error has stderr text. A real run has either output bytes or a long enough runtime to be an actual run. The wrapper specifically catches the silent-death case where neither happens. False positives on real errors with stderr are fine — those usually fail again on retry anyway, and the retry is the same cost as a manual one. False positives on slow-but-real runs are avoided by the runtime threshold.
