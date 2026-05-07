"""
Retry helper that uses the classifier to decide retry behavior per
exception category instead of "try N times with a fixed sleep."

The classifier knows that:
- network errors should retry 3× with 2s base + jitter
- rate_limit errors should retry 2× with 5s base
- auth + model errors should fail fast (retry doesn't help)
- parse errors are caller-specific (we expose them but don't retry)

Usage:

    from retry_with_backoff import retry_with_backoff

    def _do_call():
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)

    result = retry_with_backoff(_do_call, log_prefix="qualify-batch: ")

The wrapped function gets retried automatically. On final failure, the
last exception is re-raised so the caller can decide what to do.
"""
from __future__ import annotations

import random
import sys
import time
from typing import Callable, TypeVar

from error_classifier import classify, ErrorCategory


T = TypeVar("T")


def retry_with_backoff(
    fn: Callable[[], T],
    *,
    log_prefix: str = "",
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Call `fn`, retrying on classified-retryable exceptions.

    Backoff: base * 2^attempt + uniform(0, base/2) jitter. The jitter
    exists to prevent thundering-herd when multiple skills hit the
    same rate-limit window simultaneously.

    `sleep` is overrideable for tests (pass a lambda that records
    sleep durations instead of actually sleeping).
    """
    attempt = 0
    last_exc: BaseException | None = None

    while True:
        try:
            return fn()
        except BaseException as exc:
            last_exc = exc
            cat = classify(exc)

            if not cat.retryable:
                sys.stderr.write(
                    f"{log_prefix}{cat.type} (no retry): {exc}\n"
                )
                raise

            if attempt >= cat.max_retries:
                sys.stderr.write(
                    f"{log_prefix}{cat.type} exhausted ({attempt} retries): {exc}\n"
                )
                raise

            delay = _delay_for(cat, attempt)
            sys.stderr.write(
                f"{log_prefix}{cat.type} retry {attempt + 1}/{cat.max_retries} "
                f"in {delay:.1f}s: {exc}\n"
            )
            sleep(delay)
            attempt += 1


def _delay_for(cat: ErrorCategory, attempt: int) -> float:
    """Exponential backoff with jitter."""
    base = cat.base_delay_seconds
    exponential = base * (2 ** attempt)
    jitter = random.uniform(0, base / 2)
    return exponential + jitter
