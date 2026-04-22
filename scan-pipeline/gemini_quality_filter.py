def quality_filter_events(events_by_date: dict, date_range_label: str, api_key: str) -> tuple[dict, list]:
    """
    Use Gemini 2.5 Flash to filter events. Drops ones that are NOT:
    - AI / enterprise tech focused
    - Sponsored by venture-backed or well-known companies
    Returns (filtered_events_by_date, rejected_events) where each rejected has reason.
    """
    if not api_key:
        return events_by_date, []

    # Build the compact event list for Gemini
    flat_events = []
    for day, evts in events_by_date.items():
        for e in evts:
            flat_events.append({
                "day": day,
                "name": e["name"],
                "desc": (e.get("description") or "")[:300],
                "url": e.get("url", ""),
            })
    if not flat_events:
        return events_by_date, []

    # Number events so Gemini can refer to them by ID
    event_lines = "\n".join(
        f"[{i}] {ev['name']} ({ev['day']}) — {ev['desc']}"
        for i, ev in enumerate(flat_events)
    )

    prompt = (
        f"You are a quality filter for a curated list of NYC tech events ({date_range_label}). "
        f"Evaluate each event and decide KEEP or REJECT.\n\n"
        f"KEEP only if the event matches AT LEAST ONE of:\n"
        f"1. Clearly about AI, agentic AI, enterprise AI, or ML\n"
        f"2. Clearly about enterprise software, infrastructure, dev tools, cloud, or SaaS\n"
        f"3. Hosted or sponsored by a venture-backed or well-known company "
        f"(e.g., OpenAI, Anthropic, Stripe, Notion, Nvidia, Databricks, Snowflake, Google, "
        f"Microsoft, Amazon, Meta, AWS, Salesforce, Cloudflare, Vercel, a16z, Sequoia, YC, Founders Fund, etc.)\n\n"
        f"REJECT if the event is:\n"
        f"- Generic networking with no clear tech or enterprise focus\n"
        f"- Crypto/web3 only (unless the host is well-known)\n"
        f"- Wellness, creator economy, or influencer-only\n"
        f"- Hobbyist/non-professional unless host is notable\n\n"
        f"Events to evaluate:\n{event_lines}\n\n"
        f"Respond with ONLY a JSON object in this exact format (no prose, no markdown fences):\n"
        f'{{"decisions": [{{"id": 0, "keep": true, "reason": "AI focus"}}, {{"id": 1, "keep": false, "reason": "generic networking"}}]}}'
    )

    try:
        response = _call_gemini(prompt, api_key, use_search=False, timeout=90)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        return events_by_date, [{"error": f"Gemini filter failed: {exc}"}]

    # Parse response
    try:
        # Strip markdown fences if present
        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```", 2)[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0].strip()
        parsed = json.loads(cleaned)
        decisions = parsed.get("decisions", [])
    except json.JSONDecodeError:
        return events_by_date, [{"error": f"Gemini returned invalid JSON: {response[:300]}"}]

    keep_ids = {d["id"] for d in decisions if d.get("keep")}
    rejected = []
    for d in decisions:
        if not d.get("keep") and 0 <= d.get("id", -1) < len(flat_events):
            ev = flat_events[d["id"]]
            rejected.append({"name": ev["name"], "day": ev["day"], "reason": d.get("reason", "no reason given")})

    # Rebuild events_by_date with only kept events
    filtered: dict = {}
    idx = 0
    for day, evts in events_by_date.items():
        for e in evts:
            if idx in keep_ids:
                filtered.setdefault(day, []).append(e)
            idx += 1
    return filtered, rejected


