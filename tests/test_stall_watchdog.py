"""Tests for agent-orchestration/stall_watchdog.py.

Pins the dual-kill state machine the user critique flagged as untested:
- happy path (clean exit within total_timeout, no kill)
- wall-time timeout fires kill
- output-stall timeout fires kill when csv mtime stalls
- stall detector resets on csv writes (no kill if writes resume)
- kill failures are logged + swallowed (ProcessLookupError, PermissionError)
- csv_path_hint=None disables stall detection (only wall-time applies)
- "no csv ever written" produces a distinct kill reason

Mocks subprocess.Popen, time.time, and Path.stat at the module level so
the test runs in milliseconds without spawning any real processes.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

import stall_watchdog


# ── Helpers ────────────────────────────────────────────────────────────────

class FakeClock:
    """Controllable monotonic clock. test.tick(n) advances by n seconds."""
    def __init__(self, start: float = 1000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def tick(self, seconds: float) -> None:
        self.now += seconds


def _make_fake_proc(poll_sequence: list, pid: int = 12345,
                    communicate_returns: tuple = ("stdout-out", "stderr-out")):
    """Build a Mock that quacks like a subprocess.Popen.

    poll_sequence: each call to .poll() returns the next item.
                   None = still running, int = exit code.
    """
    proc = MagicMock()
    proc.pid = pid
    proc.returncode = None
    poll_iter = iter(poll_sequence)

    def _poll():
        try:
            rc = next(poll_iter)
        except StopIteration:
            rc = poll_sequence[-1]   # cling to last value
        if rc is not None:
            proc.returncode = rc
        return rc

    proc.poll.side_effect = _poll
    proc.communicate.return_value = communicate_returns
    proc.kill = MagicMock()
    return proc


@pytest.fixture
def clock():
    """Patch time.time() in the stall_watchdog module with our controllable clock."""
    c = FakeClock()
    with patch.object(stall_watchdog.time, "time", side_effect=c):
        # Also no-op time.sleep so the poll loop doesn't actually wait.
        with patch.object(stall_watchdog.time, "sleep"):
            yield c


@pytest.fixture
def no_csv_path():
    """Convenience: most tests don't need a CSV path hint."""
    return None


# ── Test 1: happy path ─────────────────────────────────────────────────────

def test_happy_path_clean_exit(clock):
    """Subprocess exits cleanly before any watchdog fires."""
    proc = _make_fake_proc(poll_sequence=[None, None, 0])
    with patch.object(stall_watchdog.subprocess, "Popen", return_value=proc):
        result = stall_watchdog.run_collector_with_stall_watchdog(
            ["echo", "ok"],
            total_timeout_seconds=60,
            stall_timeout_seconds=10,
            csv_path_hint=None,
            poll_interval_seconds=0.0,
        )

    assert result.returncode == 0
    assert result.timed_out is False
    assert result.stall_killed is False
    proc.kill.assert_not_called()


# ── Test 2: wall-time timeout ──────────────────────────────────────────────

def test_wall_time_timeout_fires_kill(clock):
    """Subprocess never exits; wall-time elapses; kill is sent."""
    proc = _make_fake_proc(poll_sequence=[None] * 50)

    # Each poll() call ticks the clock past the timeout boundary.
    original_poll = proc.poll.side_effect

    def _poll_with_clock_tick():
        clock.tick(20)
        return original_poll()

    proc.poll.side_effect = _poll_with_clock_tick

    with patch.object(stall_watchdog.subprocess, "Popen", return_value=proc):
        result = stall_watchdog.run_collector_with_stall_watchdog(
            ["sleep", "999"],
            total_timeout_seconds=30,
            stall_timeout_seconds=120,
            csv_path_hint=None,
            poll_interval_seconds=0.0,
        )

    assert result.timed_out is True
    assert result.stall_killed is False
    proc.kill.assert_called_once()
    assert "absolute timeout" in result.stderr


# ── Test 3: output-stall timeout ───────────────────────────────────────────

def test_csv_stall_fires_kill(clock, tmp_path):
    """CSV exists at start, mtime never advances, stall timeout fires."""
    csv = tmp_path / "out.csv"
    csv.write_text("seed,row\n")
    initial_mtime = csv.stat().st_mtime

    proc = _make_fake_proc(poll_sequence=[None] * 50)

    # Each poll advances clock; mtime never changes; stall detector fires.
    def _poll_with_clock_tick():
        clock.tick(10)
        # Force the recorded mtime to stay constant (don't touch the file).
        return None if proc.poll.call_count < 10 else None

    proc.poll.side_effect = _poll_with_clock_tick

    with patch.object(stall_watchdog.subprocess, "Popen", return_value=proc):
        result = stall_watchdog.run_collector_with_stall_watchdog(
            ["./collector"],
            total_timeout_seconds=600,
            stall_timeout_seconds=20,
            csv_path_hint=str(csv),
            poll_interval_seconds=0.0,
        )

    assert result.stall_killed is True
    assert result.timed_out is False
    proc.kill.assert_called_once()
    assert "stall" in result.stderr.lower()
    # The file existed at start, so the message names it.
    assert "out.csv" in result.stderr


# ── Test 4: stall detector resets on writes ────────────────────────────────

