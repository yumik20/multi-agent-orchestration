"""Tests for quality-gates/artifact_gate.py.

Pins the tri-state contract:
- pass / uncertain / fail with appropriate scores
- FAIL_FLOOR floor on score
- class marker required (un-marked → uncertain, not silent pass)
- score reflects severity weighting
"""
from artifact_gate import (
    ArtifactClass,
    validate_artifact,
    parse_frontmatter,
    FAIL_FLOOR,
)


SAMPLE_GOOD = """---
title: My Article
slug: my-article
category: engineering
class: blog-draft
---

# My Article

## Introduction
This is a draft article for testing. It needs at least 400 words to pass
the artifact gate. {} The content here is filler designed to push the
word count above the minimum. {}
"""

# Pad up to ≥400 words by repeating filler.
FILLER = " ".join(["lorem"] * 400)
SAMPLE_GOOD = SAMPLE_GOOD.format(FILLER, FILLER)


SAMPLE_TOO_SHORT = """---
title: Short
slug: short
category: engineering
class: blog-draft
---

# Short

## Introduction
Too short.
"""


SAMPLE_NO_CLASS = """---
title: Unmarked
---

# Unmarked
""" + FILLER


SAMPLE_FORBIDDEN_PHRASE = """---
title: Has Forbidden Phrase
slug: forbidden
category: engineering
class: blog-draft
---

# Has Forbidden Phrase

## Introduction
{}

In conclusion, this is what I wanted to say.
""".format(FILLER)


BLOG_DRAFT = ArtifactClass(
    name="blog-draft",
    required_frontmatter=("title", "slug", "category"),
    required_body_headings=("Introduction",),
    min_word_count=400,
    forbidden_phrases=("In conclusion,", "As an AI"),
)


def _write_and_validate(tmp_path, name, text, klass=BLOG_DRAFT):
    p = tmp_path / name
    p.write_text(text)
    return validate_artifact(p, klass)


class TestFrontmatterParse:
    def test_extracts_kv_pairs(self):
        fm, body = parse_frontmatter(SAMPLE_GOOD)
        assert fm["title"] == "My Article"
        assert fm["class"] == "blog-draft"
        assert "Introduction" in body

    def test_no_frontmatter_returns_empty(self):
        fm, body = parse_frontmatter("# Just a body\nno fm")
        assert fm == {}
        assert "body" in body


class TestValidatorVerdicts:
    def test_pass_on_good_input(self, tmp_path):
        v = _write_and_validate(tmp_path, "good.md", SAMPLE_GOOD)
        assert v.status == "pass", f"expected pass, got {v.issues}"
        assert v.score == 1.0

    def test_fail_on_too_short(self, tmp_path):
        v = _write_and_validate(tmp_path, "short.md", SAMPLE_TOO_SHORT)
        assert v.status == "fail"
        assert any(i["code"] == "below_min_words" for i in v.issues)

    def test_uncertain_on_unmarked_class(self, tmp_path):
        v = _write_and_validate(tmp_path, "unmarked.md", SAMPLE_NO_CLASS)
        assert v.status == "uncertain"
        assert any(i["code"] == "class_unmarked" for i in v.issues)

    def test_fail_on_forbidden_phrase(self, tmp_path):
        v = _write_and_validate(tmp_path, "forbidden.md",
                                 SAMPLE_FORBIDDEN_PHRASE)
        assert v.status == "fail"
        assert any(i["code"] == "forbidden_phrase" for i in v.issues)

    def test_class_mismatch_fails(self, tmp_path):
        text = SAMPLE_GOOD.replace("class: blog-draft", "class: not-this-class")
        v = _write_and_validate(tmp_path, "mismatch.md", text)
        assert v.status == "fail"
        assert any(i["code"] == "class_mismatch" for i in v.issues)


class TestScoreFloor:
    def test_score_never_below_zero(self, tmp_path):
        # Multiple fails should still produce a non-negative score.
        text = (
            "---\nclass: blog-draft\n---\n\nshort"  # missing fm + headings + words
        )
        v = _write_and_validate(tmp_path, "many-fails.md", text)
        assert v.score >= 0.0


class TestMissingFile:
    def test_returns_fail_for_missing_file(self):
        v = validate_artifact("/no/such/path.md", BLOG_DRAFT)
        assert v.status == "fail"
        assert v.score == 0.0
        assert any(i["code"] == "file_not_found" for i in v.issues)
