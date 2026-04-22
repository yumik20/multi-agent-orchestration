def _collect_sns_rows_for_qa() -> list[dict]:
    """Load rows from each platform's final CSV (written by that scan's
    builder/finalizer) into a unified shape for the QA pass and email."""
    scan_specs = [
        ("linkedin", LINKEDIN_SCAN_STATE_PATH, parse_linkedin_scan_state),
        ("x",        X_SCAN_STATE_PATH,        parse_x_scan_state),
        ("substack", SUBSTACK_SCAN_STATE_PATH, parse_substack_scan_state),
        ("hn-reddit", HN_REDDIT_SCAN_STATE_PATH, parse_hn_reddit_scan_state),
    ]
    unified: list[dict] = []
    for source, _, parser in scan_specs:
        state = parser() or {}
        csv_path = state.get("csvPath") or ""
        if not csv_path or not Path(csv_path).exists():
            continue
        try:
            with Path(csv_path).open("r", encoding="utf-8", newline="") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    # Normalize across schemas:
                    # LinkedIn / X / HN-Reddit use `post_url`, `post_summary`.
                    # Substack uses `article_url`, `title`, `summary`.
                    url = (row.get("post_url") or row.get("article_url") or "").strip()
                    if not url:
                        continue
                    title_or_summary = (
                        row.get("post_summary")
                        or row.get("title")
                        or row.get("summary")
                        or ""
                    ).strip()
                    person = (row.get("person") or row.get("author") or "").strip()
                    context_bits = [
                        row.get("newsletter", ""),
                        row.get("who_they_are", ""),
                        row.get("summary", ""),
                    ]
                    context = " · ".join(b for b in context_bits if b).strip()
                    unified.append({
                        "source": source,
                        "url": url,
                        "person": person,
                        "text": title_or_summary,
                        "context": context[:400],
                        "raw": dict(row),
                    })
        except Exception as exc:
            sys.stderr.write(f"  sns QA: failed to read {csv_path}: {exc}\n")
    return unified


def _qualify_rows_with_gemini(rows: list[dict]) -> list[dict]:
    """Call Gemini Flash once with the full batch. Returns rows with two
    new keys: `qualified` (bool) and `qualification_reason` (short text).
    On API failure, falls back to keyword-match qualification so the pipeline
    never blocks on LLM unavailability."""
    if not rows:
        return []
    api_key = _load_gemini_api_key()
    if not api_key:
        sys.stderr.write("  sns QA: GEMINI_API_KEY missing — using deterministic fallback\n")
        return _fallback_qualify(rows)

    numbered = [
        f"[{i}] {{source:{r['source']}, person:{r['person']}, text:{r['text'][:240]}, ctx:{r['context'][:120]}}}"
        for i, r in enumerate(rows)
    ]
    prompt = (
        "You decide whether each post is relevant to BehaviorGraph's themes:\n"
        f"{SNS_BEHAVIORGRAPH_THEMES}\n\n"
        "Be loose — include anything that genuinely touches these themes, "
        "even tangentially. Exclude only clearly off-topic or pure hype with no substance.\n\n"
        "Return ONLY a compact JSON array, one object per input index, "
        'in the form: [{"i":0,"q":true,"r":"why"}, ...]. '
        '"q" is boolean qualified, "r" is one short reason (≤12 words).\n\n'
        "Posts:\n" + "\n".join(numbered)
    )

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{SNS_GEMINI_MODEL}:generateContent?key={api_key}"
    )
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        # maxOutputTokens high enough for ~60 rows with reason strings.
        # thinkingBudget=0 disables reasoning tokens on gemini-2.5-flash so
        # we don't silently spend the budget on invisible "thinking" output
        # and truncate the actual JSON answer.
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 16000,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }).encode("utf-8")
    try:
        req = Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        # Strip markdown fences if model wrapped them
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
        verdicts = json.loads(text)
    except Exception as exc:
        sys.stderr.write(f"  sns QA: Gemini call failed ({exc}) — falling back\n")
        return _fallback_qualify(rows)

    by_i = {int(v.get("i", -1)): v for v in verdicts if isinstance(v, dict)}
    enriched: list[dict] = []
    for i, row in enumerate(rows):
        verdict = by_i.get(i, {"q": False, "r": "no verdict returned"})
        row = dict(row)
        row["qualified"] = bool(verdict.get("q"))
        row["qualification_reason"] = str(verdict.get("r", ""))[:180]
        enriched.append(row)
    return enriched


