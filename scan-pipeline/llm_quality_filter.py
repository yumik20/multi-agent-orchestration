"""
LLM-based quality filter for collected events / items.

Generic version: given a list of items and a topical filter spec, ask
an LLM to KEEP or REJECT each one with a reason. Returns the kept set
plus a list of rejected items (with reasons) for audit logs.

The filter spec is plain text — keep / reject criteria, plus examples
of named hosts / sponsors / categories that should be auto-kept. The
spec lives outside the code so editing it doesn't require a deploy.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

QA_MODEL = "gemini-2.5-flash"


def quality_filter_items(
    items_by_bucket: dict[str, list[dict]],
    filter_spec: str,
    api_key: str,
    timeout: float = 90.0,
) -> tuple[dict[str, list[dict]], list[dict]]:
    """
    Filter items grouped by bucket (e.g. by date). Drop items the LLM
    rejects, return them separately with reasons.

    Args:
      items_by_bucket: {"2026-05-06": [{name, description, url, ...}, ...]}
      filter_spec:     plain-text criteria. KEEP rules, REJECT rules,
                       sample named entities to auto-keep, etc.
      api_key:         provider API key
      timeout:         seconds

    Returns:
      (kept_by_bucket, rejected_with_reasons)

    Falls back to identity (keep all) on any API failure so the
    pipeline never blocks on the filter being available.
    """
    if not api_key:
        sys.stderr.write("  quality filter: no api_key — passing through\n")
        return items_by_bucket, []

    flat = []
    for bucket, items in items_by_bucket.items():
        for it in items:
            flat.append({
                "bucket": bucket,
                "name": it.get("name", ""),
                "desc": (it.get("description") or "")[:300],
                "url": it.get("url", ""),
            })
    if not flat:
        return items_by_bucket, []

    numbered = "\n".join(
        f"[{i}] {it['name']} ({it['bucket']}) — {it['desc']}"
        for i, it in enumerate(flat)
    )
    prompt = (
        f"You are a quality filter. Apply this spec to each item and "
        f"decide KEEP or REJECT.\n\n"
        f"FILTER SPEC:\n{filter_spec}\n\n"
        f"ITEMS:\n{numbered}\n\n"
        f"Return ONLY a JSON object in this exact format (no prose, "
        f"no markdown fences):\n"
        f'{{"decisions": [{{"id": 0, "keep": true, "reason": "..."}}, ...]}}'
    )

    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 4096,
            "thinkingBudget": 0,
        },
    }).encode("utf-8")
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{QA_MODEL}:generateContent?key={api_key}")
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"})

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            response = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"  quality filter: call failed ({exc}) — passing through\n")
        return items_by_bucket, [{"error": str(exc)}]

    text_out = ""
    try:
        parts = response.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        text_out = " ".join(p.get("text", "") for p in parts)
    except Exception:
        pass

    decisions = _parse_decisions(text_out)
    if decisions is None:
        sys.stderr.write("  quality filter: unparseable — passing through\n")
        return items_by_bucket, [{"error": "unparseable response",
                                  "raw_first_300": text_out[:300]}]

    by_id = {d["id"]: d for d in decisions if isinstance(d, dict) and "id" in d}
    kept_by_bucket: dict[str, list[dict]] = {b: [] for b in items_by_bucket}
    rejected: list[dict] = []
    flat_idx = 0
    for bucket, items in items_by_bucket.items():
        for item in items:
            decision = by_id.get(flat_idx, {"keep": True, "reason": "no decision"})
            if decision.get("keep"):
                kept_by_bucket[bucket].append(item)
            else:
                rejected.append({
                    "bucket": bucket,
                    "item": item,
                    "reason": decision.get("reason", ""),
                })
            flat_idx += 1
    return kept_by_bucket, rejected


def _parse_decisions(text: str) -> list[dict] | None:
    """Robust JSON-object extractor. Mirrors the parser in the qualifier."""
    if not text:
        return None
    start = 0
    while True:
        i = text.find("{", start)
        if i < 0:
            return None
        end = text.rfind("}")
        if end <= i:
            return None
        try:
            obj = json.loads(text[i:end + 1])
            if isinstance(obj, dict) and isinstance(obj.get("decisions"), list):
                return obj["decisions"]
        except json.JSONDecodeError:
            pass
        start = i + 1


# ── Example filter spec (operators edit this in a markdown file) ──────

EXAMPLE_FILTER_SPEC = """\
Apply to a curated calendar of professional / industry events.

KEEP only if the item matches AT LEAST ONE of:
1. Clearly about [domain] / [adjacent domain] / [adjacent domain]
2. Hosted or sponsored by a notable, well-funded company in the space
3. Speaker lineup includes named, identifiable practitioners

REJECT if the item is:
- Generic networking with no clear topical focus
- Wellness, lifestyle, or influencer-only with no domain link
- Hobbyist / non-professional unless host is independently notable
- Off-topic adjacent (entertainment, politics, sports) unless host is notable

When in doubt, REJECT — this filter feeds a curated weekly digest.
"""
