# Error Handling: Classifier + Retry Helper

Two files that turn the typical "try 3 times with a fixed sleep" retry into something deterministic.

The pattern is older than this repo — it ships in production load balancers, AWS SDKs, and most serious HTTP clients. But you don't see it often in agent codebases, where retries are usually written ad-hoc per call site.

## The shape

```
def _do_call():
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)

result = retry_with_backoff(_do_call, log_prefix="qualify-batch: ")
```

The wrapped function gets retried per-category:

| Category | Retryable? | Max retries | Base delay |
|---|---|---|---|
| network (DNS, refused, generic 5xx) | yes | 3 | 2s |
| timeout (408, socket timeout, "timed out") | yes | 3 | 2s |
| rate_limit (429, "rate limit", "quota") | yes | 2 | 5s |
| auth (401, 403, "invalid api key") | **no** | 0 | — |
| model (400 with context-window / content-filter) | **no** | 0 | — |
| parse (200 with malformed body) | **no** | 0 | — |
| unknown | yes | 1 | 2s |

Backoff is `base * 2^attempt + jitter`. Jitter prevents thundering-herd when multiple skills hit the same rate-limit window simultaneously.

## Why fail-fast on auth + model

A typical "retry 3 times" loop on an auth error wastes ~6 seconds and three API calls before giving up — and the 4th attempt would have failed too. Same for context-window-overflow: the prompt isn't going to fit on retry. The cost of a fast fail is one stack trace; the cost of a slow fail is six wasted requests AND the same stack trace.

The classifier looks at:
1. Exception type (HTTPError → status code is gold-standard signal)
2. Status code mapping (401/403 → auth, 429 → rate_limit, 400 → check message for model hints)
3. Substring fallback on the exception message (some libraries raise plain Exception with the real signal in the text)

## Why this is in the public sample

Most of the engineering depth in a production AI system isn't in the prompts — it's in the layers between the prompt and the user. Retries, dedup, output validation, fallbacks. This file shows that depth without leaking anything domain-specific.
