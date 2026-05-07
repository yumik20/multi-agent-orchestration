#!/usr/bin/env python3
"""
MCP Scan Pipeline Server — stdio transport.

Exposes seven tools shared across scanner skills:
    run_scan, qualify, smart_dedup, weekly_report,
    cleanup, scan_status, send_email

Calls per-source scan scripts as subprocesses; manages run state and
30-day URL dedup in SQLite.

This file is a sanitized excerpt — concrete platform names are replaced
with `source-a` / `source-b` / etc. Each entry in SCRIPTS maps to a
real collector script in production.
"""

# MCP stdio: do NOT reopen sys.stdout — Node child_process pipe breaks.
# Unbuffered mode is set via the -u flag in the runtime config.
import sys

import concurrent.futures
import csv
import json
import random
import sqlite3
import subprocess
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

# ─── Paths ───────────────────────────────────────────────────────────────────
WORKSPACE = Path.home() / "workspace"
SKILLS = WORKSPACE / "skills"
DATA_OUT = WORKSPACE / "scan-output"
DB_PATH = Path(__file__).parent / "state.db"
SHARED_DIR = SKILLS / "_shared"

# Per-source collector scripts (sanitized — real paths are project-specific).
SCRIPTS = {
    "source-a": SKILLS / "scan-source-a" / "scripts" / "collect.py",
    "source-b": SKILLS / "scan-source-b" / "scripts" / "collect.py",
    "source-c": SKILLS / "scan-source-c" / "scripts" / "collect.py",
    "source-d": SKILLS / "scan-source-d" / "scripts" / "collect.py",
}

QUALIFIER_MODEL = "claude-haiku-4-5-20251001"
STAGGER_SEC = (10, 20)
SCAN_TIMEOUT_SEC = 1200

# Per-source success thresholds. Below this = partial; above = success.
MIN_ROWS = {
    "source-a": 8,
    "source-b": 8,
    "source-c": 5,
    "source-d": 8,
}

DEDUP_WINDOW_DAYS = 30
RETENTION_DAYS = 31


