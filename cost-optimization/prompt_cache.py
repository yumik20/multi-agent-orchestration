"""
Anthropic prompt-cache wiring.

The cached portion gets ~90% input-token discount on subsequent calls
that send the same system prefix within 5 minutes. The right place to
put cached content is anything that's stable across calls in a batch:

- The thesis / scoring rubric you qualify against
- Output schema spec
- Few-shot examples
- A reference list the model uses for context

Forward-compatible: silently no-ops when the cached prefix is below
the model's minimum cacheable size:
- Haiku 4.5: ≥ 2048 tokens
- Sonnet:    ≥ 1024 tokens

Below that, cache_control is accepted by the API but no caching happens.
The wire format stays correct so the cache activates automatically as
you grow your system context.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from typing import Any


def call_anthropic_cached(
    *,
    api_key: str,
    model: str,
    user_prompt: str,
    system: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.0,
    log_cache_stats: bool = True,
) -> dict[str, Any]:
    """Call the Anthropic Messages API with optional cached system prefix.

    Returns the full response dict so callers can inspect usage. Logs
    cache_creation_input_tokens / cache_read_input_tokens to stderr
    when present so you can see when the cache is actually firing.
    """
    body: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    if system:
        # System as a list of blocks lets us attach cache_control.
        # `ephemeral` = 5-minute cache TTL (the only currently supported type).
        body["system"] = [{
            "type": "text",
            "text": system,
            "cache_control": {"type": "ephemeral"},
        }]

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    if log_cache_stats:
        usage = result.get("usage") or {}
        creation = usage.get("cache_creation_input_tokens", 0)
        read = usage.get("cache_read_input_tokens", 0)
        if creation or read:
            sys.stderr.write(
                f"  prompt-cache: created={creation} read={read} "
                f"input={usage.get('input_tokens', 0)} "
                f"output={usage.get('output_tokens', 0)}\n"
            )

    return result


def extract_text(response: dict[str, Any]) -> str:
    """Pull the assistant's text out of a Messages API response."""
    return "".join(b.get("text", "") for b in response.get("content", []))


# Example: a qualify call that puts the stable thesis + rubric in the
# cached system block, leaving only the changing candidates in the
# user message.

THESIS_AND_RUBRIC_TEMPLATE = """\
You qualify candidate posts/articles against a thesis. Be inclusive:
include items with reasonable thesis overlap. We want 5-10 signals per
batch, not 1. Output raw JSON only (no code blocks, no preamble).

THESIS:
{thesis}

RUBRIC:
{rubric}

OUTPUT FORMAT:
A JSON array of integer indices, e.g. [0, 3, 7]. Only the indices of
items that pass the thesis. No prose, no code fences."""


def qualify_with_cached_thesis(
    api_key: str,
    candidates: list[dict],
    text_field: str,
    thesis: str,
    rubric: str = "",
    model: str = "claude-haiku-4-5-20251001",
) -> set[int]:
    """Qualify a batch of candidates with the thesis cached. Returns the
    set of qualified indices.

    The thesis + rubric is stable across batches → goes in the cached
    system block. The numbered candidates change every call → user msg.
    """
    if not candidates:
        return set()

    system_prompt = THESIS_AND_RUBRIC_TEMPLATE.format(thesis=thesis, rubric=rubric)
    numbered = "\n".join(
        f"[{i}] {str(c.get(text_field, '')).strip()[:500]}"
        for i, c in enumerate(candidates)
    )
    user_prompt = (
        f"Below are {len(candidates)} numbered candidates. Return the "
        f"JSON array of indices that pass the thesis.\n\n{numbered}"
    )

    response = call_anthropic_cached(
        api_key=api_key,
        model=model,
        user_prompt=user_prompt,
        system=system_prompt,
        max_tokens=512,
    )
    text = extract_text(response)

    # Parse robustly — the response should be a JSON array of ints.
    arr = _extract_int_array(text, max_value=len(candidates))
    return set(arr) if arr is not None else set(range(len(candidates)))


def _extract_int_array(text: str, max_value: int) -> list[int] | None:
    """Robust extractor for a JSON array of integers."""
    if not text:
        return None
    start = 0
    while True:
        i = text.find("[", start)
        if i < 0:
            return None
        end = text.rfind("]")
        if end <= i:
            return None
        try:
            parsed = json.loads(text[i:end + 1])
            if isinstance(parsed, list) and all(isinstance(x, int) for x in parsed):
                return [x for x in parsed if 0 <= x < max_value]
        except json.JSONDecodeError:
            pass
        start = i + 1
