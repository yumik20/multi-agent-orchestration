"""
run_tracker — record every skill execution to a single append-only log
so the evening standup can ask the operator to rate them.

Schema (one JSON object per line, runs/YYYY-MM/runs.jsonl):

    {
      "job_id":     "scan-source-a@2026-05-06T07:30:00.123-3b9f",
      "skill":      "scan-source-a",
      "mcps_used":  ["scan-pipeline"],
      "platforms":  [],                    # or ["a","b","c"] for bundled runs
      "trigger":    "cron" | "manual" | "agent",
      "started":    "2026-05-06T07:30:00",
      "finished":   "2026-05-06T07:35:12",
      "duration_s": 312,
      "artifacts":  ["/path/to/output.csv", ...],
      "row_count":  42,
      "status":     "success" | "failure" | "partial",
      "error":      null | "short message",
      "extra":      {"model_actual": "...", ...}
    }

Usage from a skill script:

    from run_tracker import start_run, finish_run

    run = start_run(
        skill="scan-source-a",
        trigger="cron",
        mcps_used=["scan-pipeline"],
    )
    try:
        ...do work...
        finish_run(run, status="success", artifacts=[csv_path], row_count=42)
    except Exception as e:
        finish_run(run, status="failure", error=str(e))
        raise

For runs that bundle multiple sources in one execution (e.g. a morning
scan that hits four sources in parallel), pass `platforms=[...]`. The
standup will fan out into one rateable item per platform, and the
weekly memo aggregates by `(skill, platform)`.
"""
from __future__ import annotations

import json
import os
import secrets
import time
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict


class RunHandle(TypedDict):
    """In-memory run state returned by start_run() and consumed by
    finish_run(). Not the on-disk record (see RunRecord)."""
    job_id: str
    skill: str
    mcps_used: list[str]
    platforms: list[str]
    trigger: str
    started: str
    _started_monotonic: float
    extra: dict[str, Any]


class RunRecord(TypedDict):
    """One JSONL line in runs.jsonl. The append-only on-disk shape that
    the eval pipeline reads."""
    job_id: str
    skill: str
    mcps_used: list[str]
    platforms: list[str]
    trigger: str
    started: str
    finished: str
    duration_s: float
    artifacts: list[str]
    row_count: int | None
    status: str
    error: str | None
    extra: dict[str, Any]


ROOT = Path(__file__).parent
RUNS_DIR = ROOT / "runs"


def _month_dir(now: datetime) -> Path:
    d = RUNS_DIR / now.strftime("%Y-%m")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _runs_file(now: datetime) -> Path:
    return _month_dir(now) / "runs.jsonl"


def _now() -> datetime:
    return datetime.now()


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def _iso_ms(dt: datetime) -> str:
    """Millisecond-precision ISO timestamp — used in job_id so rapid
    same-skill runs don't collide."""
    ms = dt.microsecond // 1000
    return dt.replace(microsecond=0).isoformat() + f".{ms:03d}"


def start_run(
    skill: str,
    trigger: str = "manual",
    mcps_used: list[str] | None = None,
    platforms: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> RunHandle:
    """Begin a run. Returns a RunHandle you must pass to finish_run.

    `platforms`: optional list of sub-units the operator should rate
    separately. A morning scan that hits four sources in parallel
    declares platforms=["a","b","c","d"], and the standup fans out
    into four rateable items.
    """
    started = _now()
    # 4-hex suffix breaks ties when two runs of the same skill start
    # in the same millisecond (smoke tests do this; cron rarely will).
    job_id = f"{skill}@{_iso_ms(started)}-{secrets.token_hex(2)}"
    return RunHandle(
        job_id=job_id,
        skill=skill,
        mcps_used=list(mcps_used or []),
        platforms=list(platforms or []),
        trigger=trigger,
        started=_iso(started),
        _started_monotonic=time.monotonic(),
        extra=dict(extra or {}),
    )


def finish_run(
    run: RunHandle,
    status: str = "success",
    artifacts: list[str] | None = None,
    row_count: int | None = None,
    error: str | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    """Append the finished run to today's runs.jsonl. Returns the path."""
    finished = _now()
    duration = round(time.monotonic() - run["_started_monotonic"], 2)
    record: RunRecord = {
        "job_id": run["job_id"],
        "skill": run["skill"],
        "mcps_used": run["mcps_used"],
        "platforms": run.get("platforms", []),
        "trigger": run["trigger"],
        "started": run["started"],
        "finished": _iso(finished),
        "duration_s": duration,
        "artifacts": [str(p) for p in (artifacts or [])],
        "row_count": row_count,
        "status": status,
        "error": error,
        "extra": {**run.get("extra", {}), **(extra or {})},
    }
    path = _runs_file(finished)
    with path.open("a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    return path


def iter_runs(since: datetime | None = None, until: datetime | None = None):
    """Yield every run record across all month files, optionally filtered
    by finished-time window. Skips malformed lines."""
    if not RUNS_DIR.exists():
        return
    for month_dir in sorted(RUNS_DIR.iterdir()):
        f = month_dir / "runs.jsonl"
        if not f.exists():
            continue
        for line in f.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if since or until:
                try:
                    finished_dt = datetime.fromisoformat(rec.get("finished", ""))
                except ValueError:
                    continue
                if since and finished_dt < since:
                    continue
                if until and finished_dt > until:
                    continue
            yield rec