# ─── SQLite state ────────────────────────────────────────────────────────────
def init_db():
    db = sqlite3.connect(str(DB_PATH), isolation_level=None, check_same_thread=False)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY,
            platform TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            started_at TEXT,
            finished_at TEXT,
            item_count INTEGER DEFAULT 0,
            csv_path TEXT,
            error TEXT,
            run_group TEXT
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS seen_urls (
            url TEXT PRIMARY KEY,
            platform TEXT NOT NULL,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            qualified INTEGER DEFAULT 0
        )
    """)
    return db


def record_start(db, run_id, platform, run_group):
    db.execute(
        "INSERT INTO runs (id, platform, status, started_at, run_group) VALUES (?, ?, 'running', ?, ?)",
        (run_id, platform, datetime.now().isoformat(timespec="seconds"), run_group),
    )


def record_finish(db, run_id, status, item_count=0, csv_path="", error=""):
    db.execute(
        "UPDATE runs SET status=?, finished_at=?, item_count=?, csv_path=?, error=? WHERE id=?",
        (status, datetime.now().isoformat(timespec="seconds"), item_count, csv_path, error, run_id),
    )


# ─── URL dedup (30-day rolling window) ──────────────────────────────────────
def is_url_seen(db, url: str) -> bool:
    row = db.execute(
        "SELECT 1 FROM seen_urls WHERE url = ? AND last_seen > date('now', ?)",
        (url, f"-{DEDUP_WINDOW_DAYS} days"),
    ).fetchone()
    return row is not None


def mark_url_seen(db, url: str, platform: str, qualified: bool = False):
    now = datetime.now().isoformat(timespec="seconds")
    db.execute("""
        INSERT INTO seen_urls (url, platform, first_seen, last_seen, qualified)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(url) DO UPDATE SET last_seen=?, qualified=?
    """, (url, platform, now, now, int(qualified), now, int(qualified)))


def cleanup_old_urls(db):
    db.execute("DELETE FROM seen_urls WHERE last_seen < date('now', ?)",
               (f"-{DEDUP_WINDOW_DAYS} days",))


def get_dedup_stats(db) -> dict:
    total = db.execute("SELECT COUNT(*) FROM seen_urls").fetchone()[0]
    by_platform = dict(db.execute("SELECT platform, COUNT(*) FROM seen_urls GROUP BY platform"))
    recent = db.execute(
        "SELECT COUNT(*) FROM seen_urls WHERE last_seen > date('now', '-7 days')"
    ).fetchone()[0]
    return {"total_urls": total, "by_platform": by_platform,
            "last_7_days": recent, "window_days": DEDUP_WINDOW_DAYS}


# ─── Scan execution ─────────────────────────────────────────────────────────
def run_platform_scan(platform: str, db, run_group: str) -> dict:
    """Run a single source's collector. Returns a status dict."""
    run_id = str(uuid.uuid4())
    record_start(db, run_id, platform, run_group)

    today = datetime.now().strftime("%Y-%m-%d")
    output_json = DATA_OUT / f"raw-{platform}-{today}.json"
    output_csv = DATA_OUT / f"{platform}-candidates-{today}.csv"
    report_md = DATA_OUT / f"findings-{platform}-{today}.md"

    cmd = [
        "python3", str(SCRIPTS[platform]),
        "--output", str(output_json),
        "--csv-output", str(output_csv),
        "--report-md", str(report_md),
        "--date", today,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=SCAN_TIMEOUT_SEC,
            cwd=str(SCRIPTS[platform].parent),
        )
    except subprocess.TimeoutExpired:
        record_finish(db, run_id, "timeout", error="exceeded SCAN_TIMEOUT_SEC")
        return {"platform": platform, "status": "timeout", "item_count": 0,
                "csv_path": "", "error": "timeout"}

    item_count = 0
    if output_json.exists():
        try:
            data = json.loads(output_json.read_text())
            item_count = len(data) if isinstance(data, list) else 0
        except json.JSONDecodeError:
            pass

    threshold = MIN_ROWS.get(platform, 0)
    if result.returncode == 0 and item_count >= threshold:
        status = "success"
    elif item_count > 0:
        status = "partial"
    else:
        status = "failed"

    err = (result.stderr or "")[-300:] if status != "success" else ""
    record_finish(db, run_id, status, item_count=item_count,
                  csv_path=str(output_csv) if output_csv.exists() else "", error=err)
    return {"platform": platform, "status": status, "item_count": item_count,
            "csv_path": str(output_csv) if output_csv.exists() else "", "error": err}


