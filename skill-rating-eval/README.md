# Skill Rating Eval: Operator-Driven Quality Loop

The system can't grade its own quality. A skill that "ran without errors" can still produce nothing useful. The only signal that survives is the operator's tap.

This subsystem turns that tap into structured data:

```
each skill execution → run_tracker.start_run / finish_run
                              │
                              ▼
                       runs/YYYY-MM/runs.jsonl
                              │
        ┌─────────────────────┴─────────────────────┐
        ▼                                            ▼
Evening (18:00)                             Sunday (19:00)
compute_unrated_jobs.py                     build_weekly_memo.py
+ messaging-app inline 1-5★ keyboard             aggregate by (skill, platform)
+ poll callback_queries                     surface buckets below 3.0★
+ record_ratings.py → ratings.jsonl         email memo + CSV
+ daily/YYYY-MM-DD.md
```

Unrated jobs carry over until rated. Every job must be rated.

## Files

- `run_tracker.py` — `start_run` / `finish_run` helpers. Append-only `runs/YYYY-MM/runs.jsonl`. Millisecond-precision job_id with random suffix to avoid collisions on rapid same-skill runs.
- `compute_unrated_jobs.py` — joins runs.jsonl + ratings.jsonl, returns unrated set as JSON. Fans out per-platform when a run declares `platforms=[...]`.
- `record_ratings.py` — keys ratings on `(job_id, platform)`. Refuses ratings for unknown job_ids. Refuses ratings for platform-tagged runs that don't specify platform.
- `build_weekly_memo.py` — Sunday 19:00 aggregator. Joins by `(skill, platform)`, surfaces buckets <3.0★, writes md memo + CSV, emails them.

## The platform fanout pattern

Some skills do multiple things in one run. The morning scan, for example, hits four sources in parallel and emits one merged CSV. Rating it as a single job loses signal — what if one source returned junk and the others were great?

Solution: skills that bundle multiple concerns declare `platforms=[…]` on `start_run`. The standup expands one run into N rateable items (one per platform), and the weekly memo aggregates by `(skill, platform)`. Now you can spot "scanner is great on source-a and source-d, but source-c needs new targets."

## Why messaging-app inline buttons

The standup runs at 18:00 daily. Free-text replies (`1: 4 good signals`, `2: 3`) work but require the operator to type. Inline keyboard buttons (1★ 2★ 3★ 4★ 5★) let the operator rate everything in 30 seconds during dinner.

The standup never sends per-rating confirmations — clicking the button is acknowledged silently via `answerCallbackQuery`, and one final summary message lists the day's ratings at the end. Anything more is friction the operator pays for daily.

## Schema

```json
{
  "job_id":      "scanner-source-a@2026-05-06T07:30:00.123-3b9f",
  "skill":       "scanner-source-a",
  "mcps_used":   ["scan-pipeline"],
  "platforms":   [],                       // or ["source-a","source-b",…]
  "trigger":     "cron",
  "started":     "2026-05-06T07:30:00",
  "finished":    "2026-05-06T07:35:12",
  "duration_s":  312,
  "artifacts":   ["/path/to/output.csv"],
  "row_count":   42,
  "status":      "success",
  "error":       null,
  "extra":       {"model_actual": "anthropic/claude-haiku-4-5"}
}
```

```json
{
  "job_id":   "scanner-source-a@2026-05-06T07:30:00.123-3b9f",
  "skill":    "scanner-source-a",
  "platform": "",
  "rating":   4,
  "note":     "",
  "rated_at": "2026-05-06T18:42:00"
}
```

The `extra.model_actual` field captures which model actually ran — distinct from the model declared in the org's config. When a primary endpoint times out and the fallback dispatcher routes the run to a backup model, that fact lands here so the weekly memo can answer "did the publishing skill's quality dip because the skill broke, or because the primary model was unavailable?"
