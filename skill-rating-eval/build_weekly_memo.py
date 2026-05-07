#!/usr/bin/env python3
"""
Sunday weekly memo — joins 7 days of runs.jsonl + ratings.jsonl,
computes per-(skill, platform) stats, surfaces buckets below 3.0★,
writes a markdown memo + CSV, and emails them via Mail.app AppleScript.

Aggregating by `(skill, platform)` instead of just `skill` matters when
a skill bundles multiple sources in one run. It lets the operator see
"the morning scan is great on source-a but the source-c targets are
stale" instead of one averaged number that hides the per-source signal.
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

SHARED_ROOT = Path(__file__).resolve().parent
RUNS_DIR = SHARED_ROOT / "runs"
RATINGS_FILE = SHARED_ROOT / "ratings" / "ratings.jsonl"
OUT_DIR = SHARED_ROOT / "reports"

RECIPIENT_TO = "<RECIPIENT_EMAIL>"   # set by env / project config
RECIPIENT_CC = ""


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


def _all_runs(since_dt: datetime, until_dt: datetime):
    if not RUNS_DIR.exists():
        return
    for month_dir in sorted(RUNS_DIR.iterdir()):
        for r in _read_jsonl(month_dir / "runs.jsonl"):
            try:
                finished = datetime.fromisoformat(r.get("finished", ""))
            except ValueError:
                continue
            if since_dt <= finished <= until_dt:
                yield r


def _load_ratings() -> dict[tuple, dict]:
    """Keyed on (job_id, platform-or-empty)."""
    out: dict[tuple, dict] = {}
    for r in _read_jsonl(RATINGS_FILE):
        if "job_id" in r:
            out[(r["job_id"], r.get("platform", "") or "")] = r
    return out


def aggregate(runs: list[dict], ratings: dict[tuple, dict]) -> list[dict]:
    """Group by (skill, platform). A run with N platforms produces N
    (skill, platform) buckets — so a 4-source scan shows up as 4 rows
    in the memo, one per source."""
    by_key: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in runs:
        skill = r.get("skill", "unknown")
        platforms = r.get("platforms") or [""]
        for p in platforms:
            by_key[(skill, p)].append(r)

    out = []
    for (skill, platform), items in by_key.items():
        rt_list = [ratings[(r["job_id"], platform)]
                   for r in items if (r["job_id"], platform) in ratings]
        rate_values = [int(rt["rating"]) for rt in rt_list]
        success_count = sum(1 for r in items if r.get("status") == "success")
        mcps = sorted({m for r in items for m in r.get("mcps_used", [])})
        durations = [r.get("duration_s", 0) for r in items if r.get("duration_s")]
        notes = [rt.get("note") for rt in rt_list if rt.get("note")]
        models = sorted({r.get("extra", {}).get("model_actual", "")
                         for r in items
                         if r.get("extra", {}).get("model_actual")})

        out.append({
            "skill": skill,
            "platform": platform,
            "runs": len(items),
            "success_rate": (success_count / len(items)) if items else 0.0,
            "rated": len(rate_values),
            "avg_rating": (statistics.mean(rate_values) if rate_values else None),
            "min_rating": min(rate_values) if rate_values else None,
            "max_rating": max(rate_values) if rate_values else None,
            "mcps_used": mcps,
            "models_actual": models,
            "avg_duration_s": (statistics.mean(durations) if durations else 0),
            "sample_notes": notes[:5],
        })

    # Sort: lowest avg-rating first (weakest surfaces), unrated at bottom.
    out.sort(key=lambda s: (s["avg_rating"] is None, s["avg_rating"] or 0, -s["runs"]))
    return out


def _label(s: dict) -> str:
    return f"{s['skill']} [{s['platform']}]" if s.get("platform") else s["skill"]


def render_memo(stats: list[dict], runs: list[dict],
                ratings: dict[tuple, dict],
                since_dt: datetime, until_dt: datetime) -> str:
    lines = [f"# Weekly skill review — {since_dt.date()} → {until_dt.date()}\n"]
    if not runs:
        lines.append("_No runs recorded in this window._")
        return "\n".join(lines)

    total_units = 0
    rated_count = 0
    rate_values = []
    for r in runs:
        ps = r.get("platforms") or [""]
        for p in ps:
            total_units += 1
            if (r["job_id"], p) in ratings:
                rated_count += 1
                rate_values.append(int(ratings[(r["job_id"], p)]["rating"]))
    avg_global = statistics.mean(rate_values) if rate_values else None

    lines.append("## Headline numbers")
    lines.append(f"- Runs: **{len(runs)}** across {len(stats)} skill/platform buckets")
    lines.append(f"- Rated: **{rated_count}/{total_units}** rateable items"
                 + (f" — average **{avg_global:.1f}★**" if avg_global is not None else ""))
    lines.append(f"- Unrated carryover: **{total_units - rated_count}**\n")

    weak = [s for s in stats if s["avg_rating"] is not None and s["avg_rating"] < 3.0]
    if weak:
        lines.append("## Buckets below 3.0★\n")
        for s in weak:
            lines.append(f"### {_label(s)} — **{s['avg_rating']:.1f}★** "
                         f"({s['rated']} ratings, {s['runs']} runs)")
            lines.append(f"- Success rate: {s['success_rate']:.0%}")
            lines.append(f"- MCPs: {', '.join(s['mcps_used']) or '—'}")
            if s["models_actual"]:
                lines.append(f"- Models actually run: {', '.join(s['models_actual'])}")
            if s["sample_notes"]:
                lines.append("- Notes:")
                for n in s["sample_notes"]:
                    lines.append(f'  - "{n}"')
            lines.append("")

    lines.append("## All skill/platform buckets\n")
    lines.append("| Skill | Platform | Runs | Success | Rated | Avg★ | Models actual |")
    lines.append("|---|---|---|---|---|---|---|")
    for s in stats:
        avg = f"{s['avg_rating']:.1f}" if s["avg_rating"] is not None else "—"
        platform_cell = s["platform"] or "—"
        models_cell = ", ".join(s["models_actual"]) or "—"
        lines.append(f"| {s['skill']} | {platform_cell} | {s['runs']} | "
                     f"{s['success_rate']:.0%} | {s['rated']}/{s['runs']} | "
                     f"{avg} | {models_cell} |")

    lines.append("\n_Full per-run data is attached as CSV._\n")
    return "\n".join(lines)


def write_csv(runs: list[dict], ratings: dict[tuple, dict], out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["job_id", "skill", "platform", "trigger", "mcps_used", "started",
            "finished", "duration_s", "row_count", "status", "error",
            "model_actual", "rating", "note"]
    with out_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in runs:
            platforms = r.get("platforms") or [""]
            for p in platforms:
                rt = ratings.get((r["job_id"], p), {})
                w.writerow({
                    "job_id": r["job_id"],
                    "skill": r.get("skill", ""),
                    "platform": p,
                    "trigger": r.get("trigger", ""),
                    "mcps_used": ",".join(r.get("mcps_used", [])),
                    "started": r.get("started", ""),
                    "finished": r.get("finished", ""),
                    "duration_s": r.get("duration_s", ""),
                    "row_count": r.get("row_count", ""),
                    "status": r.get("status", ""),
                    "error": r.get("error") or "",
                    "model_actual": r.get("extra", {}).get("model_actual", ""),
                    "rating": rt.get("rating", ""),
                    "note": rt.get("note", ""),
                })


def applescript_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def send_email(subject: str, body: str, csv_path: Path) -> bool:
    if not RECIPIENT_TO or RECIPIENT_TO.startswith("<"):
        sys.stderr.write("send_email: RECIPIENT_TO not configured — skipping\n")
        return False
    cc_block = (f'        make new cc recipient with properties '
                f'{{address:{applescript_str(RECIPIENT_CC)}}}\n') if RECIPIENT_CC else ""
    script = f"""
