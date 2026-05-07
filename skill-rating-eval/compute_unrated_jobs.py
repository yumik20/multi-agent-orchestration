#!/usr/bin/env python3
"""
Standup helper — compute the set of skill runs that the operator hasn't
rated yet, including carryovers from previous days.

Reads runs.jsonl + ratings.jsonl. For runs that declare `platforms=[…]`,
fans out into one entry per platform (a bundled scan with 4 platforms
shows up as 4 rateable items — one per platform). Carryover rule:
items stay unrated until the operator rates them. There is no time-out.

Usage:
    python3 compute_unrated_jobs.py            # JSON list (default)
    python3 compute_unrated_jobs.py --pretty   # human-readable
    python3 compute_unrated_jobs.py --since 2026-04-29
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNS_DIR = ROOT / "runs"
RATINGS_FILE = ROOT / "ratings" / "ratings.jsonl"


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


def _all_runs():
    if not RUNS_DIR.exists():
        return
    for month_dir in sorted(RUNS_DIR.iterdir()):
        yield from _read_jsonl(month_dir / "runs.jsonl")


def _rated_keys() -> set[tuple]:
    """Set of (job_id, platform-or-empty) tuples that are already rated."""
    out = set()
    for r in _read_jsonl(RATINGS_FILE):
        if "job_id" in r:
            out.add((r["job_id"], r.get("platform", "") or ""))
    return out


def _summarize(run: dict) -> str:
    bits = []
    if run.get("row_count") is not None:
        bits.append(f"{run['row_count']} rows")
    if run.get("artifacts"):
        bits.append(f"{len(run['artifacts'])} files")
    bits.append(f"{run.get('duration_s', 0):.0f}s")
    if run.get("status") and run["status"] != "success":
        bits.append(run["status"])
    return ", ".join(bits)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", default="",
                        help="ISO date YYYY-MM-DD; carryovers older than this are dropped")
    parser.add_argument("--pretty", action="store_true",
                        help="human-readable text instead of JSON")
    args = parser.parse_args()

    since_dt = datetime.fromisoformat(args.since) if args.since else None
    rated = _rated_keys()

    # Each unrated entry is one rateable unit: either a whole-job rating
    # (platform="") or a per-platform rating for runs that declared platforms.
    unrated: list[tuple[dict, str]] = []
    for run in _all_runs():
        if since_dt:
            try:
                finished_dt = datetime.fromisoformat(run.get("finished", ""))
            except ValueError:
                continue
            if finished_dt < since_dt:
                continue
        platforms = run.get("platforms") or []
        if platforms:
            for p in platforms:
                if (run["job_id"], p) not in rated:
                    unrated.append((run, p))
        else:
            if (run["job_id"], "") not in rated:
                unrated.append((run, ""))

    unrated.sort(key=lambda pair: (pair[0].get("finished", ""), pair[1]))

    if args.pretty:
        if not unrated:
            print("No unrated jobs. All caught up.")
            return 0
        print(f"{len(unrated)} unrated rating(s):")
        for i, (run, platform) in enumerate(unrated, 1):
            tag = f" [{platform}]" if platform else ""
            print(f"  {i}. {run['skill']}{tag}  ({run.get('trigger', '?')})  "
                  f"finished {run.get('finished','?')}  — {_summarize(run)}")
        return 0

    out = [
        {
            "index": i,
            "job_id": run["job_id"],
            "skill": run["skill"],
            "platform": platform,
            "mcps_used": run.get("mcps_used", []),
            "trigger": run.get("trigger", ""),
            "finished": run.get("finished", ""),
            "summary": _summarize(run),
            "status": run.get("status", ""),
        }
        for i, (run, platform) in enumerate(unrated, 1)
    ]
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
