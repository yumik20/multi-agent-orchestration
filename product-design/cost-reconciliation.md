# Cost reconciliation UX

Most LLM dashboards I've seen show one number: estimated cost from API responses. That number is wrong in two ways for someone running a real budget.

This dashboard shows three numbers and the variance between them. The hero panel is built around the gap between estimate and reality.

## The three numbers

**Estimated.** Auto-tracked from API responses. Each call returns an `input_tokens` / `output_tokens` count; we multiply by the per-model pricing in `pricing.json` and sum.

**Prepaid consumed.** Operator-entered. When a provider invoice arrives, the operator records the actual amount drawn against the prepaid balance. This is the ground truth.

**Reconciled total.** The estimate plus a variance term. Variance is computed as (prepaid actual − estimate) and color-coded:
- Positive variance (over budget vs. estimate) → warning tone
- Negative variance (under budget) → ok tone
- Zero or near-zero → neutral

## Why three numbers

The estimate is wrong for two reasons that compound:

1. **Pricing drift.** Provider prices change. A model that cost $3/1M input tokens last quarter might be $2.50 this quarter. Our `pricing.json` has the rate when we last updated it. The estimate uses that rate; the actual draw uses the current rate. They diverge.

2. **Tokens we don't see.** Some calls have hidden charges: vision tokens at a different rate, image generations charged per image, prompt-cache reads charged at a discount we may not be tracking. The estimate sees what the API response advertised; the actual draw sees what the provider charges.

Showing only the estimate gives the operator false confidence. Showing only the actual draw is reactive: by the time the invoice arrives, last month's overspend is already there. Showing both, plus the variance, lets the operator answer:

- *"Are we tracking?"*: variance near zero, our estimate is calibrated
- *"Are we drifting?"*: variance growing, time to update `pricing.json` or investigate untracked usage
- *"Did something break?"*: variance spiking, an agent might be in a runaway loop

## What this is NOT

It's not a billing system. It doesn't predict next month's invoice. It doesn't enforce budget caps (the system doesn't refuse to call a model because the variance is high; refer to [show-dont-decide](show-dont-decide.md)).

It's a *calibration UI*. The variance is the diagnostic. The operator interprets it.

## The hero-panel decision

The temptation in dashboard UI is to push reconciliation into a "Cost details" subpanel, out of the way, available if the operator wants to drill in. This dashboard does the opposite: variance is hero-level. The operator sees it before they see the agent list, before they see the schedule, before anything else.

The reasoning is that cost anxiety for someone running their own LLM budget is legitimate and continuous. Hiding the variance in a subpanel teaches the operator that cost is occasional. Surfacing it teaches that cost is always-on, and reduces the anxiety by making the answer visible without a click.

This is a specific operator-empathy choice, not a generic dashboard convention.
