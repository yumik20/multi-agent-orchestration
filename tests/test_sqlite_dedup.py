"""Tests for cost-optimization/sqlite_dedup.py.

Pins the contract that production scanners depend on:
- mark_seen + is_seen roundtrip
- partition() returns (seen, new, metadata) with correct splits
- cleanup_old removes rows outside the window
- stats() returns the expected shape
- platform metadata is preserved on seen rows
"""
import os
from datetime import datetime, timedelta

import pytest

from sqlite_dedup import UrlDedup


@pytest.fixture
def dedup(tmp_path):
    db = UrlDedup(tmp_path / "dedup.db", window_days=30)
    yield db
    db.close()


class TestMarkAndSee:
    def test_unseen_initially(self, dedup):
        assert not dedup.is_seen("https://example.com/a")

    def test_mark_then_seen(self, dedup):
        dedup.mark_seen("https://example.com/a", platform="src-a", qualified=True)
        assert dedup.is_seen("https://example.com/a")

    def test_mark_refreshes_last_seen(self, dedup):
        # Marking the same URL twice should not create a duplicate row.
        dedup.mark_seen("https://example.com/a", platform="src-a")
        dedup.mark_seen("https://example.com/a", platform="src-a")
        stats = dedup.stats()
        assert stats["total_urls"] == 1


class TestPartition:
    def test_splits_seen_and_new(self, dedup):
        dedup.mark_seen("https://example.com/a", platform="src-a", qualified=True)
        dedup.mark_seen("https://example.com/b", platform="src-b", qualified=False)

        seen, new, meta = dedup.partition([
            "https://example.com/a",     # seen + qualified
            "https://example.com/b",     # seen + not qualified
            "https://example.com/c",     # new
        ])

        assert seen == ["https://example.com/a", "https://example.com/b"]
        assert new == ["https://example.com/c"]
        assert meta["https://example.com/a"]["qualified"] is True
        assert meta["https://example.com/b"]["qualified"] is False
        assert meta["https://example.com/a"]["platform"] == "src-a"

    def test_skips_blank_urls(self, dedup):
        seen, new, meta = dedup.partition(["", None, "https://example.com/x"])
        assert seen == []
        assert new == ["https://example.com/x"]


class TestStats:
    def test_empty_db(self, dedup):
        stats = dedup.stats()
        assert stats["total_urls"] == 0
        assert stats["by_platform"] == {}
        assert stats["last_7_days"] == 0
        assert stats["window_days"] == 30

    def test_groups_by_platform(self, dedup):
        dedup.mark_seen("https://example.com/a", platform="src-a")
        dedup.mark_seen("https://example.com/b", platform="src-a")
        dedup.mark_seen("https://example.com/c", platform="src-b")
        stats = dedup.stats()
        assert stats["total_urls"] == 3
        assert stats["by_platform"] == {"src-a": 2, "src-b": 1}


class TestCleanup:
    def test_removes_only_old_rows(self, dedup):
        dedup.mark_seen("https://example.com/recent", platform="src-a")

        # Backdate one row past the window using a direct SQL update.
        old_iso = (datetime.now() - timedelta(days=60)).isoformat(timespec="seconds")
        dedup._db.execute(
            "INSERT INTO seen_urls (url, platform, first_seen, last_seen, qualified) "
            "VALUES (?, ?, ?, ?, ?)",
            ("https://example.com/old", "src-a", old_iso, old_iso, 0),
        )

        deleted = dedup.cleanup_old()
        assert deleted == 1
        assert dedup.is_seen("https://example.com/recent")
        assert not dedup.is_seen("https://example.com/old")
