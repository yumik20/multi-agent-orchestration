"""
LLM error classifier — categorize an exception into one of five
outcomes that drive deterministic retry decisions.

Without classification, retry loops degrade into "try 3 times, sleep 2s
between" — which retries auth errors (waste), retries model errors
(waste), and gives up on rate-limit errors that should retry longer.

The five categories:

- network:   transient connectivity (urlopen URLError, socket reset,
             DNS, generic timeout). Retry up to 3× with 2s base + jitter.
- timeout:   read timeout on an active HTTP connection. Same as network.
- rate_limit: HTTP 429, or provider-specific quota messages. Retry 2×
             with 5s base + jitter; longer than network because the
             cooldown is what's actually needed.
- auth:      HTTP 401 / 403, missing credential, malformed key. Fail
             fast — retry never helps without operator intervention.
- model:     HTTP 400 with model-side reason (context-window overflow,
             content-filter, prompt-too-long), HTTP 500 with the same.
             Fail fast — retry-without-edit produces the same failure.
- parse:     200 OK with malformed body (truncated JSON, schema
             mismatch). Marked non-retryable here because a single
             retry won't change the response shape — the caller
             needs to handle this (e.g. switch to a stricter response
             schema, fall back to keyword filtering, or surface the
             malformed payload to the operator).

Used by retry_with_backoff (this folder) to make the retry decision
deterministic instead of "try a few times and pray."
"""
from __future__ import annotations

import socket
import urllib.error
from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorCategory:
    type: str
    retryable: bool
    max_retries: int
    base_delay_seconds: float


CATEGORIES = {
    "network":    ErrorCategory("network", retryable=True,  max_retries=3, base_delay_seconds=2.0),
    "timeout":    ErrorCategory("timeout", retryable=True,  max_retries=3, base_delay_seconds=2.0),
    "rate_limit": ErrorCategory("rate_limit", retryable=True, max_retries=2, base_delay_seconds=5.0),
    "auth":       ErrorCategory("auth", retryable=False, max_retries=0, base_delay_seconds=0.0),
    "model":      ErrorCategory("model", retryable=False, max_retries=0, base_delay_seconds=0.0),
    "parse":      ErrorCategory("parse", retryable=False, max_retries=0, base_delay_seconds=0.0),
    "unknown":    ErrorCategory("unknown", retryable=True, max_retries=1, base_delay_seconds=2.0),
}


# Substring matchers on exception messages. Order matters: more
# specific matches come first.
_MODEL_HINTS = (
    "context_length",
    "context window",
    "maximum context length",
    "prompt is too long",
    "model_overloaded",
    "content filter",
    "content_policy",
    "invalid model",
)
_AUTH_HINTS = (
    "invalid api key",
    "invalid_api_key",
    "incorrect api key",
    "authentication",
    "permission denied",
    "missing api key",
    "unauthorized",
)
_RATE_LIMIT_HINTS = (
    "rate limit",
    "rate_limit",
    "too many requests",
    "quota",
    "ratelimit",
)


def classify(exc: BaseException) -> ErrorCategory:
    """Map an exception into one of the categories above.

    The classification looks at the exception type first (HTTPError
    status codes are the strongest signal), then falls through to
    substring matches on the message for cases where the exception
    type is generic (urllib.error.URLError wraps both DNS and timeouts;
    HTTPError carries the real signal in its code).
    """
    msg = str(exc).lower()

    if isinstance(exc, urllib.error.HTTPError):
        code = exc.code
        if code == 401 or code == 403:
            return CATEGORIES["auth"]
        if code == 429:
            return CATEGORIES["rate_limit"]
        if code == 400 and any(h in msg for h in _MODEL_HINTS):
            return CATEGORIES["model"]
        if code in (500, 502, 503, 504):
            # 5xx that mention model-side issues are model errors;
            # everything else is treated as network.
            if any(h in msg for h in _MODEL_HINTS):
                return CATEGORIES["model"]
            return CATEGORIES["network"]
        if code == 408:
            return CATEGORIES["timeout"]
        if 400 <= code < 500:
            # 4xx that didn't match the more-specific cases. Treat as
            # auth/model — both fail-fast — and leave the caller to
            # log and inspect.
            if any(h in msg for h in _AUTH_HINTS):
                return CATEGORIES["auth"]
            return CATEGORIES["model"]

    if isinstance(exc, urllib.error.URLError):
        # URLError wraps connection-level failures. Look at the underlying
        # reason for timeout vs. DNS vs. refused.
        reason = getattr(exc, "reason", None)
        if isinstance(reason, socket.timeout) or "timed out" in msg:
            return CATEGORIES["timeout"]
        return CATEGORIES["network"]

    if isinstance(exc, socket.timeout) or "timed out" in msg:
        return CATEGORIES["timeout"]
    if isinstance(exc, ConnectionError):
        return CATEGORIES["network"]

    # Substring-match fallbacks for libraries that raise plain Exception
    # with the real signal in the message (some HTTP clients do this).
    if any(h in msg for h in _RATE_LIMIT_HINTS):
        return CATEGORIES["rate_limit"]
    if any(h in msg for h in _AUTH_HINTS):
        return CATEGORIES["auth"]
    if any(h in msg for h in _MODEL_HINTS):
        return CATEGORIES["model"]
    if "json" in msg and ("decode" in msg or "parse" in msg):
        return CATEGORIES["parse"]

    return CATEGORIES["unknown"]
