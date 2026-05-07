# ADR-002: Operator rating loop over LLM self-evaluation

**Status:** accepted  
**Date:** 2026-05

## Context

Six weeks into running 22 scheduled jobs daily, I had no honest signal on which ones were producing useful output. Engineering observability said all 22 were "healthy" — exit codes, runtime, token counts all looked fine. But three of them were quietly producing junk emails I'd skim and delete. The system was running; the system wasn't working.

I needed an evaluation layer that survived "skill ran without errors but produced nothing useful."

## Options considered

**Option A: LLM self-grading.** Add a "did you do your job?" prompt at the end of each skill run. Cheap, easy to implement.

I tried this. The model gave confident yeses on every run, including ones that produced obvious garbage. The model couldn't see what good looked like in this domain. Self-grading is a thermometer that always reads 98°F.

**Option B: Heuristic metrics.** Define quality proxies (row count, output length, presence of certain fields) and threshold on them. Worked for "did anything get produced" but not for "is it any good." Junk rows with the right shape passed every check.

**Option C: LLM judge with reference outputs.** Have a stronger model grade the weaker model's output against curated examples. Reasonable for narrow tasks (write code that passes these tests) but I couldn't curate reference examples for "did the morning scan find a useful signal" — useful signals look different every day.

**Option D: Operator rating.** I tap a 1-5 star button per job each evening. The system records, accumulates, and aggregates the ratings into a weekly memo. The friction has to be near-zero or it doesn't survive contact with a busy week.

## Decision

Option D. The operating model is closer to how a Japanese senior would supervise a junior employee than to classical software eval:

- **報告 (hou — daily reporting)**: every job logs to `runs.jsonl`. Nothing is invisible.
- **連絡 (ren — daily inform)**: 18:00 chat message lists today's runs + carryovers. The operator is informed of every item, not a sampled subset.
- **相談 (sou — consult)**: optional notes capture what the operator wanted differently. The skill's owner agent reads these into next-week's revisions.
- **振り返り (furikaeri — weekly retrospective)**: Sunday memo aggregates `(skill, platform)` performance, surfaces the bottom of the list, and proposes specific corrective edits to the underlying SKILL.md files.

The system is not graded on metrics — it's reviewed on items. Same as how a junior's work is reviewed in their manager's weekly 1:1, not via a dashboard.

## Consequences

- **Real signal at last.** The data immediately showed which skills were producing junk. Three skills got specific corrective edits within the first month of the loop running.
- **30-second daily cost to the operator.** Inline star-button taps. No typing. No prompts for notes (they're optional and most ratings carry no note). The daily session is short enough to survive a busy week.
- **Carryover discipline.** Every job MUST be rated. Unrated jobs roll forward. There is no "skip this one" — the whole point is that nothing is invisible. This sometimes means rating 2-3 days of carryover when I've been on the road, but the discipline is the value.
- **Per-platform fanout.** A bundled scan that hits 4 sources is rated as 4 separate items, not one averaged number. The weekly memo can spot "scanner is great on source-a, useless on source-c" — a granularity averaged metrics would hide.
- **Distinguishes skill failure from environment failure.** The `model_actual` field on each run records which model actually executed (vs. the model declared in config). When a primary endpoint times out and the fallback dispatcher quietly routes to a backup, that fact lands in the log. The weekly memo can answer "did the publishing skill's quality dip because the skill broke, or because the primary model endpoint was down?" — different fixes, different ownership.

## What we'd do differently

- **Build it earlier.** The system was running with no eval signal for six weeks. I should have built this in week two.
- **Don't over-design the message format.** The first version had three rating axes (quantity / timeliness / quality). The operator (me) wouldn't reliably tap three buttons per item — friction was too high. One axis with a five-step scale survives. The compressed signal is enough; the per-skill notes capture nuance when it matters.

## Lesson named

The system can't grade its own quality. The operator IS the eval signal. Design for that — single-tap simplicity, daily cadence, every item reviewed. The friction is the whole problem.