tell application "Mail"
    set newMsg to make new outgoing message with properties {{subject:{applescript_str(subject)}, content:{applescript_str(body)}, visible:false}}
    tell newMsg
        make new to recipient with properties {{address:{applescript_str(RECIPIENT_TO)}}}
{cc_block}        tell content
            make new attachment with properties {{file name:(POSIX file {applescript_str(str(csv_path))})}} at after last paragraph
        end tell
    end tell
    send newMsg
end tell
"""
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(f"AppleScript error: {r.stderr}\n")
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--no-send", action="store_true")
    parser.add_argument("--end", default="",
                        help="ISO datetime end of window (default: now)")
    args = parser.parse_args()

    until_dt = datetime.fromisoformat(args.end) if args.end else datetime.now()
    since_dt = until_dt - timedelta(days=args.days)

    runs = list(_all_runs(since_dt, until_dt))
    ratings = _load_ratings()
    stats = aggregate(runs, ratings)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = until_dt.strftime("%Y-%m-%d")
    memo_path = OUT_DIR / f"weekly-{stamp}.md"
    csv_path = OUT_DIR / f"weekly-{stamp}.csv"

    memo = render_memo(stats, runs, ratings, since_dt, until_dt)
    memo_path.write_text(memo)
    write_csv(runs, ratings, csv_path)

    rated_units = sum(
        1 for r in runs for p in (r.get("platforms") or [""])
        if (r["job_id"], p) in ratings
    )
    total_units = sum(len(r.get("platforms") or [""]) for r in runs)
    print(json.dumps({
        "memo": str(memo_path),
        "csv": str(csv_path),
        "runs": len(runs),
        "buckets": len(stats),
        "rated_units": rated_units,
        "total_units": total_units,
    }, indent=2))

    if args.no_send:
        return 0
    if not runs:
        print("No runs in window — skipping email.", file=sys.stderr)
        return 0
    subject = f"[weekly] Skill review — {since_dt.date()} → {until_dt.date()}"
    if send_email(subject, memo, csv_path):
        print("Email sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
