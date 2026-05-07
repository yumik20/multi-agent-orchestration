#!/usr/bin/env python3
"""
Standup recorder — append ratings to ratings.jsonl, rewrite the day's
markdown digest.

Input is a JSON array (via --ratings). Each entry needs a job_id and a
1-5 rating. For runs that declared platforms=[…], the entry MUST also
include `platform` — otherwise we'd lose the per-platform granularity
the operator gave us. The recorder refuses ratings for unknown job_ids
or platform-tagged runs without a platform.

Usage:
    python3 record_ratings.py --ratings @/tmp/today_ratings.json
    python3 record_ratings.py --ratings '[{"job_id":"...","rating":4}]'
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNS_DIR = ROOT / "runs"
RATINGS_DIR = ROOT / "ratings"
RATINGS_FILE = RATINGS_DIR / "ratings.jsonl"
DAILY_DIR = RATINGS_DIR / "daily"


def _read_jsonl(path: Path):
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def _all_runs() -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not RUNS_DIR.exists():
        return out
    for month_dir in sorted(RUNS_DIR.iterdir()):
        for r in _read_jsonl(month_dir / "runs.jsonl"):
            if "job_id" in r:
                out[r["job_id"]] = r
    return out


def _existing_ratings() -> dict[tuple, dict]:
    """Keyed on (job_id, platform-or-empty)."""
    out: dict[tuple, dict] = {}
    for r in _read_jsonl(RATINGS_FILE):
        if "job_id" in r:
            out[(r["job_id"], r.get("platform", "") or "")] = r
    return out


def _append(record: dict):
    RATINGS_DIR.mkdir(parents=True, exist_ok=True)
    with RATINGS_FILE.open("a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _write_daily_report(date_str: str):
    """Rewrite the day's markdown digest from scratch from the canonical
    runs + ratings logs. Idempotent."""
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    runs = _all_runs()
    ratings = _existing_ratings()

    day_runs = [r for r in runs.values() if r.get("finished", "").startswith(date_str)]
    day_runs.sort(key=lambda r: r.get("finished", ""))

    lines = [f"# Standup ratings — {date_str}", ""]
    if not day_runs:
        lines.append("_No skill runs recorded on this date._")
    else:
        units = []
        for r in day_runs:
            ps = r.get("platforms") or []
            if ps:
                for p in ps:
                    units.append((r, p))
            else:
                units.append((r, ""))
        rated_units = [(r, p) for (r, p) in units if (r["job_id"], p) in ratings]
        rate_values = [int(ratings[(r["job_id"], p)]["rating"]) for (r, p) in rated_units]

        lines.append(f"{len(day_runs)} run(s) today, {len(units)} rateable item(s).")
        if rate_values:
            avg = sum(rate_values) / len(rate_values)
            lines.append(f"Rated: {len(rated_units)}/{len(units)} — average {avg:.1f}★")
        else:
            lines.append("Rated: 0 — nothing rated yet.")
        carry = len(units) - len(rated_units)
        if carry:
            lines.append(f"Carryover (unrated as of report time): {carry}")
        lines.append("")
        lines.append("| Skill | Platform | Trigger | MCPs | Rating | Note |")
        lines.append("|---|---|---|---|---|---|")
        for (r, p) in units:
            rt = ratings.get((r["job_id"], p), {})
            stars = (str(rt.get("rating", "—")) + "★") if rt else "—"
            note = (rt.get("note") or "").replace("|", "/")
            mcps = ", ".join(r.get("mcps_used", [])) or "—"
            platform_cell = p or "—"
            lines.append(f"| {r['skill']} | {platform_cell} | {r.get('trigger','?')} | "
                         f"{mcps} | {stars} | {note} |")

    out_path = DAILY_DIR / f"{date_str}.md"
    out_path.write_text("\n".join(lines) + "\n")
    return out_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ratings", required=True,
                        help="JSON array of {job_id, rating, note?, platform?} OR @path/to/file")
    parser.add_argument("--report-date", default="",
                        help="Date for the daily report (default: today)")
    args = parser.parse_args()

    raw = args.ratings
    if raw.startswith("@"):
        raw = Path(raw[1:]).read_text()
    payload = json.loads(raw)
    if not isinstance(payload, list):
        print("--ratings must be a JSON array", file=sys.stderr)
        return 2

    runs = _all_runs()
    existing = _existing_ratings()

    written = 0
    skipped = []
    now_iso = datetime.now().replace(microsecond=0).isoformat()

    for entry in payload:
        job_id = entry.get("job_id")
        rating = entry.get("rating")
        note = entry.get("note", "")
        platform = (entry.get("platform") or "").strip()

        if not job_id or not isinstance(rating, int) or not 1 <= rating <= 5:
            skipped.append({"reason": "invalid", "entry": entry})
            continue
        if job_id not in runs:
            skipped.append({"reason": "unknown_job_id", "job_id": job_id})
            continue

        # If the run declared platforms, the rating MUST identify which one.
        run_platforms = runs[job_id].get("platforms") or []
        if run_platforms and not platform:
            skipped.append({"reason": "missing_platform", "job_id": job_id,
                            "expected_one_of": run_platforms})
            continue
        if platform and run_platforms and platform not in run_platforms:
            skipped.append({"reason": "unknown_platform", "job_id": job_id,
                            "platform": platform, "expected_one_of": run_platforms})
            continue

        key = (job_id, platform)
        if key in existing:
            skipped.append({"reason": "already_rated", "job_id": job_id,
                            "platform": platform or None})
            continue

        record = {
            "job_id": job_id,
            "skill": runs[job_id].get("skill", ""),
            "platform": platform,
            "rating": rating,
            "note": note,
            "rated_at": now_iso,
        }
        _append(record)
        existing[key] = record
        written += 1

    date_str = args.report_date or datetime.now().strftime("%Y-%m-%d")
    report_path = _write_daily_report(date_str)

    json.dump({
        "written": written,
        "skipped": skipped,
        "daily_report": str(report_path),
    }, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
