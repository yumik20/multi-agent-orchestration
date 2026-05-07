"""Tests for the URL/date validators in quality-gates/output_contract.py.

The output contract is the cheapest gate in the qualify pipeline — it
runs before dedup and the LLM. False-passes leak fabricated URLs into
the dedup table; false-fails drop real signal. Tests pin both ends.
"""
from output_contract import (
    is_url_with_path,
    is_status_url,
    is_post_url,
    is_article_url,
    is_thread_url,
    is_verified_url,
    is_verified_date,
    drop_unverified,
)


# ── is_url_with_path: generic any-path-after-domain matcher ────────────

class TestUrlWithPath:
    def test_accepts_path_with_segment(self):
        assert is_url_with_path("https://example.com/a/b/c")

    def test_rejects_bare_homepage(self):
        assert not is_url_with_path("https://example.com")
        assert not is_url_with_path("https://example.com/")

    def test_rejects_empty(self):
        assert not is_url_with_path("")

    def test_rejects_non_http_scheme(self):
        assert not is_url_with_path("ftp://example.com/x")
        assert not is_url_with_path("javascript:alert(1)")


# ── is_status_url: /<handle>/status/<numeric-id> ───────────────────────

class TestStatusUrl:
    def test_accepts_canonical_status(self):
        assert is_status_url("https://example.com/alice/status/1234567890123456789")

    def test_rejects_too_few_digits(self):
        # Real status IDs are 15-20 digits; reject obvious fabrications.
        assert not is_status_url("https://example.com/alice/status/12345")

    def test_rejects_non_numeric_id(self):
        assert not is_status_url("https://example.com/alice/status/abcdef")

    def test_rejects_missing_handle(self):
        assert not is_status_url("https://example.com/status/1234567890123456789")


# ── is_post_url: /posts/<slug> ─────────────────────────────────────────

class TestPostUrl:
    def test_accepts_post_slug(self):
        assert is_post_url("https://example.com/posts/abc-def-123")

    def test_rejects_bare_homepage(self):
        assert not is_post_url("https://example.com")

    def test_rejects_other_paths(self):
        assert not is_post_url("https://example.com/articles/abc")


# ── is_article_url: /p/<slug> or /<year>/<month>/<slug> ────────────────

class TestArticleUrl:
    def test_accepts_p_slug(self):
        assert is_article_url("https://blog.example.com/p/my-article")

    def test_accepts_dated_path(self):
        assert is_article_url("https://blog.example.com/2026/05/my-article")

    def test_rejects_bare_p(self):
        assert not is_article_url("https://blog.example.com/p/")


# ── is_thread_url: /item?id=<num> ──────────────────────────────────────

class TestThreadUrl:
    def test_accepts_item_id(self):
        assert is_thread_url("https://example.com/item?id=123456")

    def test_rejects_missing_id(self):
        assert not is_thread_url("https://example.com/item?id=")

    def test_rejects_non_numeric_id(self):
        assert not is_thread_url("https://example.com/item?id=abc")


# ── is_verified_url: dispatches to validator or generic ────────────────

class TestVerifiedUrl:
    def test_default_uses_generic(self):
        assert is_verified_url("https://example.com/path/x")
        assert not is_verified_url("https://example.com")

    def test_with_validator(self):
        assert is_verified_url(
            "https://example.com/posts/abc",
            validator=is_post_url,
        )
        assert not is_verified_url(
            "https://example.com/x",
            validator=is_post_url,
        )

    def test_rejects_non_string(self):
        assert not is_verified_url(None)
        assert not is_verified_url(123)
        assert not is_verified_url("")


# ── is_verified_date: ISO + prose ──────────────────────────────────────

class TestVerifiedDate:
    def test_iso_date(self):
        assert is_verified_date("2026-05-07")

    def test_iso_datetime(self):
        assert is_verified_date("2026-05-07T14:30:00")

    def test_prose_date(self):
        assert is_verified_date("April 21, 2026")
        assert is_verified_date("January 1 2026")

    def test_rejects_garbage(self):
        assert not is_verified_date("not a date")
        assert not is_verified_date("99/99/9999")
        assert not is_verified_date("")


# ── drop_unverified: partition rows + tag drop reason ──────────────────

class TestDropUnverified:
    def test_partitions_correctly(self):
        rows = [
            {"url": "https://example.com/a/b"},
            {"url": "https://example.com"},          # bare homepage → drop
            {"url": "ftp://example.com/x"},          # wrong scheme → drop
            {"url": "https://example.com/c/d/e"},
        ]
        kept, dropped = drop_unverified(rows, url_field="url")
        assert len(kept) == 2
        assert len(dropped) == 2
        assert all("url_invalid" == d["_drop_reason"] for d in dropped)

    def test_uses_validator_when_given(self):
        rows = [
            {"url": "https://example.com/posts/abc"},   # passes is_post_url
            {"url": "https://example.com/articles/xyz"},  # fails is_post_url
        ]
        kept, dropped = drop_unverified(
            rows, url_field="url", url_validator=is_post_url
        )
        assert len(kept) == 1
        assert kept[0]["url"].endswith("/posts/abc")

    def test_date_field_optional(self):
        rows = [
            {"url": "https://example.com/x", "date": "2026-05-07"},
            {"url": "https://example.com/y", "date": "garbage"},
        ]
        kept, dropped = drop_unverified(rows, url_field="url", date_field="date")
        assert len(kept) == 1
        assert dropped[0]["_drop_reason"] == "date_invalid"
