"""
SQLite-backed 30-day rolling URL dedup.

Replaces the previous JSON-file dedup cache. With thousands of URLs
across multiple sources, the JSON cache became a bottleneck:
- Read entire file → parse → mutate → rewrite
- Each scanner kept its own copy → no cross-skill state
- Diff size grew unbounded

SQLite gives:
- WAL-mode incremental writes (no file rewrite)
- Indexed lookups in microseconds
- Single shared state queryable cross-skill via an MCP tool
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

DEFAULT_WINDOW_DAYS = 30


class UrlPartition(NamedTuple):
    """Result of UrlDedup.partition(). Three named fields plus positional
    unpacking (NamedTuples support both `result.seen` and
    `seen, new, meta = partition(urls)` style)."""
    seen: list[str]
    new: list[str]
    metadata: dict[str, dict]   # {url: {"platform": str, "qualified": bool}}


class UrlDedup:
    """30-day rolling URL dedup. Thread-safe via SQLite's own locking."""

    def __init__(self, db_path: str | Path, window_days: int = DEFAULT_WINDOW_DAYS):
        self.db_path = str(db_path)
        self.window_days = window_days
        self._db = sqlite3.connect(self.db_path,
                                   isolation_level=None,
                                   check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS seen_urls (
                url        TEXT PRIMARY KEY,
                platform   TEXT NOT NULL,
                first_seen TEXT NOT NULL,
                last_seen  TEXT NOT NULL,
                qualified  INTEGER DEFAULT 0
            )
        """)
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_seen_urls_last_seen "
            "ON seen_urls(last_seen)"
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_seen_urls_platform "
            "ON seen_urls(platform)"
        )

    def is_seen(self, url: str) -> bool:
        """True if URL is in the rolling window."""
        row = self._db.execute(
            "SELECT 1 FROM seen_urls WHERE url = ? AND last_seen > date('now', ?)",
            (url, f"-{self.window_days} days"),
        ).fetchone()
        return row is not None

    def mark_seen(self, url: str, platform: str, qualified: bool = False) -> None:
        """Insert or refresh last_seen for a URL."""
        now = datetime.now().isoformat(timespec="seconds")
        self._db.execute("""
            INSERT INTO seen_urls (url, platform, first_seen, last_seen, qualified)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET last_seen = ?, qualified = ?
        """, (url, platform, now, now, int(qualified), now, int(qualified)))

    def cleanup_old(self) -> int:
        """Delete rows outside the rolling window. Returns rows deleted."""
        cur = self._db.execute(
            "DELETE FROM seen_urls WHERE last_seen < date('now', ?)",
            (f"-{self.window_days} days",),
        )
        return cur.rowcount

    def stats(self) -> dict:
        """Total URLs, by-platform breakdown, last-7-days count."""
        total = self._db.execute("SELECT COUNT(*) FROM seen_urls").fetchone()[0]
        by_platform = dict(self._db.execute(
            "SELECT platform, COUNT(*) FROM seen_urls GROUP BY platform"
        ).fetchall())
        recent = self._db.execute(
            "SELECT COUNT(*) FROM seen_urls WHERE last_seen > date('now', '-7 days')"
        ).fetchone()[0]
        return {
            "total_urls": total,
            "by_platform": by_platform,
            "last_7_days": recent,
            "window_days": self.window_days,
        }

    def partition(self, urls: list[str]) -> UrlPartition:
        """Split urls into (seen, new, metadata).

        metadata maps each seen url to {platform, qualified}, so callers
        can decide whether to re-qualify a previously-rejected URL when
        the qualify rules have changed. Returns a NamedTuple so callers
        can use either positional unpacking
        (`seen, new, meta = d.partition(urls)`) or named access
        (`d.partition(urls).metadata`).
        """
        seen, new, meta = [], [], {}
        for url in urls:
            if not isinstance(url, str) or not url:
                continue
            row = self._db.execute(
                "SELECT platform, qualified FROM seen_urls "
                "WHERE url = ? AND last_seen > date('now', ?)",
                (url, f"-{self.window_days} days"),
            ).fetchone()
            if row:
                seen.append(url)
                meta[url] = {"platform": row[0], "qualified": bool(row[1])}
            else:
                new.append(url)
        return UrlPartition(seen=seen, new=new, metadata=meta)

    def close(self):
        self._db.close()


# ── CLI for one-off inspection ─────────────────────────────────────────────

def _cli():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("db", help="Path to dedup SQLite file")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("stats")
    p_check = sub.add_parser("check"); p_check.add_argument("urls", nargs="+")
    sub.add_parser("cleanup")
    args = parser.parse_args()

    d = UrlDedup(args.db)
    if args.cmd == "stats":
        import json; print(json.dumps(d.stats(), indent=2))
    elif args.cmd == "check":
        seen, new, meta = d.partition(args.urls)
        print(f"seen ({len(seen)}):")
        for u in seen:
            print(f"  {u} → {meta[u]}")
        print(f"new ({len(new)}):")
        for u in new:
            print(f"  {u}")
    elif args.cmd == "cleanup":
        n = d.cleanup_old()
        print(f"deleted {n} rows outside {d.window_days}-day window")
    d.close()


if __name__ == "__main__":
    _cli()