def _fallback_qualify(rows: list[dict]) -> list[dict]:
    keywords = ("agent", "enterprise", "governance", "context", "llm", "rag",
                "orchestrat", "knowledge", "routing", "trust", "autonomy",
                "deploy", "workflow")
    out: list[dict] = []
    for row in rows:
        lowered = (row.get("text", "") + " " + row.get("context", "")).lower()
        hit = any(k in lowered for k in keywords)
        r = dict(row)
        r["qualified"] = hit
        r["qualification_reason"] = "keyword match (deterministic fallback)" if hit else "no theme keyword match"
        out.append(r)
    return out


def _write_qa_csv(path: Path, rows: list[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["source", "url", "person", "post_summary", "qualification_reason"])
        for row in rows:
            writer.writerow([
                row.get("source", ""),
                row.get("url", ""),
                row.get("person", ""),
                row.get("text", ""),
                row.get("qualification_reason", ""),
            ])
            count += 1
    return count


def _build_sns_email_body(summary: dict) -> str:
    total = summary["qualifiedCount"] + summary["unqualifiedCount"]
    lines = [
        f"SNS scan wave — {summary['runDate']}",
        "",
        f"Total rows across 4 platforms: {total}",
        f"  • Qualified: {summary['qualifiedCount']}",
        f"  • Unqualified: {summary['unqualifiedCount']}",
        "",
        "Per-platform breakdown:",
    ]
    for source, counts in summary["perSource"].items():
        lines.append(f"  • {source}: {counts['qualified']}q / {counts['unqualified']}uq (total {counts['total']})")
    lines += [
        "",
        "Qualification: Gemini 2.0 Flash, loose relevance to BehaviorGraph themes",
        "(enterprise AI agents, governance, org context, agent orchestration).",
        "",
        "Two CSVs attached: qualified.csv + unqualified.csv.",
        "",
        "— SNS scan pipeline (local)",
    ]
    return "\n".join(lines)


def _send_sns_email_via_mail_app(subject: str, body: str, qualified_path: Path,
                                 unqualified_path: Path) -> None:
    """AppleScript → Mail.app. Uses Mail's default account as sender (iCloud
    on this machine). Single recipient. Same pattern as the existing
    LinkedIn/X mailers, just unified for the whole wave."""
    body_esc = body.replace("\\", "\\\\").replace('"', '\\"')
    subj_esc = subject.replace("\\", "\\\\").replace('"', '\\"')
    q_esc = str(qualified_path).replace("\\", "\\\\").replace('"', '\\"')
    u_esc = str(unqualified_path).replace("\\", "\\\\").replace('"', '\\"')
    script = f'''tell application "Mail"
  set m to make new outgoing message with properties {{subject:"{subj_esc}", content:"{body_esc}", visible:false}}
  tell m
    make new to recipient with properties {{address:"{SNS_EMAIL_RECIPIENT}"}}
    make new attachment with properties {{file name:(POSIX file "{q_esc}")}}
    make new attachment with properties {{file name:(POSIX file "{u_esc}")}}
  end tell
  send m
end tell
return "sent"'''
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or "").strip() or "Mail.app send failed")


def run_sns_qa_and_email() -> dict:
    """Unified QA + email step. Called after all 4 sub-scans reach terminal
    state. Returns a summary dict; never raises so the wave always closes."""
    run_dt = datetime.now(LOCAL_TZ)
    run_date = run_dt.strftime("%Y-%m-%d")
    matt_root = MARKETING_ROOT / "behaviorgraph" / "3_matt_intel_bot"
    qualified_path = matt_root / f"sns-qualified-{run_date}.csv"
    unqualified_path = matt_root / f"sns-unqualified-{run_date}.csv"