# ─── Qualify pipeline (URL contract → dedup → LLM relevance) ────────────────
def qualify_results(csv_paths: list[str]) -> dict:
    """The three-stage funnel that turns raw scan output into a
    qualified CSV. Stages run in cost order: cheapest first, LLM last."""
    sys.path.insert(0, str(SHARED_DIR))
    from llm_qualifier import qualify, load_api_key, DOMAIN_THESIS, DEFAULT_ENV
    from output_contract import (
        is_url_with_path, is_post_url, is_status_url,
        is_article_url, is_thread_url,
    )

    PLATFORM_VALIDATORS = {
        "source-a": is_post_url,
        "source-b": is_status_url,
        "source-c": is_thread_url,
        "source-d": is_article_url,
    }

    db = init_db()
    cleanup_old_urls(db)
    contract_dropped = 0
    dedup_count = 0

    today = datetime.now().strftime("%Y-%m-%d")
    qualified_csv = DATA_OUT / f"qualified-{today}.csv"
    unqualified_csv = DATA_OUT / f"unqualified-{today}.csv"

    all_rows = []
    for csv_path in csv_paths:
        if not csv_path or not Path(csv_path).exists():
            continue
        rows_iter = []
        try:
            raw = Path(csv_path).read_text(encoding="utf-8").strip()
            if raw.startswith("["):
                # JSON array; flatten any nested {handle, posts:[]} structures
                for item in json.loads(raw):
                    if not isinstance(item, dict):
                        continue
                    if "posts" in item and isinstance(item["posts"], list):
                        for post in item["posts"]:
                            flat = {**post}
                            flat["author"] = item.get("name", item.get("handle", ""))
                            rows_iter.append(flat)
                    else:
                        rows_iter.append(item)
            else:
                with open(csv_path, "r", encoding="utf-8", newline="") as fh:
                    rows_iter = list(csv.DictReader(fh))
        except (OSError, json.JSONDecodeError, ValueError) as e:
            # File read or JSON-shape failure for one source. Skip and
            # let the others run — partial-success is better than total
            # abort when one scanner produced a bad output file.
            sys.stderr.write(f"  qualify: error reading {csv_path}: {e}\n")
            continue

        for row in rows_iter:
            url = (row.get("post_url") or row.get("article_url")
                   or row.get("url") or "").strip()
            if not url:
                continue
            text = (row.get("post_summary") or row.get("summary") or row.get("title")
                    or row.get("text") or "")
            stem = Path(csv_path).stem
            platform_guess = stem.replace("raw-", "").split("-")[0]

            # Stage 1: URL contract — drop malformed URLs before they
            # enter the dedup table or hit the LLM. Microseconds.
            validator = PLATFORM_VALIDATORS.get(platform_guess, is_url_with_path)
            if not validator(url):
                contract_dropped += 1
                continue

            # Stage 2: 30-day dedup
            if is_url_seen(db, url):
                dedup_count += 1
                continue

            all_rows.append({
                "url": url, "text": text, "source": csv_path,
                "raw": row, "platform": platform_guess,
            })

    # Stage 3: LLM relevance qualification (only on rows that survived 1+2)
    fieldnames = ["source", "url", "author", "post_summary", "qualification_reason"]
    q_rows, uq_rows = [], []

    if all_rows:
        api_key = load_api_key(Path(DEFAULT_ENV))
        qualified_items = qualify(api_key, all_rows, "text", DOMAIN_THESIS)
        qualified_urls = {item.get("url", "")[:100] for item in qualified_items} \
            if isinstance(qualified_items, list) else set()

        for row in all_rows:
            is_qualified = row["url"] in qualified_urls
            out_row = {
                "source": row["platform"],
                "url": row["url"],
                "author": row["raw"].get("author", row["raw"].get("person", "")),
                "post_summary": row["text"][:200],
                "qualification_reason": "on-thesis" if is_qualified else "off-thesis",
            }
            (q_rows if is_qualified else uq_rows).append(out_row)
            mark_url_seen(db, row["url"], row["platform"], qualified=is_qualified)

    if not q_rows and not uq_rows:
        return {"qualified_count": 0, "unqualified_count": 0,
                "qualified_csv": "", "unqualified_csv": "",
                "contract_dropped": contract_dropped, "dedup_skipped": dedup_count}

    for path, rows in [(qualified_csv, q_rows), (unqualified_csv, uq_rows)]:
        with open(path, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    sys.stderr.write(
        f"  qualify: {contract_dropped} contract-dropped, "
        f"{dedup_count} deduped, {len(all_rows)} new → "
        f"{len(q_rows)} qualified, {len(uq_rows)} rejected\n"
    )

    return {
        "qualified_count": len(q_rows),
        "unqualified_count": len(uq_rows),
        "dedup_skipped": dedup_count,
        "contract_dropped": contract_dropped,
        "qualified_csv": str(qualified_csv),
        "unqualified_csv": str(unqualified_csv),
        "dedup": get_dedup_stats(db),
    }


# ─── Weekly rollup ──────────────────────────────────────────────────────────
def generate_weekly_report() -> dict:
    today = datetime.now()
    week_start = (today - timedelta(days=7)).strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")
    weekly_csv = DATA_OUT / f"weekly-report-{today_str}.csv"

    all_qualified = []
    for f in sorted(DATA_OUT.glob("qualified-*.csv")):
        date_part = f.stem.replace("qualified-", "")
        if week_start <= date_part <= today_str:
            try:
                with open(f, "r", encoding="utf-8", newline="") as fh:
                    for row in csv.DictReader(fh):
                        row["scan_date"] = date_part
                        all_qualified.append(row)
            except (OSError, ValueError):
                # CSV read failure for one day's file — skip and roll up
                # the rest. The weekly report tolerates partial sources.
                continue

    # Dedup by URL across the week
    seen_urls = set()
    deduped = []
    for row in all_qualified:
        url = row.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            deduped.append(row)

    if deduped:
        fieldnames = list(deduped[0].keys())
        with open(weekly_csv, "w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(deduped)

    return {
        "period": f"{week_start} to {today_str}",
        "total_qualified": len(deduped),
        "duplicates_removed": len(all_qualified) - len(deduped),
        "csv_path": str(weekly_csv) if deduped else "",
    }


# ─── MCP protocol — tool registry + handler ─────────────────────────────────
TOOLS = [
    {
        "name": "run_scan",
        "description": "Run scans on specified source IDs in parallel with stagger.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "platforms": {
                    "type": "array",
                    "items": {"type": "string", "enum": list(SCRIPTS.keys())},
                },
            },
        },
    },
    {
        "name": "qualify",
        "description": "Run the three-stage qualify funnel (URL contract → dedup → LLM relevance) on raw scan outputs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "csv_paths": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    {
        "name": "smart_dedup",
        "description": "Cross-skill 30-day URL dedup. Returns which URLs have been seen by ANY scan.",
        "inputSchema": {
            "type": "object",
            "properties": {"urls": {"type": "array", "items": {"type": "string"}}},
            "required": ["urls"],
        },
    },
    {
        "name": "weekly_report",
        "description": "Roll up the past 7 days of qualified results, dedup by URL.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "cleanup",
        "description": "Delete artifacts older than retention window. Prune dedup table.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "scan_status",
        "description": "Query SQLite run history. Filter by run_group or today.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_group": {"type": "string"},
                "today_only": {"type": "boolean", "default": True},
            },
        },
    },
    {
        "name": "send_email",
        "description": "Send results email with CSV attached via Mail.app.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "qualified_csv": {"type": "string"},
                "subject": {"type": "string"},
            },
            "required": ["qualified_csv"],
        },
    },
]


