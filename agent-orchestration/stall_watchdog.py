def run_collector_with_stall_watchdog(
    cmd: list,
    *,
    total_timeout_seconds: int,
    stall_timeout_seconds: int,
    csv_path_hint: str | Path | None = None,
    poll_interval_seconds: float = 2.0,
) -> tuple:
    """Subprocess wrapper that enforces TWO kill rules:

      1. Absolute timeout — if the subprocess runs longer than
         total_timeout_seconds, it's SIGKILLed.
      2. CSV-stall timeout — if csv_path_hint is provided and that file
         hasn't been modified for stall_timeout_seconds, the subprocess
         is SIGKILLed. This catches "collector is alive but wedged"
         situations (Chrome backgrounded, LLM hanging on a handle, etc).

    Returns (returncode, stdout, stderr, timed_out, stall_killed).
    stdout/stderr are the captured text. When either watchdog fires,
    returncode is -9 (SIGKILL) and the corresponding flag is True.

    Note: this replaces subprocess.run(..., timeout=) in collectors that
    write to a known CSV. For collectors without an obvious CSV progress
    signal, pass csv_path_hint=None and only the absolute timeout applies."""
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    start = time.time()
    # Track CSV mtime progress. "last_progress_at" is the most recent time
    # we observed growth (or the scan start if the CSV didn't exist yet).
    last_mtime = 0.0
    last_progress_at = start
    csv_existed_at_start = False
    if csv_path_hint:
        csv_path = Path(csv_path_hint)
        if csv_path.exists():
            csv_existed_at_start = True
            last_mtime = csv_path.stat().st_mtime

    timed_out = False
    stall_killed = False
    kill_reason = ""

    while True:
        rc = proc.poll()
        if rc is not None:
            break
        elapsed = time.time() - start
        if elapsed > total_timeout_seconds:
            timed_out = True
            kill_reason = f"absolute timeout after {int(elapsed)}s (cap {total_timeout_seconds}s)"
            break
        if csv_path_hint:
            p = Path(csv_path_hint)
            if p.exists():
                mt = p.stat().st_mtime
                if mt > last_mtime + 0.001:
                    last_mtime = mt
                    last_progress_at = time.time()
            # Stall check: if we've been running long enough that any
            # legitimate collector would've written at least once, AND
            # the CSV hasn't moved, kill it. We give the collector a
            # "cold start" window equal to stall_timeout before we begin
            # enforcing stall — a direct-API collector may still be
            # enumerating pubs at t=60s with no CSV yet, and that's fine.
            stalled_for = time.time() - last_progress_at
            if stalled_for > stall_timeout_seconds:
                stall_killed = True
                if csv_existed_at_start or p.exists():
                    kill_reason = (
                        f"CSV stall: {Path(csv_path_hint).name} hasn't been "
                        f"written for {int(stalled_for)}s (cap {stall_timeout_seconds}s)"
                    )
                else:
                    kill_reason = (
                        f"No CSV written at all after {int(stalled_for)}s "
                        f"(cap {stall_timeout_seconds}s)"
                    )
                break
        time.sleep(poll_interval_seconds)

    if timed_out or stall_killed:
        try:
            proc.kill()
        except Exception:
            pass
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except Exception:
            stdout, stderr = "", ""
    else:
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate(timeout=5)

    if kill_reason:
        stderr = (stderr or "") + f"\n[watchdog] {kill_reason}"
    return proc.returncode, stdout or "", stderr or "", timed_out, stall_killed


# ---------------------------------------------------------------------------
# Scan error ledger — persistent JSONL log of scan-app failures so transient
# runs can be triaged later without tailing each state file. Append-only:
# resolved entries get a tombstone line; the original record is preserved.
