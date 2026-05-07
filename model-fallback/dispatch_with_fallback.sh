#!/usr/bin/env bash
# dispatch_with_fallback.sh — run an agent with auto-fallback to a
# second model if the primary dies in <PRIMARY_MIN_RUNTIME_SEC with zero
# meaningful output. Catches the silent-death pattern where a primary
# endpoint times out and leaves the spawn dead with no real error.
#
# Usage:
#   dispatch_with_fallback.sh <agent_id> <fallback_model> <message>
#
# Example:
#   ./dispatch_with_fallback.sh \
#     creator anthropic/claude-sonnet-4-6 \
#     "Run the publishing flow for post 'X'..."
#
# When fallback fires, an event is appended to:
#   ~/workspace/skills/_shared/runs/YYYY-MM/fallbacks.jsonl
# so the weekly memo can spot patterns ("creator fell back 4× this week").
#
# Tunable thresholds:
#   PRIMARY_MIN_RUNTIME_SEC=180   below this + no output = treat as dead
#   PRIMARY_MIN_OUTPUT_BYTES=200  output below this = no output

set -u

AGENT_ID="${1:?agent_id required}"
FALLBACK_MODEL="${2:?fallback_model required}"
MESSAGE="${3:?message required}"

PRIMARY_MIN_RUNTIME_SEC="${PRIMARY_MIN_RUNTIME_SEC:-180}"
PRIMARY_MIN_OUTPUT_BYTES="${PRIMARY_MIN_OUTPUT_BYTES:-200}"

RUNS_DIR="$HOME/workspace/skills/_shared/runs/$(date +%Y-%m)"
FALLBACK_LOG="$RUNS_DIR/fallbacks.jsonl"
LOG_DIR="$HOME/workspace/logs"
mkdir -p "$LOG_DIR" "$RUNS_DIR"

# Locate the agent runtime CLI. Project-specific — replace `agent_cli`
# with whatever your runtime exposes.
AGENT_CLI="$(command -v agent_cli || true)"
[ -x "$AGENT_CLI" ] || { echo "agent_cli not found in PATH" >&2; exit 127; }

primary_started=$(date +%s)
primary_started_iso=$(date -u +%Y-%m-%dT%H:%M:%SZ)

PRIMARY_OUT="$LOG_DIR/dispatch-primary-$$.out"
PRIMARY_ERR="$LOG_DIR/dispatch-primary-$$.err"

"$AGENT_CLI" agent --local --agent "$AGENT_ID" --message "$MESSAGE" --json \
    > "$PRIMARY_OUT" 2> "$PRIMARY_ERR"
primary_rc=$?
primary_finished=$(date +%s)
primary_runtime=$(( primary_finished - primary_started ))
primary_bytes=$(wc -c < "$PRIMARY_OUT" | tr -d ' ')

# Decide if we need to fall back. Specifically: non-zero exit AND
# fast death AND no real output. Real errors with stderr OR long runs
# OR runs that produced output are NOT retried — they already cost
# the same as a manual retry would and are unlikely to improve.
need_fallback=0
fallback_reason=""
if [ "$primary_rc" -ne 0 ] \
   && [ "$primary_runtime" -lt "$PRIMARY_MIN_RUNTIME_SEC" ] \
   && [ "$primary_bytes" -lt "$PRIMARY_MIN_OUTPUT_BYTES" ]; then
    need_fallback=1
    fallback_reason="exit=$primary_rc runtime=${primary_runtime}s output=${primary_bytes}B"
fi

if [ "$need_fallback" -eq 1 ]; then
    echo "[dispatch_with_fallback] primary died fast ($fallback_reason); falling back to $FALLBACK_MODEL" >&2

    fallback_started_iso=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    FALLBACK_OUT="$LOG_DIR/dispatch-fallback-$$.out"
    FALLBACK_ERR="$LOG_DIR/dispatch-fallback-$$.err"

    "$AGENT_CLI" agent --local --agent "$AGENT_ID" \
        --model "$FALLBACK_MODEL" --message "$MESSAGE" --json \
        > "$FALLBACK_OUT" 2> "$FALLBACK_ERR"
    fallback_rc=$?
    fallback_finished_iso=$(date -u +%Y-%m-%dT%H:%M:%SZ)

    # Log the fallback event for the weekly memo.
    python3 -c "
import json
record = {
    'event': 'model_fallback',
    'agent': '$AGENT_ID',
    'fallback_model': '$FALLBACK_MODEL',
    'primary_started': '$primary_started_iso',
    'primary_runtime_s': $primary_runtime,
    'primary_output_bytes': $primary_bytes,
    'primary_exit': $primary_rc,
    'fallback_started': '$fallback_started_iso',
    'fallback_finished': '$fallback_finished_iso',
    'fallback_exit': $fallback_rc,
    'reason': '$fallback_reason',
    'message_preview': '''$MESSAGE'''[:200],
}
with open('$FALLBACK_LOG', 'a') as f:
    f.write(json.dumps(record, ensure_ascii=False) + '\n')
" 2>/dev/null

    cat "$FALLBACK_OUT"
    [ -s "$FALLBACK_ERR" ] && cat "$FALLBACK_ERR" >&2
    rm -f "$PRIMARY_OUT" "$PRIMARY_ERR" "$FALLBACK_OUT" "$FALLBACK_ERR"
    exit "$fallback_rc"
fi

# Primary succeeded, or failed in a way we don't retry (long runtime,
# real output, or actual error message).
cat "$PRIMARY_OUT"
[ -s "$PRIMARY_ERR" ] && cat "$PRIMARY_ERR" >&2
rm -f "$PRIMARY_OUT" "$PRIMARY_ERR"
exit "$primary_rc"