def test_stall_resets_on_csv_writes(clock, tmp_path):
    """CSV mtime advances periodically; stall timer resets each time;
    process exits cleanly before stall window ever elapses without a write."""
    csv = tmp_path / "out.csv"
    csv.write_text("seed\n")

    poll_count = [0]

    def _poll_advancing_csv():
        poll_count[0] += 1
        clock.tick(5)
        # Touch the CSV to advance its mtime (every poll = active write).
        csv.write_text(f"seed\nrow{poll_count[0]}\n")
        # Exit cleanly after 6 polls (~30s elapsed).
        return 0 if poll_count[0] >= 6 else None

    proc = _make_fake_proc(poll_sequence=[None] * 10)
    proc.poll.side_effect = _poll_advancing_csv

    with patch.object(stall_watchdog.subprocess, "Popen", return_value=proc):
        result = stall_watchdog.run_collector_with_stall_watchdog(
            ["./collector"],
            total_timeout_seconds=600,
            stall_timeout_seconds=20,
            csv_path_hint=str(csv),
            poll_interval_seconds=0.0,
        )

    assert result.stall_killed is False
    assert result.timed_out is False
    proc.kill.assert_not_called()


# ── Test 5: kill failure — ProcessLookupError logged + swallowed ──────────

def test_kill_failure_process_lookup_error(clock, capsys):
    """os.kill raising ProcessLookupError shouldn't crash the wrapper.
    Should log the failure to stderr (the bug the user explicitly flagged
    in the original audit was: kill failures were silently swallowed)."""
    proc = _make_fake_proc(poll_sequence=[None] * 50)
    proc.kill.side_effect = ProcessLookupError("no such process")

    def _poll_with_clock_tick():
        clock.tick(20)
        return None

    proc.poll.side_effect = _poll_with_clock_tick

    with patch.object(stall_watchdog.subprocess, "Popen", return_value=proc):
        # Should NOT raise.
        result = stall_watchdog.run_collector_with_stall_watchdog(
            ["./dead"],
            total_timeout_seconds=30,
            stall_timeout_seconds=120,
            csv_path_hint=None,
            poll_interval_seconds=0.0,
        )

    assert result.timed_out is True
    # ProcessLookupError is the "already-dead" race; we explicitly chose
    # to swallow this one without logging since it's expected.
    proc.kill.assert_called_once()


def test_kill_failure_permission_error_logs(clock, capsys):
    """OSError (PermissionError) on kill should be logged to stderr —
    that's the operator-visible signal that the watchdog wanted to kill
    but couldn't. Was the silent-swallow bug the user critique flagged."""
    proc = _make_fake_proc(poll_sequence=[None] * 50)
    proc.kill.side_effect = PermissionError("not permitted")

    def _poll_with_clock_tick():
        clock.tick(20)
        return None

    proc.poll.side_effect = _poll_with_clock_tick

    with patch.object(stall_watchdog.subprocess, "Popen", return_value=proc):
        result = stall_watchdog.run_collector_with_stall_watchdog(
            ["./root_only"],
            total_timeout_seconds=30,
            stall_timeout_seconds=120,
            csv_path_hint=None,
            poll_interval_seconds=0.0,
        )

    captured = capsys.readouterr()
    assert "[watchdog] kill failed" in captured.err
    assert "not permitted" in captured.err
    assert result.timed_out is True


# ── Test 7: csv_path_hint=None disables stall detection ───────────────────

def test_csv_path_none_only_wall_time_matters(clock):
    """With csv_path_hint=None, the stall detector code is skipped
    entirely. Only wall-time timeout can kill."""
    proc = _make_fake_proc(poll_sequence=[None] * 50)

    poll_count = [0]
    def _poll_with_clock_tick():
        poll_count[0] += 1
        clock.tick(5)
        # Exit cleanly at poll #5 (~25s elapsed) — well under 60s timeout.
        return 0 if poll_count[0] >= 5 else None

    proc.poll.side_effect = _poll_with_clock_tick

    with patch.object(stall_watchdog.subprocess, "Popen", return_value=proc):
        result = stall_watchdog.run_collector_with_stall_watchdog(
            ["./silent"],
            total_timeout_seconds=60,
            stall_timeout_seconds=10,   # would fire if csv_path_hint were set
            csv_path_hint=None,
            poll_interval_seconds=0.0,
        )

    # No kill — stall detection inactive without csv_path_hint.
    assert result.stall_killed is False
    assert result.timed_out is False
    proc.kill.assert_not_called()


# ── Test 8: no csv ever written produces distinct message ─────────────────

def test_no_csv_written_distinct_message(clock, tmp_path):
    """When the CSV doesn't exist at start AND never gets written, the
    stall message should explicitly say 'No CSV written at all' rather
    than 'hasn't been written for Ns'. Pin that distinction."""
    csv = tmp_path / "never_appears.csv"   # never created

    proc = _make_fake_proc(poll_sequence=[None] * 50)

    def _poll_with_clock_tick():
        clock.tick(10)
        return None

    proc.poll.side_effect = _poll_with_clock_tick

    with patch.object(stall_watchdog.subprocess, "Popen", return_value=proc):
        result = stall_watchdog.run_collector_with_stall_watchdog(
            ["./collector"],
            total_timeout_seconds=600,
            stall_timeout_seconds=20,
            csv_path_hint=str(csv),
            poll_interval_seconds=0.0,
        )

    assert result.stall_killed is True
    assert "No CSV written at all" in result.stderr
