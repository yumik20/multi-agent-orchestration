"""
Cross-source qualification pipeline.

Reads the per-source CSV outputs from the scanner skills, normalizes
their column schemas into one shape, runs a single batched LLM call to
qualify the unified set against the project's domain thesis, and
writes a merged qualified-output CSV.

Each source has its own column convention (some use `post_url`/`post_summary`,
others `article_url`/`title`/`summary`). This pipeline is the seam.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

# ─── Source registry ─────────────────────────────────────────────────────
# Generic — concrete scanner names + state-file paths are project-specific.

WORKSPACE_ROOT = Path(os.environ.get("WORKSPACE_ROOT", Path.home() / "workspace"))
DATA_ROOT = WORKSPACE_ROOT / "data"

SOURCE_STATE_PATHS = {
    "source-a": DATA_ROOT / "source_a_scan_state.json",
    "source-b": DATA_ROOT / "source_b_scan_state.json",
    "source-c": DATA_ROOT / "source_c_scan_state.json",
    "source-d": DATA_ROOT / "source_d_scan_state.json",
}


def _parse_scan_state(path: Path) -> dict:
    """Read a scan-state JSON written by a scanner skill."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"  qa pipeline: malformed scan state {path}: {exc}\n")
        return {}


# ─── Unification ─────────────────────────────────────────────────────────

def _collect_rows_for_qa() -> list[dict]:
    """Load rows from each source's final CSV into a unified shape for
    the qualification pass + email."""
    unified: list[dict] = []
    for source, state_path in SOURCE_STATE_PATHS.items():
        state = _parse_scan_state(state_path)
        csv_path = state.get("csvPath") or ""
        if not csv_path or not Path(csv_path).exists():
            continue
        try:
            with Path(csv_path).open("r", encoding="utf-8", newline="") as fh:
                for row in csv.DictReader(fh):
                    # Normalize across schemas. Some sources emit
                    # post_url/post_summary; others use article_url/title.
                    url = (row.get("post_url") or row.get("article_url") or "").strip()
                    if not url:
                        continue
                    title_or_summary = (
                        row.get("post_summary")
                        or row.get("title")
                        or row.get("summary")
                        or ""
                    ).strip()
                    author = (row.get("person") or row.get("author") or "").strip()
                    context_bits = [
                        row.get("newsletter", ""),
                        row.get("who_they_are", ""),
                        row.get("summary", ""),
                    ]
                    context = " · ".join(b for b in context_bits if b).strip()
                    unified.append({
                        "source": source,
                        "url": url,
                        "author": author,
                        "text": title_or_summary,
                        "context": context[:400],
                        "raw": dict(row),
                    })
        except (OSError, ValueError) as exc:
            # CSV read failure for one source — skip + continue with the
            # others rather than aborting the whole qualification pass.
            sys.stderr.write(f"  qa pipeline: failed to read {csv_path}: {exc}\n")
    return unified


# ─── Qualification (single batched call, deterministic fallback) ────────

QA_MODEL = "gemini-2.5-flash"
DOMAIN_THEMES_PATH = WORKSPACE_ROOT / "config" / "domain_themes.md"


def _load_domain_themes() -> str:
    """Themes are stored as markdown so editing the file moves the
    qualifier without a code change. Falls back to an inline default
    if the file is absent."""
    if DOMAIN_THEMES_PATH.exists():
        return DOMAIN_THEMES_PATH.read_text(encoding="utf-8")
    return (
        "DOMAIN THEMES (edit config/domain_themes.md to override):\n"
        "- Items that materially change how the domain operates\n"
        "- Adoption stories with specifics (numbers, named users, costs)\n"
        "- New tools or platform shifts with named users\n"
    )


