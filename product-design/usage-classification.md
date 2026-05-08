# Usage classification

Every skill in the system has a `usage:` field in its frontmatter. The field has six values, each meaning something different about how the skill is invoked and what error-handling it needs.

## The six values

```yaml
usage: cron (<bot>, <cadence>)
usage: manual (<bot>)
usage: subprocess (called by <parent skill>)
usage: chained (called within <workflow>)
usage: emergency (failover when <trigger>)
usage: deprecated (replaced by <successor>)
```

Examples:

```yaml
# A skill on a fixed schedule, owned by one agent
usage: cron (scanner, daily 08:00)

# Operator-triggered only, no schedule
usage: manual (intel)

# Internal helper invoked by another skill
usage: subprocess (called by scan-pipeline)

# Skill that runs as part of a multi-step workflow
usage: chained (called within publish-flow Phase B)

# Emergency-only failover
usage: emergency (failover when scan apps crash)

# Old skill with a successor; kept for reference
usage: deprecated (replaced by skill-y-2026)
```

## Why this matters

Different invocation contexts need different error-handling, notification, and logging strategies. Without explicit classification, every skill ends up with a slightly different convention, and operators have to read prose to figure out which is which.

A `cron` skill that fails should notify the operator (a scheduled run is supposed to produce something). A `subprocess` skill that fails should propagate its error to the parent skill, not page the operator (the parent skill might handle it). A `manual` skill that fails should fail loudly to the operator who's already attending to it.

A `deprecated` skill should be visible in the catalog but flagged in the dashboard with a "do not use" badge, and the orchestrator should warn if any cron job tries to invoke it. The retired skill stays parsed (so audit trails of past runs still resolve) but its scheduled invocations are no-ops.

The classification turns *prose* ("this skill runs on cron Mondays at 9 AM and is owned by the scanner agent") into *queryable metadata* ("usage = cron, owner = scanner, cadence = Mon 09:00"). The dashboard reads it. The cron dispatcher reads it. The lifecycle-management skill reads it.

## What this replaces

The pre-classification version had:

- Cron schedules in one file (`launchd plists`)
- Skill-to-agent ownership in another file (`org-chart.md`)
- Workflow chains in a third file (`workflows.md`)
- Deprecation notes in skill prose, sometimes in commit messages, sometimes nowhere

Each source could drift from the others. A skill could be in the cron file but not in the org-chart file, or marked deprecated in commit history but still actively scheduled.

Putting `usage:` in the skill's own frontmatter means there's one source of truth, parsed at request time, and the dashboard's drift detector can flag any inconsistency between this field and the actual scheduler state.

## Cost

Operators who add new skills have to know which classification to pick. Most are obvious (a scheduled scanner is `cron`; a help skill is `manual`). The non-obvious cases (`emergency` vs. `subprocess`, `chained` vs. `subprocess`) require thinking about how the skill will be invoked, which is the right question to ask at design time anyway.

The cost is paid once at skill-creation. The benefit is queryable for the skill's lifetime.
