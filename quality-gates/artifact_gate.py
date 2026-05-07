"""
Artifact Gate — declarative schema validator for structured agent outputs.

Marker-based opt-in. Validation only fires when the artifact's frontmatter
declares a class (`class: blog-draft`). Files without the marker pass
silently — never accidentally validate a config file because its path
matched a pattern.

Tri-state verdicts: pass / uncertain / fail.
- pass:       all required checks satisfied
- uncertain:  some soft check failed; suggest re-run, don't block
- fail:       hard check failed; caller should retry or escalate

Cap rules: outputs that hit FAIL_FLOOR (e.g. broken structure) get
capped — downstream consumers must not claim higher confidence than
the gate-level evidence supports.

Usage:

    from artifact_gate import ArtifactClass, validate_artifact, ArtifactGateError

    BLOG_DRAFT = ArtifactClass(
        name="blog-draft",
        required_frontmatter=("title", "slug", "category", "publish_date"),
        required_body_headings=("Introduction", "Conclusion"),
        min_word_count=400,
        max_word_count=2000,
        forbidden_phrases=("In conclusion,", "It's worth noting", "Certainly!"),
    )

    verdict = validate_artifact("path/to/draft.md", BLOG_DRAFT)
    if verdict.status == "fail":
        raise ArtifactGateError(verdict)
    elif verdict.status == "uncertain":
        log_warning(verdict)

CLI:

    python3 artifact_gate.py path/to/file.md --class blog-draft
    python3 artifact_gate.py path/to/file.md --class blog-draft --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ArtifactClass:
    """Schema spec for one class of agent output."""
    name: str
    required_frontmatter: tuple[str, ...] = ()
    required_body_headings: tuple[str, ...] = ()
    required_links_with_attr: str = ""        # e.g. 'rel="nofollow"'
    min_word_count: int = 0
    max_word_count: int = 0                   # 0 = no max
    forbidden_phrases: tuple[str, ...] = ()
    soft_phrases: tuple[str, ...] = ()        # downgrades to uncertain, not fail


@dataclass
class Verdict:
    status: str                               # "pass" | "uncertain" | "fail"
    issues: list[dict] = field(default_factory=list)
    score: float = 1.0                        # 0..1 confidence
    artifact_path: str = ""
    class_name: str = ""


class ArtifactGateError(Exception):
    """Raised by callers that want hard-fail semantics."""


FAIL_FLOOR = 0.3                              # below this → always fail


# ── Frontmatter parsing ────────────────────────────────────────────────────

FRONTMATTER_BOUNDARY = re.compile(r"^---\s*$", re.MULTILINE)
FRONTMATTER_KV = re.compile(r"^(?P<key>[A-Za-z0-9_\-]+):\s*(?P<value>.*)$")


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Return (frontmatter_dict, body_text). If no frontmatter, dict is empty."""
    if not text.startswith("---"):
        return {}, text
    parts = FRONTMATTER_BOUNDARY.split(text, maxsplit=2)
    if len(parts) < 3:
        return {}, text
    fm_text, body = parts[1], parts[2]
    fm: dict[str, Any] = {}
    for line in fm_text.splitlines():
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue
        m = FRONTMATTER_KV.match(line)
        if m:
            key = m.group("key").strip()
            value = m.group("value").strip().strip('"').strip("'")
            fm[key] = value
    return fm, body.lstrip("\n")


# ── Validators ─────────────────────────────────────────────────────────────

def _check_frontmatter(fm: dict, required: tuple[str, ...]) -> list[dict]:
    issues = []
    for key in required:
        if key not in fm or not str(fm.get(key, "")).strip():
            issues.append({"severity": "fail", "code": "missing_frontmatter",
                           "field": key, "msg": f"Required frontmatter field '{key}' missing or empty"})
    return issues


def _check_body_headings(body: str, required: tuple[str, ...]) -> list[dict]:
    headings = re.findall(r"^#{1,6}\s+(.+?)\s*$", body, flags=re.MULTILINE)
    headings_norm = {h.strip().lower() for h in headings}
    issues = []
    for h in required:
        if h.lower() not in headings_norm:
            issues.append({"severity": "fail", "code": "missing_heading",
                           "field": h, "msg": f"Required heading '{h}' not found in body"})
    return issues


def _check_word_count(body: str, lo: int, hi: int) -> list[dict]:
    words = len(re.findall(r"\b\w+\b", body))
    issues = []
    if lo and words < lo:
        issues.append({"severity": "fail", "code": "below_min_words",
                       "msg": f"Body has {words} words; minimum is {lo}"})
    if hi and words > hi:
        issues.append({"severity": "uncertain", "code": "above_max_words",
                       "msg": f"Body has {words} words; max is {hi}"})
    return issues


