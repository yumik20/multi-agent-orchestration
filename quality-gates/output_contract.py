"""
Output contract — anti-fabrication enforcer.

Per-source-type URL-shape regex applied before the dedup cache and the
LLM relevance qualifier. Drops fabricated `https://example.com/post/abc`
URLs in microseconds, before they enter the 30-day dedup window or burn
Haiku tokens.

Inspired by the pattern of dropping unverified outputs at the boundary,
not after the fact:

    Findings without a verified date and article URL are dropped —
    no fabricated dates, no homepage links.

Generic source-types: post (numeric id), thread (forum-style), article
(title-slug), status (timestamp-id). Specific scanners pass an explicit
validator; everything else falls back to is_url_with_path.

Usage:

    from output_contract import drop_unverified, is_post_url

    rows = [...]  # raw rows from extraction
    kept, dropped = drop_unverified(
        rows,
        url_field="post_url",
        date_field="post_date",
        url_validator=is_post_url,
    )
    write_csv(kept)
    log_dropped(dropped)
"""

from __future__ import annotations

import re
from typing import Callable

# ── URL validators ─────────────────────────────────────────────────────────

# Generic — must have a path of at least one segment, not a bare homepage.
URL_WITH_PATH_RE = re.compile(
    r"^https?://[A-Za-z0-9.\-]+\.[A-Za-z]{2,}/[A-Za-z0-9/_\-]+(?:[/?#].*)?$"
)

# Status-style: /<handle>/status/<numeric-id>. Numeric id length 15-20 digits.
STATUS_URL_RE = re.compile(
    r"^https?://[A-Za-z0-9.\-]+\.[A-Za-z]{2,}/[A-Za-z0-9_]+/status/\d{15,20}(?:[/?#].*)?$"
)

# Post-style: /posts/<id> — generic shape for professional networks.
POST_URL_RE = re.compile(
    r"^https?://[A-Za-z0-9.\-]+\.[A-Za-z]{2,}/posts/[\w\-:%]+(?:[/?#].*)?$"
)

# Article-style: /p/<slug> or /<year>/<month>/<slug>/.
ARTICLE_URL_RE = re.compile(
    r"^https?://[A-Za-z0-9.\-]+\.[A-Za-z]{2,}/p/[A-Za-z0-9\-]+(?:[/?#].*)?$"
    r"|^https?://[A-Za-z0-9.\-]+\.[A-Za-z]{2,}/\d{4}/\d{2}/[A-Za-z0-9\-]+(?:/[A-Za-z0-9\-]*)*/?(?:[?#].*)?$"
)

# Thread-style: /item?id=<num> — generic forum-with-numeric-thread-id pattern.
THREAD_URL_RE = re.compile(
    r"^https?://[A-Za-z0-9.\-]+\.[A-Za-z]{2,}/item\?id=\d+(?:&.*)?$"
)

# ── Date validators ────────────────────────────────────────────────────────

ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2})?)?")
PROSE_DATE_RE = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b"
)


# ── Public API ─────────────────────────────────────────────────────────────

def is_url_with_path(url: str) -> bool:
    return bool(URL_WITH_PATH_RE.match(url or ""))


def is_status_url(url: str) -> bool:
    return bool(STATUS_URL_RE.match(url or ""))


def is_post_url(url: str) -> bool:
    return bool(POST_URL_RE.match(url or ""))


def is_article_url(url: str) -> bool:
    return bool(ARTICLE_URL_RE.match(url or ""))


def is_thread_url(url: str) -> bool:
    return bool(THREAD_URL_RE.match(url or ""))


def is_verified_url(url: str, validator: Callable[[str], bool] | None = None) -> bool:
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    if validator is not None:
        return bool(validator(url))
    return is_url_with_path(url)


def is_verified_date(value: str) -> bool:
    if not value or not isinstance(value, str):
        return False
    s = value.strip()
    return bool(ISO_DATE_RE.match(s) or PROSE_DATE_RE.search(s))


def drop_unverified(
    rows: list[dict],
    url_field: str = "url",
    date_field: str | None = None,
    url_validator: Callable[[str], bool] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Partition rows into (kept, dropped). A row is dropped if its URL
    doesn't pass `url_validator` (or `is_url_with_path` if none given)
    or if `date_field` is provided but the row's date is unverified."""
    kept, dropped = [], []
    for row in rows:
        url = str(row.get(url_field, "")).strip()
        if not is_verified_url(url, url_validator):
            dropped.append({**row, "_drop_reason": "url_invalid"})
            continue
        if date_field is not None:
            if not is_verified_date(str(row.get(date_field, ""))):
                dropped.append({**row, "_drop_reason": "date_invalid"})
                continue
        kept.append(row)
    return kept, dropped