def handle_tool_call(name: str, args: dict) -> dict:
    db = init_db()

    if name == "run_scan":
        platforms = args.get("platforms", list(SCRIPTS.keys()))
        run_group = str(uuid.uuid4())[:8]
        valid = [p for p in platforms if p in SCRIPTS]
        invalid = [{"platform": p, "status": "error",
                    "error": f"Unknown source: {p}"} for p in platforms if p not in SCRIPTS]

        def _run_with_stagger(idx_p):
            idx, platform = idx_p
            if idx > 0:
                time.sleep(idx * random.uniform(*STAGGER_SEC))
            return run_platform_scan(platform, db, run_group)

        results = list(invalid)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results.extend(pool.map(_run_with_stagger, enumerate(valid)))

        # Periodic cleanup of very old run rows
        db.execute("DELETE FROM runs WHERE started_at < date('now', '-90 days')")

        success = sum(1 for r in results if r.get("status") == "success")
        partial = sum(1 for r in results if r.get("status") == "partial")
        failed = sum(1 for r in results if r.get("status") in ("failed", "timeout", "error"))
        total_items = sum(r.get("item_count", 0) for r in results)
        overall = ("success" if failed == 0 and partial == 0 else
                   "partial_success" if success > 0 or partial > 0 else "failed")

        return {
            "run_group": run_group,
            "overall": overall,
            "summary": f"{success} full, {partial} partial, {failed} failed — {total_items} total items",
            "results": results,
        }

    if name == "qualify":
        csv_paths = args.get("csv_paths") or _autodiscover_today_raw()
        return qualify_results(csv_paths)

    if name == "smart_dedup":
        urls = args.get("urls") or []
        seen, new, meta = [], [], {}
        for url in urls:
            if not isinstance(url, str) or not url:
                continue
            row = db.execute(
                "SELECT platform, qualified FROM seen_urls "
                "WHERE url = ? AND last_seen > date('now', ?)",
                (url, f"-{DEDUP_WINDOW_DAYS} days"),
            ).fetchone()
            if row:
                seen.append(url)
                meta[url] = {"platform": row[0], "qualified": bool(row[1])}
            else:
                new.append(url)
        return {
            "seen_count": len(seen), "new_count": len(new),
            "seen": seen, "new": new, "seen_metadata": meta,
            "window_days": DEDUP_WINDOW_DAYS,
        }

    if name == "weekly_report":
        return generate_weekly_report()

    if name == "cleanup":
        cutoff = (datetime.now() - timedelta(days=RETENTION_DAYS)).strftime("%Y-%m-%d")
        deleted = []
        for f in DATA_OUT.iterdir():
            if not f.is_file():
                continue
            # Only touch files with an embedded YYYY-MM-DD older than cutoff
            for chunk in f.stem.split("-"):
                if len(chunk) == 10 and chunk < cutoff and chunk.count("-") == 0:
                    f.unlink()
                    deleted.append(f.name)
                    break
        cleanup_old_urls(db)
        return {"deleted_count": len(deleted), "cutoff_date": cutoff,
                "dedup_after_cleanup": get_dedup_stats(db)}

    if name == "scan_status":
        today = datetime.now().strftime("%Y-%m-%d")
        query = "SELECT * FROM runs"
        params = []
        if args.get("run_group"):
            query += " WHERE run_group = ?"
            params.append(args["run_group"])
        elif args.get("today_only", True):
            query += " WHERE started_at LIKE ?"
            params.append(f"{today}%")
        query += " ORDER BY started_at DESC LIMIT 30"
        rows = db.execute(query, params).fetchall()
        cols = ["id", "platform", "status", "started_at", "finished_at",
                "item_count", "csv_path", "error", "run_group"]
        return {"runs": [dict(zip(cols, row)) for row in rows]}

    if name == "send_email":
        # Implementation lives in send_email.py — uses Mail.app AppleScript.
        # Stub here to keep the sample focused on orchestration.
        return {"sent": False, "note": "see send_email.py for implementation"}

    return {"error": f"Unknown tool: {name}"}


def _autodiscover_today_raw():
    today = datetime.now().strftime("%Y-%m-%d")
    return [str(p) for p in DATA_OUT.glob(f"raw-*-{today}.json")]


# ─── Stdio JSON-RPC loop ────────────────────────────────────────────────────
def send(payload: dict):
    """Write a JSON-RPC reply on stdout. Flushes after every write."""
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


def main():
    """Read newline-delimited JSON-RPC from stdin; respond on stdout."""
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = req.get("method", "")
        rid = req.get("id")
        params = req.get("params", {})

        if method == "initialize":
            send({"jsonrpc": "2.0", "id": rid, "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "scan-pipeline", "version": "1.0.0"},
            }})
        elif method == "tools/list":
            send({"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {}) or {}
            try:
                result = handle_tool_call(tool_name, tool_args)
                send({"jsonrpc": "2.0", "id": rid, "result": {
                    "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
                }})
            except Exception as exc:
                send({"jsonrpc": "2.0", "id": rid, "error": {
                    "code": -32603, "message": f"{type(exc).__name__}: {exc}",
                }})


if __name__ == "__main__":
    main()
