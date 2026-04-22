def run_linkedin_scan_app(
    *,
    query_file: str = "",
    max_queries: int = 6,
    max_results_per_query: int = 10,
    send_email: bool = False,
    min_rows: int = 0,
) -> dict:
    run_dt = datetime.now(LOCAL_TZ)
    run_date = run_dt.strftime("%Y-%m-%d")
    matt_root = MARKETING_ROOT / "behaviorgraph" / "3_matt_intel_bot"
    skill_root = WORKSPACE_ROOT / "skills" / "matt-linkedin-scan"
    raw_path = matt_root / f"raw-linkedin-{run_date}.json"
    report_path = matt_root / f"findings-linkedin-{run_date}.md"
    csv_path = matt_root / f"linkedin-candidates-{run_date}.csv"
    qa_path = matt_root / f"linkedin-qa-log-{run_date}.csv"
    history_path = matt_root / "linkedin-seen-urls.json"
    queries_path = Path(query_file).expanduser() if query_file else skill_root / "references" / "search-queries.md"
    targets_path = skill_root / "references" / "targets.md"
    collector = skill_root / "scripts" / "collect_linkedin_activity_chrome.py"
    builder = skill_root / "scripts" / "build_linkedin_signal_report.py"

    collector_cmd = [
        "python3",
        str(collector),
        "--queries-file",
        str(queries_path),
        "--targets-file",
        str(targets_path),
        "--output",
        str(raw_path),
        "--report-md",
        str(report_path),
        "--max-queries",
        str(max_queries),
        "--max-results-per-query",
        str(max_results_per_query),
        "--scrolls",
        "1",
        "--delay",
        "1.0",
        "--verbose",
        "--chrome-profile",
        SHARED_CHROME_SCAN_PROFILE,
    ]
    started_at = datetime.now().isoformat(timespec="seconds")
    # Watch the RAW JSON path (what the collector writes incrementally),
    # not the CSV (which is built later by the separate builder subprocess).
    # Pointing the stall watchdog at a file that only the builder produces
    # would false-positive-kill every collector during its cold-start.
    collector_returncode, collector_stdout, collector_stderr, collector_timed_out, collector_stall_killed = \
        run_collector_with_stall_watchdog(
            collector_cmd,
            total_timeout_seconds=SCAN_COLLECTOR_TIMEOUT_SECONDS,
            stall_timeout_seconds=SCAN_CSV_STALL_SECONDS,
            csv_path_hint=raw_path,
        )
    state = {
        "startedAt": started_at,
        "finishedAt": datetime.now().isoformat(timespec="seconds"),
        "status": "failed" if collector_returncode else "running",
        "runDate": run_date,
        "collectorCommand": collector_cmd,
        "collectorReturncode": collector_returncode,
        "collectorTimedOut": collector_timed_out,
        "collectorStallKilled": collector_stall_killed,
        "collectorStdout": collector_stdout[:12000],
        "collectorStderr": collector_stderr[:12000],
        "rawPath": str(raw_path),
        "reportPath": str(report_path),
        "csvPath": str(csv_path),
        "qaLogPath": str(qa_path),
        "historyPath": str(history_path),
    }
    if collector_returncode != 0 and not (collector_timed_out and raw_path.exists()):
        save_linkedin_scan_state(state)
        raise RuntimeError(collector_stderr.strip() or collector_stdout.strip() or "LinkedIn collector failed.")
    if not raw_path.exists():
        state["status"] = "failed"
        save_linkedin_scan_state(state)
        raise RuntimeError("LinkedIn collector finished without writing a raw JSON file.")

    builder_cmd = [
        "python3",
        str(builder),
        "--input",
        str(raw_path),
        "--targets-file",
        str(targets_path),
        "--csv-output",
        str(csv_path),
        "--report-output",
        str(report_path),
        "--qa-log-output",
        str(qa_path),
        "--history-file",
