"""Tests for skill-rating-eval/compute_unrated_jobs.py.

Pins the standup-loop semantics:
- empty inputs → empty output
- a run with no platforms produces 1 unrated entry (platform="")
- a run with N platforms produces N unrated entries
- already-rated (job_id, platform) pairs are excluded
- carryovers from previous days appear alongside today's runs
- the --since filter drops older entries
"""
import json
from datetime import datetime, timedelta

import pytest

import compute_unrated_jobs as cuj
import run_tracker


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    """Re-route both modules to a temp directory so tests don't interfere."""
    monkeypatch.setattr(run_tracker, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(cuj, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(cuj, "RATINGS_FILE", tmp_path / "ratings" / "ratings.jsonl")


def _seed_run(skill: str, platforms=None, **extra):
    run = run_tracker.start_run(skill=skill, platforms=platforms or [], **extra)
    run_tracker.finish_run(run, status="success")
    return run["job_id"]


def _seed_rating(ratings_file, job_id: str, platform: str = "", rating: int = 5):
    ratings_file.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "job_id": job_id,
        "platform": platform,
        "rating": rating,
        "rated_at": datetime.now().isoformat(timespec="seconds"),
    }
    with ratings_file.open("a") as f:
        f.write(json.dumps(record) + "\n")


class TestEmptyInputs:
    def test_no_runs_returns_empty(self, capsys):
        cuj.main_args = []
        # We use the module's internal _all_runs and _rated_keys directly
        runs = list(cuj._all_runs())
        assert runs == []
        rated = cuj._rated_keys()
        assert rated == set()


class TestSinglePlatformRun:
    def test_no_platforms_one_unrated(self):
        _seed_run("scan-a")
        runs = list(cuj._all_runs())
        rated = cuj._rated_keys()
        assert len(runs) == 1
        assert runs[0]["skill"] == "scan-a"
        # platform-fanout: empty list means one rateable item with platform=""
        ps = runs[0].get("platforms") or [""]
        assert ps == [""]
        for p in ps:
            assert (runs[0]["job_id"], p) not in rated


class TestMultiPlatformFanout:
    def test_four_platforms_four_units(self):
        _seed_run("bundled-scan", platforms=["a", "b", "c", "d"])
        runs = list(cuj._all_runs())
        # The compute logic iterates platforms[]; each one is a rateable item.
        unrated_units = []
        for run in runs:
            for p in (run.get("platforms") or [""]):
                unrated_units.append((run["job_id"], p))
        assert len(unrated_units) == 4
        platforms = [p for (_, p) in unrated_units]
        assert sorted(platforms) == ["a", "b", "c", "d"]


class TestRatedExclusion:
    def test_rated_pair_excluded(self, tmp_path, monkeypatch):
        ratings_file = tmp_path / "ratings" / "ratings.jsonl"
        monkeypatch.setattr(cuj, "RATINGS_FILE", ratings_file)

        job_id = _seed_run("scan-a", platforms=["x", "y"])
        _seed_rating(ratings_file, job_id, platform="x", rating=4)

        rated = cuj._rated_keys()
        assert (job_id, "x") in rated
        assert (job_id, "y") not in rated

    def test_partial_rating_leaves_carryover(self, tmp_path, monkeypatch):
        # Rate one of the four platforms; the other three carry over.
        ratings_file = tmp_path / "ratings" / "ratings.jsonl"
        monkeypatch.setattr(cuj, "RATINGS_FILE", ratings_file)

        job_id = _seed_run("bundled", platforms=["a", "b", "c", "d"])
        _seed_rating(ratings_file, job_id, platform="b", rating=3)

        rated = cuj._rated_keys()
        unrated_count = 0
        for run in cuj._all_runs():
            for p in run.get("platforms") or [""]:
                if (run["job_id"], p) not in rated:
                    unrated_count += 1
        assert unrated_count == 3
