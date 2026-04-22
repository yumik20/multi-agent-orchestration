def schedule_duration_minutes(bot: str, label: str) -> int:
    lowered = f"{bot} {label}".lower()
    if "workspace cleanup" in lowered:
        return 120
    if "strategy review" in lowered:
        return 90
    if "standup" in lowered or "check-up" in lowered:
        return 30
    if "qa gate" in lowered:
        return 45
    if "publish" in lowered:
        return 60
    if "x post" in lowered:
        return 45
    if "intel" in lowered or "scan" in lowered:
        return 75
    if "scout" in lowered or "discussions" in lowered:
        return 90
    return 60


def assign_overlap_lanes(events: list[dict]) -> list[dict]:
    sorted_events = sorted(events, key=lambda item: (item["startMin"], item["endMin"], item["bot"]))
    groups: list[list[dict]] = []
    current_group: list[dict] = []
    current_group_end = -1

    for event in sorted_events:
        if not current_group or event["startMin"] < current_group_end:
            current_group.append(event)
            current_group_end = max(current_group_end, event["endMin"])
        else:
            groups.append(current_group)
            current_group = [event]
            current_group_end = event["endMin"]
    if current_group:
        groups.append(current_group)

    for group in groups:
        active: list[tuple[int, int]] = []
        max_lane = 0
        for event in group:
            active = [(lane, end_min) for lane, end_min in active if end_min > event["startMin"]]
            used_lanes = {lane for lane, _ in active}
            lane_index = 0
            while lane_index in used_lanes:
                lane_index += 1
            event["laneIndex"] = lane_index
            active.append((lane_index, event["endMin"]))
            max_lane = max(max_lane, lane_index)
        lane_count = max_lane + 1
        for event in group:
            event["laneCount"] = lane_count
    return events


def build_weekly_schedule_view(agents: list[dict]) -> dict:
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    planner = {day: [] for day in day_names}
    calendar_events = {day: [] for day in day_names}
    rows = []
    now_local = datetime.now(LOCAL_TZ)
    today_index = now_local.weekday()
    current_time_min = now_local.hour * 60 + now_local.minute
    all_start_mins: list[int] = []
    all_end_mins: list[int] = []
    for agent in agents:
        bot = agent["name"]
        schedule_items = BOT_SCHEDULES.get(bot, [])
        capability = BOT_CAPABILITIES.get(bot, {})
        by_day: dict[int, list[str]] = {}
        for item in schedule_items:
            start_hour, start_minute = [int(part) for part in item["time"].split(":", 1)]
            start_min = start_hour * 60 + start_minute
            duration_min = int(item.get("durationMin", schedule_duration_minutes(bot, item["label"])))
            end_min = start_min + duration_min
            for day in item.get("days", []):
                by_day.setdefault(day, []).append(f"{item['time']} {item['label']}")
                planner[day_names[day]].append(
                    {
                        "bot": bot,
                        "team": agent["room"],
                        "task": item["label"],
                        "time": item["time"],
                        "managerType": capability.get("managerType", "worker"),
                    }
                )
                calendar_events[day_names[day]].append(
                    {
                        "bot": bot,
                        "team": agent["room"],
                        "task": item["label"],
                        "time": item["time"],
                        "startMin": start_min,
                        "endMin": end_min,
                        "durationMin": duration_min,
                        "managerType": capability.get("managerType", "worker"),
                        "isToday": day == today_index,
                        "isActiveNow": day == today_index and start_min <= current_time_min < end_min,
                    }
                )
                all_start_mins.append(start_min)
                all_end_mins.append(end_min)
        planned_days = ", ".join(day_names[day] for day in sorted(by_day.keys())) if by_day else "None"
        planned_slots = " | ".join(
            f"{day_names[day]}: " + ", ".join(sorted(by_day[day]))
            for day in sorted(by_day.keys())
        ) if by_day else "No scheduled slots"
        expected_frequency = f"{len(schedule_items)} slot{'s' if len(schedule_items) != 1 else ''} pattern"
        rows.append(
            {
                "bot": bot,
                "team": agent["room"],
                "plannedDays": planned_days,
                "plannedSlots": planned_slots,
                "plannedTasks": ", ".join(item["label"] for item in schedule_items) if schedule_items else "No scheduled task",
                "expectedFrequency": expected_frequency,
                "currentWeekStatus": agent.get("operationalStatus", "Unknown"),
                "managerType": capability.get("managerType", "worker"),
            }
        )
    for day in planner:
        planner[day].sort(key=lambda item: (item["time"], item["team"], item["bot"]))
    for day in calendar_events:
        assign_overlap_lanes(calendar_events[day])
        calendar_events[day].sort(key=lambda item: (item["startMin"], item["laneIndex"], item["bot"]))
    meta7_summary = [
        item for item in rows
        if item["bot"] == "Meta7"
    ]
    worker_rows = [row for row in rows if row["managerType"] != "manager"]
    day_start_min = max(0, ((min(all_start_mins) // 60) - 1) * 60) if all_start_mins else 8 * 60
    day_end_min = min(24 * 60, ((max(all_end_mins) + 59) // 60 + 1) * 60) if all_end_mins else 21 * 60
    return {
        "rows": rows,
        "workerRows": worker_rows,
        "days": day_names,
        "todayIndex": today_index,
        "todayLabel": day_names[today_index],
        "planner": planner,
        "calendar": calendar_events,
        "dayStartMin": day_start_min,
        "dayEndMin": day_end_min,
        "currentTimeMin": current_time_min,
        "meta7Summary": meta7_summary[0] if meta7_summary else None,
    }


def build_org_chart_view(agents: list[dict]) -> dict:
    by_manager: dict[str, list[dict]] = {}
