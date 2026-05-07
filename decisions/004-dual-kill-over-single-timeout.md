# ADR-004: Dual-kill watchdog over a single absolute timeout

**Status:** accepted  
**Date:** 2026-03

## Context

A scanner is a 30-90 minute browser-automation job. The naive subprocess wrapper had a single absolute timeout: kill the process after `total_timeout_seconds`. This worked, but it produced two failure modes I didn't anticipate.

**Failure mode 1: silent stall.** A scanner would lose its browser session at minute 4, fail to detect it, sit in a busy loop for the remaining 86 minutes, then get force-killed at the timeout boundary. Result: 86 minutes of wasted compute, no useful output, and the operator finding out 90 minutes later that the morning scan never produced.

**Failure mode 2: violent kill at the boundary.** A scanner that was actually still working would get SIGKILL'd at minute 90 mid-write, leaving a half-written CSV that the next stage of the pipeline would fail to parse. Result: a clean run looked like a malformed-output run.

## Options considered

**Option A: Status quo.** Live with both failure modes. They were rare-ish (~weekly).

**Option B: Larger absolute timeout.** Buys more time but doesn't solve either failure mode — silent stalls still waste the whole window, and the kill is still violent at the boundary.

**Option C: Output-stall detector.** Watch the output file's mtime. If nothing's been written for `STALL_SECONDS`, send SIGTERM. Solves the silent-stall case. Doesn't help with the violent-kill problem.

**Option D: Dual kill rules.** Both stall detection AND wall-time, with a graceful SIGTERM-then-SIGKILL ladder for both. Each failure mode gets its own detection signal; both produce a graceful shutdown that flushes partial work.

## Decision

Option D. The watchdog runs two timers concurrently:

1. **Wall-time timer.** Counts up from process start. At `total_timeout_seconds`, send SIGTERM with a 60s grace window for partial-work flush. SIGKILL at grace expiry.

2. **Output-stall timer.** Watches the configured output file's mtime. Resets every time the file is written. After `stall_timeout_seconds` of no writes (default 240s), the wall-time timer is shortened to fire immediately — same SIGTERM-grace-SIGKILL ladder, but triggered by silence instead of duration.

The ladder is the key part. SIGTERM with a 60s grace is what lets a scanner save a partial CSV, write a status entry to its state file, and exit cleanly. Without the grace, partial work is lost and the next pipeline stage gets a malformed file.

## Consequences

- **Silent stalls now kill at minute 5, not minute 90.** A scanner that loses its browser session and stops writing gets SIGTERM'd 4 minutes later. The 90-minute window is no longer available to be wasted by a non-working process.
- **Real runs flush partial work.** A scanner near the absolute timeout boundary gets a 60s warning to write what it has. The next pipeline stage sees a valid (smaller) CSV instead of a malformed one. This recovered ~4-5 hours of "looked like garbage but was actually a clean stretch of output" data per month.
- **The watchdog itself is one Python module.** ~150 lines, no extra deps. The main loop sleeps in 1s ticks, checks both timers, decides whether to escalate.
- **One non-obvious bug.** Early versions of the stall detector only checked the explicit `csv_path_hint`. Some scanners write multiple output files; the detector missed the active write to a different file and killed a still-working process. Fix was to optionally accept a list of paths, with the OR being "any file written within stall window."

## What we'd do differently

- **Default the stall detector ON.** First version made it opt-in via a `stall_timeout_seconds` parameter. Operators forgot to pass it and got the old single-timeout behavior. Should have been default-on with a constant from day one.
- **Accept multiple output paths.** As above. Scanners write multiple files; the watchdog should accept a glob or list, not a single hint.

## Lesson named

A 90-minute timeout is not a 90-minute kill — it's a guarantee about wall-time, not a guarantee about useful work. Output-stall detection is what tells you whether the process is alive in a useful sense, separate from whether it's alive in a process-table sense.
