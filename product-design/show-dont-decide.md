# Show, don't decide

The system has many places where it could auto-correct a problem. It almost never does. Instead, it surfaces the problem to the operator and lets the operator decide.

## Examples in the system

**Capability conflict detector.** The dashboard parses three sources of truth: the runtime config (which model is actually loaded), `AGENT_MODELS.md` (the documented model assignment), and `ORGCHART.md` (the allowlist of models that role is permitted to use). When they disagree, the dashboard renders an alarm with a `suggestedFix` string and the file path. It does *not* edit any of the three files to resolve the disagreement.

**Weekly skill memo.** When the operator's ratings show a skill below 3.0★ for the week, the memo lists the skill, sample notes, and proposes a specific edit to that skill's `SKILL.md`. The proposed edit is text in the email. The operator decides whether to apply it. The memo never opens a PR or amends the skill file directly.

**Model-fallback dispatcher.** When a primary endpoint times out, the dispatcher retries on a configured fallback. It does *not* update the agent's declared model. Instead, it writes a `model_actual` field on the run record so the weekly memo can answer the operator's diagnostic question: "did the skill break, or did the primary endpoint die?" The operator decides whether the recurring fallbacks mean the agent should be permanently switched.

**Retention rules.** The cleanup scripts apply mechanical rules ("delete logs older than 7 days"), but anything that requires judgment ("is this artifact still useful?") is queued for the weekly workspace curation, where the operator's curator agent reviews each candidate. Auto-curation never happens.

## Why

Auto-fixing looks efficient. It compounds drift.

If the conflict detector silently rewrites `AGENT_MODELS.md` to match the runtime, the operator never learns *why* the runtime drifted. Three weeks later it drifts again, the detector silently fixes it again, and a real bug is masked indefinitely.

If the weekly memo applies its own proposed edits, the operator stops reading the memo carefully. Trust shifts from "I review the system's recommendations" to "the system is fixing itself, I'll catch up later." Then a bad edit lands and the operator can't tell when the regression started.

If the model-fallback dispatcher silently swaps to a backup, the operator doesn't notice the primary is unhealthy until the secondary fails too.

The pattern is: **find the seam where automation could decide, and put the operator there instead.** Surface the fact loudly. Let the operator carry the cognitive load of "what should I do?" because that's where the judgment is.

## Costs

This is genuinely more friction. Every drift is an alarm someone reads. Every weekly memo is a list of decisions to make. Every recurring fallback is a question.

The cost is real. It's the price of staying in the loop.
