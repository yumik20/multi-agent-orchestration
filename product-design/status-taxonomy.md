# Status taxonomy

The dashboard classifies every agent's operational state into one of 8 categories. Not 2 (ok/fail), not 3 (ok/warning/error). Eight.

## The categories

| Status | Meaning | Operator action |
|---|---|---|
| `Running` | Actively executing a scheduled task right now or within the current run window | None. Watch. |
| `Scheduled` | Has work expected; not yet running | None. The schedule will trigger it. |
| `Completed` | Finished its scheduled work for the period (day or week) | None. Reassuring signal. |
| `Idle` | No work expected right now (no schedule due) | None. Distinct from Stale. |
| `Blocked` | Waiting on an external dependency (auth, credential, upstream service) | Resolve the dependency. |
| `Error` | Internal failure: last run exited with an error | Investigate the failure. Retry or fix. |
| `Stale` | Work was expected but hasn't run | Investigate why the schedule didn't fire. |
| `Unknown` | Not enough schedule or execution data to classify | Backfill data or wait for first run. |

## Why this granularity

The two pairs that matter most are `Idle` vs `Stale` and `Blocked` vs `Error`.

**`Idle` vs `Stale`.** Both look like "the agent isn't running." They mean opposite things to an operator. `Idle` means the system is healthy and there's no work due. `Stale` means there *was* work due, it didn't fire, and the system has lost track of why. A binary "ok / not running" status would collapse both into noise; the operator can't tell which is the alarm.

**`Blocked` vs `Error`.** Both look like "the agent didn't finish." They lead to different fixes. `Blocked` means an upstream dependency (an API auth token, a credential file, a network call to a third-party) needs operator action; the agent code is fine. `Error` means the agent's own execution path failed; the agent code might need a fix. Confusing them sends the operator down the wrong investigation path.

The other categories (`Scheduled`, `Running`, `Completed`, `Unknown`) handle the natural states of an agent's day so the dashboard doesn't have to lie about what's happening (a `Running` agent shouldn't be shown as `Idle` just because the binary status enum has no other option).

## The status-to-tone mapping

Each status maps to a UI tone:

- `Blocked` and `Error` → critical (red). Both demand action.
- `Stale` → warning (yellow). Developing problem; investigate before it escalates.
- `Running` and `Scheduled` → ok (green). Healthy motion.
- `Idle`, `Completed`, `Unknown` → neutral (gray). Don't compete for attention.

The mapping is consistent across every panel that shows agent status. Pattern recognition is faster when red always means the same thing.

## What this replaces

Most agent dashboards I've seen show one of:

- A boolean "healthy / unhealthy" heartbeat
- A 3-state traffic light (ok / warning / error)
- Raw exit codes per run

Each of those collapses operator-actionable distinctions. An operator looking at "yellow" can't tell if it's "Stale because the cron didn't fire," "Blocked because the source revoked the auth token," or "Error because a Python regex broke." Three different fixes; one dashboard color.

The 8-category taxonomy is more code than a boolean and more visual variety than a traffic light. It pays back the moment the operator opens the dashboard at 9 AM and needs to triage the morning's run results in under 30 seconds.
