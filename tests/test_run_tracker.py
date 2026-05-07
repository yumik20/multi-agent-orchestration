"""Tests for skill-rating-eval/run_tracker.py.

Pins:
- start_run + finish_run produce a well-formed JSONL record
- ms-precision job_id stays unique across rapid-fire runs
- platforms list is preserved end-to-end
- artifacts are string-coerced for safe JSON serialization
- iter_runs respects (since, until) windowing
"""
import json
from datetime import datetime, timedelta

import pytest

import run_tracker


@pytest.fixture(autouse=True)
def isolated_runs_dir(tmp_path, monkeypatch):
    """Each test gets its own runs/ directory so tests don't bleed into
    the developer's actual runs/ dir or each other."""
    monkeypatch.setattr(run_tracker, "RUNS_DIR", tmp_path / "runs")


class TestStartFinishRoundtrip:
    def test_writes_well_formed_record(self):
        run = run_tracker.start_run(skill="test-skill", trigger="manual",
                                    mcps_used=["mcp-a"])
        path = run_tracker.finish_run(run, status="success",
                                      artifacts=["/tmp/x.csv"],
                                      row_count=42)

        assert path.exists()
        records = [json.loads(l) for l in path.read_text().splitlines()]
        assert len(records) == 1
        rec = records[0]
        assert rec["skill"] == "test-skill"
        assert rec["status"] == "success"
        assert rec["row_count"] == 42
        assert rec["mcps_used"] == ["mcp-a"]
        assert rec["artifacts"] == ["/tmp/x.csv"]
        assert "duration_s" in rec
        assert rec["duration_s"] >= 0

    def test_failure_status_preserves_error(self):
        run = run_tracker.start_run(skill="test-skill")
        path = run_tracker.finish_run(run, status="failure",
                                      error="endpoint timeout")
        rec = json.loads(path.read_text())
        assert rec["status"] == "failure"
        assert rec["error"] == "endpoint timeout"


class TestJobIdUniqueness:
    def test_unique_under_rapid_calls(self):
        """Same skill, 50 starts in a tight loop. All job_ids must differ.
        Production cron rarely hits this, but smoke tests do."""
        ids = set()
        for _ in range(50):
            r = run_tracker.start_run(skill="rapid-skill")
            ids.add(r["job_id"])
        assert len(ids) == 50

    def test_job_id_starts_with_skill_name(self):
        r = run_tracker.start_run(skill="my-skill")
        assert r["job_id"].startswith("my-skill@")


class TestPlatforms:
    def test_platforms_preserved(self):
        run = run_tracker.start_run(skill="bundled-scan",
                                    platforms=["src-a", "src-b", "src-c"])
        path = run_tracker.finish_run(run, status="success", row_count=10)
        rec = json.loads(path.read_text())
        assert rec["platforms"] == ["src-a", "src-b", "src-c"]

    def test_no_platforms_default_empty_list(self):
        run = run_tracker.start_run(skill="single-purpose")
        path = run_tracker.finish_run(run, status="success")
        rec = json.loads(path.read_text())
        assert rec["platforms"] == []


class TestArtifactsCoercion:
    def test_path_objects_become_strings(self, tmp_path):
        from pathlib import Path
        run = run_tracker.start_run(skill="path-test")
        artifact = tmp_path / "out.csv"
        path = run_tracker.finish_run(run, status="success",
                                      artifacts=[artifact])
        rec = json.loads(path.read_text())
        assert rec["artifacts"] == [str(artifact)]
        assert isinstance(rec["artifacts"][0], str)


class TestIterRuns:
    def test_respects_since_window(self):
        # Write a run, then iter_runs(since=tomorrow) should yield nothing.
        run = run_tracker.start_run(skill="test")
        run_tracker.finish_run(run, status="success")
        future = datetime.now() + timedelta(days=1)
        assert list(run_tracker.iter_runs(since=future)) == []

    def test_returns_run_when_within_window(self):
        run = run_tracker.start_run(skill="test")
        run_tracker.finish_run(run, status="success")
        past = datetime.now() - timedelta(hours=1)
        future = datetime.now() + timedelta(hours=1)
        records = list(run_tracker.iter_runs(since=past, until=future))
        assert len(records) == 1
        assert records[0]["skill"] == "test"
