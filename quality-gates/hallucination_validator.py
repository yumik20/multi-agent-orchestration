"""
Hallucination Validator — post-hoc LLM judge for agent outputs.

Three supervision levels with rising thresholds. Four issue categories
with STATIC severities the judge can't game. Three verdict statuses:
pass / uncertain / fail. Hard floor 0.3 — below this, always fail.
Judge errors degrade gracefully to "uncertain" so agent work is never
lost when the validator itself fails.

Inputs:
- claims:       facts the agent asserted in its output
- tool_results: the tool outputs (URL fetches, search results, file reads)
                the agent actually had access to

The judge decides which claims are SUPPORTED vs UNSUPPORTED vs CONTRADICTED
by the tool results. The validator combines those classifications with
static severities to produce a numeric score and a tri-state verdict.

Usage:

    from hallucination_validator import (
        SupervisionLevel, validate_claims, ValidationFailedError,
    )

    verdict = validate_claims(
        api_key=api_key,
        claims=[
            "Acme Corp launched Product X on April 30, 2026.",
            "The product achieved 10x speedup over baseline.",
        ],
        tool_results=[
            "https://acme.com/blog/product-x ... announced April 30 2026 ...",
            "https://benchmark.org/2026 ... 8.4x improvement vs baseline ...",
        ],
        level=SupervisionLevel.NORMAL,
    )
    if verdict.status == "fail":
        raise ValidationFailedError(verdict)
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from enum import Enum


# ── Supervision levels ─────────────────────────────────────────────────────

class SupervisionLevel(str, Enum):
    NORMAL = "normal"      # block on score < 0.6
    STRICT = "strict"      # block on score < 0.75
    PARANOID = "paranoid"  # block on score < 0.9, demote any UNSUPPORTED to FAIL


_THRESHOLDS = {
    SupervisionLevel.NORMAL: 0.60,
    SupervisionLevel.STRICT: 0.75,
    SupervisionLevel.PARANOID: 0.90,
}


# ── Issue categories with STATIC severities ───────────────────────────────
# Judge can identify issues but can't decide their severity. Prevents
# "I'm 90% confident this is fine" loophole.

ISSUE_SEVERITY = {
    "unverifiable_claim":          0.40,   # not in tool results, not contradicted
    "weakly_supported":            0.20,   # tool results imply but don't state directly
    "contradicted_by_tool_results": 0.70,  # tool results say the opposite
    "fabricated_source":           0.90,   # claim cites a URL not in tool results
}


FAIL_FLOOR = 0.30


@dataclass
class Issue:
    category: str
    claim: str
    explanation: str
    severity: float = 0.0


@dataclass
class Verdict:
    status: str                              # pass | uncertain | fail
    score: float                             # 0..1
    level: str
    issues: list[Issue] = field(default_factory=list)
    raw_judge_response: str = ""


class ValidationFailedError(Exception):
    """Raised by callers that want hard-fail semantics."""


# ── Judge prompt + call ────────────────────────────────────────────────────

JUDGE_SYSTEM = """You are a fact-checking judge. For each numbered CLAIM,
classify it against the supplied TOOL_RESULTS into one of:

- "supported"                 — directly stated in the tool results
- "weakly_supported"          — implied but not stated in so many words
- "unverifiable_claim"        — neither stated nor contradicted; can't tell
- "contradicted_by_tool_results" — directly contradicted by tool results
- "fabricated_source"         — claim cites a URL that doesn't appear in tool_results

Respond with a JSON array of objects, one per claim:
  [{"i": 0, "category": "supported", "explanation": "..."}, ...]

No prose, no code fences. Be strict — if you're not sure, classify as
unverifiable rather than supported."""


def _call_judge(api_key: str, claims: list[str], tool_results: list[str]) -> str:
    user = (
        f"CLAIMS:\n" + "\n".join(f"[{i}] {c}" for i, c in enumerate(claims)) +
        f"\n\nTOOL_RESULTS:\n" + "\n---\n".join(tool_results) +
        "\n\nReturn JSON array now."
    )
    payload = json.dumps({
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 2048,
        "temperature": 0.0,
        "system": [{"type": "text", "text": JUDGE_SYSTEM,
                    "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": user}],
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    return "".join(b.get("text", "") for b in result.get("content", []))


# ── Public API ─────────────────────────────────────────────────────────────

def validate_claims(
    api_key: str,
    claims: list[str],
    tool_results: list[str],
    level: SupervisionLevel = SupervisionLevel.NORMAL,
) -> Verdict:
    """Classify each claim and produce a tri-state verdict + score.

    Judge errors degrade gracefully to "uncertain" so agent work is
    never lost when the validator itself fails.
    """
    if not claims:
        return Verdict(status="pass", score=1.0, level=level.value)

    try:
        raw = _call_judge(api_key, claims, tool_results)
    except (urllib.error.URLError, json.JSONDecodeError, KeyError) as exc:
        return Verdict(
            status="uncertain", score=0.5, level=level.value,
            issues=[Issue(category="judge_error",
                          claim="(validator failure)",
                          explanation=f"{type(exc).__name__}: {exc}",
                          severity=0.0)],
            raw_judge_response="",
        )

    # Parse the judge's classifications
    classifications = _parse_judge_array(raw, expected_count=len(claims))
    if classifications is None:
        return Verdict(
            status="uncertain", score=0.5, level=level.value,
            issues=[Issue(category="parse_error",
                          claim="(could not parse judge response)",
                          explanation=raw[:300],
                          severity=0.0)],
            raw_judge_response=raw,
        )

    # Build issues from non-supported classifications
    issues: list[Issue] = []
    penalty = 0.0
    for i, cls in enumerate(classifications):
        cat = cls.get("category", "")
        if cat == "supported":
            continue
        sev = ISSUE_SEVERITY.get(cat, 0.0)
        issues.append(Issue(
            category=cat,
            claim=claims[i] if i < len(claims) else "(unknown index)",
            explanation=cls.get("explanation", ""),
            severity=sev,
        ))
        penalty += sev

    # Score = 1 - normalized penalty (capped at FAIL_FLOOR floor)
    score = max(FAIL_FLOOR - 0.05, 1.0 - (penalty / max(len(claims), 1)))
    score = round(score, 3)

    threshold = _THRESHOLDS[level]
    # PARANOID: any unsupported claim is automatic fail
    if level == SupervisionLevel.PARANOID and any(
        i.category in ("unverifiable_claim", "weakly_supported",
                       "contradicted_by_tool_results", "fabricated_source")
        for i in issues
    ):
        status = "fail"
    elif score < FAIL_FLOOR:
        status = "fail"
    elif score < threshold:
        status = "uncertain"
    else:
        status = "pass"

    return Verdict(status=status, score=score, level=level.value,
                   issues=issues, raw_judge_response=raw)


# ── JSON-array parser (same robust strategy used elsewhere) ────────────────

def _parse_judge_array(text: str, expected_count: int) -> list[dict] | None:
    """Try every `[` position; return the first JSON array of dicts found."""
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
        candidate = text[i:end + 1]
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, list) and all(isinstance(x, dict) for x in parsed):
                return parsed
        except json.JSONDecodeError:
            pass
        start = i + 1