def _load_qa_api_key() -> str:
    """API key is read from a project env file. Never inline."""
    env_path = Path.home() / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("QA_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return os.environ.get("QA_API_KEY", "")


def _qualify_rows_with_llm(rows: list[dict]) -> list[dict]:
    """Call the qualifier model once with the full batch. Annotates each
    row with `qualification_status` and `qualification_reason`.

    Deterministic keyword-based fallback if the API call fails — the
    pipeline never blocks on the qualifier being available.
    """
    if not rows:
        return []

    api_key = _load_qa_api_key()
    if not api_key:
        sys.stderr.write("  qa pipeline: QA_API_KEY missing — using deterministic fallback\n")
        return _qualify_with_keyword_fallback(rows)

    themes = _load_domain_themes()
    numbered = "\n".join(
        f"[{i}] source={r['source']} :: {r['text'][:300]} :: {r.get('context','')[:200]}"
        for i, r in enumerate(rows)
    )

    prompt = (
        f"{themes}\n\n"
        f"For each of the {len(rows)} numbered items below, decide if it's "
        f"ON-THESIS for the domain themes. Be inclusive: if the item has "
        f"reasonable overlap, KEEP it.\n\n"
        f"{numbered}\n\n"
        f"Return a JSON object exactly like:\n"
        f'{{"decisions": [{{"id": 0, "keep": true, "reason": "..."}}, ...]}}'
    )

    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 4096,
            # thinkingBudget=0 disables reasoning tokens on flash-class
            # models so the response stays under maxOutputTokens.
            "thinkingBudget": 0,
        },
    }).encode("utf-8")

    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{QA_MODEL}:generateContent?key={api_key}")
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"})

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            response = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"  qa pipeline: call failed ({exc}) — keyword fallback\n")
        return _qualify_with_keyword_fallback(rows)

    text_out = ""
    try:
        parts = response.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        text_out = " ".join(p.get("text", "") for p in parts)
    except (KeyError, IndexError, TypeError):
        # Malformed response shape; text_out stays empty and the
        # qualifier falls through to the keyword-overlap fallback.
        pass

    decisions = _parse_decisions(text_out)
    if decisions is None:
        sys.stderr.write("  qa pipeline: response unparseable — keyword fallback\n")
        return _qualify_with_keyword_fallback(rows)

    by_id = {d["id"]: d for d in decisions if isinstance(d, dict) and "id" in d}
    out = []
    for i, row in enumerate(rows):
        decision = by_id.get(i, {"keep": True, "reason": "no decision (default keep)"})
        out.append({
            **row,
            "qualification_status": "qualified" if decision.get("keep") else "rejected",
            "qualification_reason": decision.get("reason", ""),
        })
    return out


def _qualify_with_keyword_fallback(rows: list[dict]) -> list[dict]:
    """Loose keyword-overlap qualifier. Used when the LLM is unavailable."""
    themes_text = _load_domain_themes().lower()
    domain_keywords = {w.strip(".,()[]") for w in themes_text.split()
                       if len(w) >= 5 and w.isalpha()}
    out = []
    for row in rows:
        text = (row.get("text", "") + " " + row.get("context", "")).lower()
        words = {w.strip(".,()[]") for w in text.split()}
        overlap = len(domain_keywords & words)
        out.append({
            **row,
            "qualification_status": "qualified" if overlap >= 2 else "rejected",
            "qualification_reason": f"keyword fallback ({overlap} overlap)",
        })
    return out


def _parse_decisions(text: str) -> list[dict] | None:
    """Robust JSON-object extractor: find the first `{` whose contents
    parse cleanly and contain a `decisions` array."""
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


# ─── Pipeline entry point ───────────────────────────────────────────────

def run_qualification(output_csv: Path) -> dict:
    """End-to-end: collect from sources, qualify, write merged CSV."""
    rows = _collect_rows_for_qa()
    if not rows:
        return {"qualified_count": 0, "rejected_count": 0, "csv_path": ""}

    qualified = _qualify_rows_with_llm(rows)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["source", "url", "author", "text",
                  "qualification_status", "qualification_reason"]
    with output_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in qualified:
            writer.writerow({k: row.get(k, "") for k in fieldnames})

    counts = {
        "qualified_count": sum(1 for r in qualified if r["qualification_status"] == "qualified"),
        "rejected_count": sum(1 for r in qualified if r["qualification_status"] == "rejected"),
        "csv_path": str(output_csv),
    }
    sys.stderr.write(
        f"  qa pipeline: {counts['qualified_count']} qualified, "
        f"{counts['rejected_count']} rejected → {output_csv}\n"
    )
    return counts
