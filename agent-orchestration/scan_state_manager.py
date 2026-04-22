def _scan_state_is_in_flight(state: dict) -> bool:
    return str(state.get("status", "")).lower() in ("running", "queued", "in_progress", "pending")


def expire_stuck_scan_state(state: dict, saver, *, app_slug: str,
                            max_runtime_seconds: int) -> dict:
    """If state is still flagged as running past its max runtime, mark it
    failed and persist. Returns the (possibly updated) state dict. Safe to
    call with any state — returns unchanged if not expired.

    Yumi's universal 30-min ceiling: regardless of what max_runtime_seconds
    the caller passes, any scan older than SCAN_HARD_CEILING_SECONDS +
    grace is force-expired. This is the belt-and-suspenders layer behind
    the subprocess timeout.
    """
    if not state or not _scan_state_is_in_flight(state):
        return state
    now = time.time()
    queued_epoch = _parse_iso_to_epoch(state.get("queuedAt", ""))
    started_epoch = _parse_iso_to_epoch(state.get("startedAt", ""))
    reference = started_epoch or queued_epoch
    if reference <= 0:
        # No timestamps at all — can't tell if stuck; leave alone.
        return state
    effective_cap = min(max_runtime_seconds, SCAN_HARD_CEILING_SECONDS)
    deadline = reference + effective_cap + _SCAN_EXPIRATION_GRACE_SECONDS
    if now < deadline:
        return state
    # Expired. Build a failure state.
    elapsed = int(now - reference)
    reason = (
        f"Scan timed out: worker was still flagged running {elapsed}s after "
        f"queue time (cap {max_runtime_seconds}s + {_SCAN_EXPIRATION_GRACE_SECONDS}s grace). "
        "Likely the server process was killed mid-run. Auto-marking failed."
    )
    updated = dict(state)
    updated["status"] = "failed"
    updated["endedReason"] = "expired"
    updated["error"] = reason
    updated["issues"] = list(state.get("issues") or []) + [reason]
    updated["completedAt"] = datetime.now().isoformat(timespec="seconds")
    updated["finishedAt"] = updated["completedAt"]
    try:
        saver(updated)
    except Exception as exc:
        sys.stderr.write(f"expire_stuck_scan_state: saver failed for {app_slug}: {exc}\n")
    try:
        notify_scan_result(app_slug, status="failed", error=reason)
    except Exception as exc:
        sys.stderr.write(f"expire_stuck_scan_state: notify_manager failed for {app_slug}: {exc}\n")
    return updated


def read_scan_state_with_expiration(parser, saver, *, app_slug: str,
                                    max_runtime_seconds: int) -> dict:
    """Read a scan state, auto-expiring it if stuck. Use from GET handlers
    and from start_*_scan_job guards so stale `running` never blocks a
    fresh dispatch."""
    return expire_stuck_scan_state(
        parser() or {},
        saver,
        app_slug=app_slug,
        max_runtime_seconds=max_runtime_seconds,
    )

