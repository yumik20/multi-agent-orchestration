def build_execution_timeline(agents: list[dict], usage_ledger: dict, selected_month: str) -> dict:
    runs_by_bot = build_bot_runs()
    months = sorted({row.get("month", "") for row in usage_ledger.get("entries", []) if row.get("month")}, reverse=True)
    if selected_month and selected_month not in months:
        months = [selected_month, *months]
    now_local = datetime.now(LOCAL_TZ)
    today = now_local.date()
    current_by_bot: dict[str, dict] = {}
    by_month: dict[str, dict] = {month: {"bots": {}} for month in months}

    for agent in agents:
        bot = agent["name"]
        schedule_items = BOT_SCHEDULES.get(bot, [])
        bot_runs = runs_by_bot.get(bot, [])
        today_slots = schedule_slots_for_range(schedule_items, today, today)
        today_matches = match_runs_to_slots(today_slots, bot_runs)
        matched_session_ids = {item["run"]["sessionId"] for item in today_matches if item.get("run")}
        ad_hoc_today_runs = [
            run
            for run in bot_runs
            if run["date"] == today.isoformat() and run["sessionId"] not in matched_session_ids
        ]
        status, reason = classify_schedule_status(bot, schedule_items, today_matches, bot_runs, agent.get("blockers", []))
        past_due = [item for item in today_matches if item["scheduledAt"] <= now_local]
        future = [item for item in today_matches if item["scheduledAt"] > now_local]
        completed_today = sum(1 for item in past_due if item["run"] and item["run"]["result"] == "completed")
        failed_today = sum(1 for item in past_due if item["run"] and item["run"]["result"] == "error")
        missed_today = sum(1 for item in past_due if item["run"] is None)
        last_run = bot_runs[-1] if bot_runs else None
        current_by_bot[bot] = {
            "bot": bot,
            "status": status,
            "reason": reason,
            "health": health_class_for_status(status),
            "scheduleSummary": schedule_time_label(schedule_items),
            "expectedTask": future[0]["label"] if future else (past_due[-1]["label"] if past_due else "No scheduled task today"),
            "nextScheduledRun": format_local_timestamp(future[0]["scheduledAt"]) if future else "",
            "lastRunTime": last_run["endedAtLabel"] if last_run else "",
            "lastRunResult": last_run["result"] if last_run else "unknown",
            "runsToday": sum(1 for run in bot_runs if run["date"] == today.isoformat()),
            "expectedToday": len(today_slots),
            "completedToday": completed_today,
            "failedToday": failed_today,
            "missedToday": missed_today,
            "adHocRunsToday": len(ad_hoc_today_runs),
            "timelineToday": sorted([
                {
                    "label": item["label"],
                    "triggerType": "scheduled",
                    "scheduledAt": item["scheduledAtLabel"],
                    "runTime": item["run"]["startedAtLabel"] if item["run"] else "",
                    "status": "Scheduled" if item["scheduledAt"] > now_local and item["run"] is None else (
                        "Missed" if item["run"] is None else ("Failed" if item["run"]["result"] == "error" else "Completed")
                    ),
                    "actualAt": item["run"]["endedAtLabel"] if item["run"] else "",
                    "task": item["run"]["task"] if item["run"] else "",
                    "outcome": item["run"]["lastAction"] if item["run"] else "",
                    "_sort": item["scheduledAt"],
                }
                for item in today_matches
            ] + [
                {
                    "label": "Ad hoc run",
                    "triggerType": "ad_hoc",
                    "scheduledAt": run["startedAtLabel"],
                    "runTime": run["startedAtLabel"],
                    "status": "Failed" if run["result"] == "error" else "Completed",
                    "actualAt": run["endedAtLabel"],
                    "task": run["task"],
                    "outcome": run["lastAction"],
                    "_sort": run["startedAt"].astimezone(LOCAL_TZ),
                }
                for run in ad_hoc_today_runs
            ], key=lambda item: item["_sort"]),
        }
        for item in current_by_bot[bot]["timelineToday"]:
            item.pop("_sort", None)
        current_by_bot[bot]["progressState"] = classify_progress_state(
            current_by_bot[bot]["expectedToday"],
            current_by_bot[bot]["completedToday"],
            current_by_bot[bot]["failedToday"],
            current_by_bot[bot]["missedToday"],
        )
        current_by_bot[bot]["dailyIssue"] = summarize_daily_issue(
            status,
            reason,
            agent.get("blockers", []),
            current_by_bot[bot]["timelineToday"],
        )
        current_by_bot[bot]["dailySummaryText"] = (
            f"{bot}\n"
            f"- Expected: {current_by_bot[bot]['expectedToday']}\n"
            f"- Completed: {current_by_bot[bot]['completedToday']}\n"
            f"- Failed: {current_by_bot[bot]['failedToday']}\n"
            f"- Missed: {current_by_bot[bot]['missedToday']}\n"
            f"- Completion: "
            f"{round((current_by_bot[bot]['completedToday'] / current_by_bot[bot]['expectedToday']) * 100) if current_by_bot[bot]['expectedToday'] else 0}%\n"
            f"- Issue: {current_by_bot[bot]['dailyIssue']}"
        )

        for month in months:
            if not month:
                continue
            start_date, end_date = month_date_range(month)
            cutoff = now_local if month == now_local.strftime("%Y-%m") else make_schedule_dt(end_date, "23:59")
            month_slots = [item for item in schedule_slots_for_range(schedule_items, start_date, end_date) if item["scheduledAt"] <= cutoff]
            month_runs = [run for run in bot_runs if run["month"] == month]
            month_matches = match_runs_to_slots(month_slots, month_runs)
            matched_month_session_ids = {item["run"]["sessionId"] for item in month_matches if item.get("run")}
            ad_hoc_month_runs = [run for run in month_runs if run["sessionId"] not in matched_month_session_ids]
            expected = len(month_slots)
            completed = sum(1 for item in month_matches if item["run"] and item["run"]["result"] == "completed")
            failed = sum(1 for item in month_matches if item["run"] and item["run"]["result"] == "error")
            missed = sum(1 for item in month_matches if item["run"] is None)
            by_month[month]["bots"][bot] = {
                "expectedRuns": expected,
                "completedRuns": completed,
                "failedRuns": failed,
                "missedRuns": missed,
                "adHocRuns": len(ad_hoc_month_runs),
                "completionRate": round((completed / expected) * 100, 1) if expected else None,
                "lastCompletedAt": month_runs[-1]["endedAtLabel"] if month_runs else "",
            }

    return {
        "today": today.isoformat(),
        "statusDefinitions": STATUS_DEFINITIONS,
        "currentByBot": current_by_bot,
        "dailySummaryText": "\n\n".join(
            current_by_bot[bot]["dailySummaryText"] for bot in sorted(current_by_bot.keys())
        ),
        "byMonth": by_month,
    }