def _check_phrases(body: str, forbidden: tuple[str, ...], soft: tuple[str, ...]) -> list[dict]:
    issues = []
    for p in forbidden:
        if p.lower() in body.lower():
            issues.append({"severity": "fail", "code": "forbidden_phrase",
                           "field": p, "msg": f"Forbidden phrase present: '{p}'"})
    for p in soft:
        if p.lower() in body.lower():
            issues.append({"severity": "uncertain", "code": "soft_phrase",
                           "field": p, "msg": f"Soft-discouraged phrase: '{p}'"})
    return issues


def _check_links_with_attr(body: str, attr: str) -> list[dict]:
    if not attr:
        return []
    # Look for any anchor; require at least one to carry the attr.
    anchors = re.findall(r"<a[^>]*>", body, flags=re.IGNORECASE)
    if not anchors:
        return [{"severity": "uncertain", "code": "no_links",
                 "msg": "No HTML anchors found; cannot verify link attribute"}]
    if not any(attr.lower() in a.lower() for a in anchors):
        return [{"severity": "fail", "code": "missing_link_attr",
                 "msg": f"No anchor carries required attribute: {attr}"}]
    return []


# ── Public API ─────────────────────────────────────────────────────────────

def validate_artifact(path: str | Path, klass: ArtifactClass) -> Verdict:
    """Validate one artifact file against a class spec. Returns a Verdict."""
    p = Path(path)
    if not p.exists():
        return Verdict(status="fail",
                       issues=[{"severity": "fail", "code": "file_not_found", "msg": str(p)}],
                       score=0.0, artifact_path=str(p), class_name=klass.name)

    text = p.read_text(encoding="utf-8", errors="replace")
    fm, body = parse_frontmatter(text)

    # Marker-based opt-in: file must declare its class
    declared = str(fm.get("class", "")).strip()
    if declared and declared != klass.name:
        return Verdict(status="fail",
                       issues=[{"severity": "fail", "code": "class_mismatch",
                                "msg": f"File declares class={declared!r}, validator expects {klass.name!r}"}],
                       score=0.0, artifact_path=str(p), class_name=klass.name)
    if not declared:
        return Verdict(status="uncertain",
                       issues=[{"severity": "uncertain", "code": "class_unmarked",
                                "msg": f"File has no `class:` frontmatter; cannot enforce {klass.name}"}],
                       score=0.5, artifact_path=str(p), class_name=klass.name)

    issues: list[dict] = []
    issues += _check_frontmatter(fm, klass.required_frontmatter)
    issues += _check_body_headings(body, klass.required_body_headings)
    issues += _check_word_count(body, klass.min_word_count, klass.max_word_count)
    issues += _check_phrases(body, klass.forbidden_phrases, klass.soft_phrases)
    issues += _check_links_with_attr(body, klass.required_links_with_attr)

    fail_count = sum(1 for i in issues if i["severity"] == "fail")
    soft_count = sum(1 for i in issues if i["severity"] == "uncertain")

    if fail_count == 0 and soft_count == 0:
        status, score = "pass", 1.0
    elif fail_count == 0:
        status = "uncertain"
        score = max(FAIL_FLOOR + 0.1, 1.0 - 0.1 * soft_count)
    else:
        status = "fail"
        score = max(0.0, FAIL_FLOOR - 0.1 * fail_count)

    return Verdict(status=status, issues=issues, score=round(score, 2),
                   artifact_path=str(p), class_name=klass.name)


# Example registered classes — extend in a project-specific registry.
REGISTERED_CLASSES: dict[str, ArtifactClass] = {
    "blog-draft": ArtifactClass(
        name="blog-draft",
        required_frontmatter=("title", "slug", "category"),
        required_body_headings=("Introduction",),
        min_word_count=400,
        max_word_count=2500,
        forbidden_phrases=("In conclusion,", "Certainly!", "As an AI"),
    ),
    "intel-report": ArtifactClass(
        name="intel-report",
        required_frontmatter=("date", "sources"),
        required_body_headings=("Findings", "Sources"),
        min_word_count=200,
        forbidden_phrases=("As an AI",),
    ),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path")
    parser.add_argument("--class", dest="class_name", required=True,
                        help="Registered class name (e.g. blog-draft)")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of human text")
    args = parser.parse_args()

    klass = REGISTERED_CLASSES.get(args.class_name)
    if not klass:
        print(f"Unknown class: {args.class_name}. Registered: {list(REGISTERED_CLASSES)}", file=sys.stderr)
        return 2

    verdict = validate_artifact(args.path, klass)
    if args.json:
        print(json.dumps(asdict(verdict), indent=2))
    else:
        print(f"[{verdict.status.upper()}] {verdict.artifact_path} (score={verdict.score})")
        for issue in verdict.issues:
            print(f"  [{issue['severity']}] {issue.get('code','?')}: {issue.get('msg','')}")
    return 0 if verdict.status != "fail" else 1


if __name__ == "__main__":
    raise SystemExit(main())
