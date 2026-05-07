# ADR-005: Markdown table config over YAML for runtime model assignments

**Status:** accepted  
**Date:** 2026-04

## Context

I needed a single source of truth for "which model does each agent use" — text model, optional image model, role label. The dashboard reads it to display the agent capability matrix. The conflict-detector reads it to flag drift between configured models and runtime models. The agents themselves don't read it (their model is set in their runtime config), but operators edit it when changing model assignments.

The first version was hardcoded in Python: a dict literal in the dashboard server module. Editing required a code change, a server restart, and a deploy step that didn't exist (this is a personal system). In practice the dict drifted from intent within a week.

## Options considered

**Option A: Status quo.** Hardcoded dict. Drift continues.

**Option B: YAML config file.** Standard format, parsers everywhere, clean structured nesting. The downside: humans don't read YAML well in PR diffs and especially don't notice subtle changes (a moved nesting level, a wrong sigil). YAML diffs make code review harder, not easier.

**Option C: JSON config file.** Same shape as YAML, worse on whitespace/comments. Trades human-readability for one less parser dependency, which is a wash on a stdlib-only system (both `json` and `yaml` are zero-add for the runtime).

**Option D: Markdown table.** A single markdown file with a table per agent group. Each row is `| Bot | Role | Text Model | Image Model | Reports To |`. Operators read it directly; dashboards parse it; PR diffs are trivially scannable.

## Decision

Option D. Single file at `marketing_team/shared/AGENT_MODELS.md`. Parser at `cost-optimization/agent_models_md.py` walks GFM tables and extracts `{bot: {model, imageModel, ...}}`. Dashboard parses it at request time — no caching beyond the standard `_PERF_CACHE` window. Editing the markdown moves the dashboard on the next render.

Three properties of markdown that won the tradeoff:

1. **Human-readable in any rendered surface.** GitHub, the in-editor preview, a static-site generator, a print preview — all show the table the same way. YAML and JSON look like config; markdown looks like documentation.

2. **PR-diff scannable.** A change to `creator-bot | creator | gpt-4.1 | nano-banana-pro / gemini-3-pro-image | manager` shows up as a one-line diff. Easy to review, easy to revert. YAML diffs of the same change can span 4-8 lines depending on nesting.

3. **The file is also documentation.** Same artifact serves as the operator's mental model and the runtime config. No "the config says X but the docs say Y" drift, because the config IS the docs.

## Consequences

- **Editing model assignments is editing markdown.** A new agent gets a row. A model swap is a one-line edit. Reviewable in 10 seconds.
- **The conflict-detector compares markdown vs. live runtime.** The dashboard surfaces "the table says agent X uses Haiku, the runtime says Sonnet" as an alarm. Drift becomes visible instead of silent.
- **One subtlety: parsing slashes.** Image-model values like `nano-banana-pro / gemini-3-pro-image` contain literal `/` separators. The split has to be on `\s+/\s+` (with required spaces), not just `/`, or `gemini-3-pro-image` becomes two values. Pinned in the parser tests.
- **Adoption cost beyond models.** Once the pattern existed, a `SCHEDULE.md` table and an `ALLOWLIST.md` table followed. Operators got used to "edit the markdown" as the lever for changing system behavior.

## What we'd do differently

- **Provide a `validate` mode on the parser.** Operators occasionally write a malformed table (forgot a column, extra pipe). The parser silently drops the row. A `python3 agent_models_md.py --validate` mode would catch this at edit time instead of at request time.
- **Standardize the column-name normalizer.** First version was case-sensitive on header names (`Text Model` vs. `text model`). The second version lower-cases and underscores. Would have been better to start with the normalized form.

## Lesson named

When humans and parsers both read the same file, optimize for the humans. Machines are tireless about formatting; humans are not. A markdown table is a config file that's also documentation; YAML is a config file that pretends to be documentation.
