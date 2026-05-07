"""Tests for error-handling/error_classifier.py + retry_with_backoff.py."""
import urllib.error
import socket

from error_classifier import classify, CATEGORIES
from retry_with_backoff import retry_with_backoff


class TestClassify:
    def test_http_401_is_auth(self):
        exc = urllib.error.HTTPError("u", 401, "Unauthorized", {}, None)
        assert classify(exc).type == "auth"
        assert not classify(exc).retryable

    def test_http_403_is_auth(self):
        exc = urllib.error.HTTPError("u", 403, "Forbidden", {}, None)
        assert classify(exc).type == "auth"

    def test_http_429_is_rate_limit(self):
        exc = urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None)
        cat = classify(exc)
        assert cat.type == "rate_limit"
        assert cat.retryable
        assert cat.max_retries == 2

    def test_http_500_is_network(self):
        exc = urllib.error.HTTPError("u", 503, "Service Unavailable", {}, None)
        cat = classify(exc)
        assert cat.type == "network"
        assert cat.retryable

    def test_http_408_is_timeout(self):
        exc = urllib.error.HTTPError("u", 408, "Request Timeout", {}, None)
        assert classify(exc).type == "timeout"

    def test_socket_timeout(self):
        assert classify(socket.timeout("read timed out")).type == "timeout"

    def test_connection_error_is_network(self):
        assert classify(ConnectionError("refused")).type == "network"

    def test_substring_rate_limit(self):
        assert classify(Exception("Rate limit exceeded")).type == "rate_limit"

    def test_substring_auth(self):
        assert classify(Exception("Invalid API key")).type == "auth"

    def test_unknown_default(self):
        cat = classify(Exception("something weird"))
        assert cat.type == "unknown"
        assert cat.max_retries == 1


class TestRetryWithBackoff:
    def test_returns_on_success(self):
        calls = []
        def fn():
            calls.append(1)
            return "ok"
        assert retry_with_backoff(fn, sleep=lambda d: None) == "ok"
        assert len(calls) == 1

    def test_retries_on_transient(self):
        calls = []
        def fn():
            calls.append(1)
            if len(calls) < 3:
                raise ConnectionError("refused")
            return "ok"
        assert retry_with_backoff(fn, sleep=lambda d: None) == "ok"
        assert len(calls) == 3

    def test_fails_fast_on_auth(self):
        calls = []
        def fn():
            calls.append(1)
            raise urllib.error.HTTPError("u", 401, "u", {}, None)
        try:
            retry_with_backoff(fn, sleep=lambda d: None)
            assert False, "should have raised"
        except urllib.error.HTTPError:
            pass
        assert len(calls) == 1   # no retries for auth

    def test_exhausts_then_raises(self):
        calls = []
        def fn():
            calls.append(1)
            raise ConnectionError("always")
        try:
            retry_with_backoff(fn, sleep=lambda d: None)
            assert False, "should have raised"
        except ConnectionError:
            pass
        # network category: max_retries=3, so 1 initial + 3 retries = 4 calls
        assert len(calls) == 4
