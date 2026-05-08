# Lifecycle and retention

Things in the system age. Skills, agents, scan results, illustrations, log files, dedup caches. Each has a lifecycle and a retention rule.

The principle: nothing disappears silently. Old things move from active state to archive, or get marked deprecated, or sit in a curation queue until the operator reviews them.

## The retention layers

Three layers, by how aggressive the cleanup is:

**Mechanical retention.** Time-based, no judgment. Run logs older than 7 days get deleted. Dedup cache entries older than 30 days get pruned. Findings markdown older than 7 days get deleted. These rules are encoded in cron scripts that run weekly and don't need operator attention.

**Curated retention.** Time-based but judgment-dependent. Illustrations older than 7 days might be reusable; the curation skill flags them for the operator's weekly review rather than deleting. Workspace memory older than the warm window (90 days) moves to archive rather than getting deleted. The operator can pull from archive if needed.

**Deprecation, not deletion.** Skills and agents are never deleted. A retired agent gets `usage: deprecated` in its frontmatter plus a strikethrough entry in the org chart with the date it was retired and what it was merged into. The retired skill stays parseable so audit trails of past runs still resolve. The orchestrator just won't dispatch new runs to it.

## Why three layers

The natural instinct is to apply mechanical retention to everything: anything old gets deleted. That works for log files; it doesn't work for illustrations or for retired skills.

**Illustrations:** an old illustration might be the right reference for a future blog post. Mechanically deleting at 7 days loses real value. Curating at 7 days (operator decides per-illustration) keeps the value but bounds the storage cost.

**Retired skills:** if a skill is mechanically deleted, the run records pointing to it stop resolving. The audit trail breaks. Six months later, the operator can't answer "what did this old skill produce in March?" Marking deprecated keeps the audit trail intact.

The three layers correspond to three different "is this disposable?" answers: yes (mechanical), maybe (curated), no (deprecation).

## The deprecation surface

When a skill becomes deprecated, three things happen, all visible:

1. **Frontmatter tag.** `usage: deprecated (replaced by <successor>)`. Machine-readable.
2. **Description prose.** A bold note at the top of the SKILL.md describing the retirement and the successor. Human-readable when reading the skill directly.
3. **Org chart strikethrough.** The org chart shows the agent struck through with a date (`~~Old Skill~~ retired 2026-04-11 → tasks → New Skill`).

Three signals because each is read at a different level: the orchestrator parses frontmatter; the operator reads SKILL.md when investigating a skill; the org chart is the high-level operator overview.

## What this prevents

**Zombie scheduled jobs.** Without `usage: deprecated`, a retired skill might still be in the cron config. The orchestrator dispatches a run, the skill is gone, the run fails, the failure clogs the alarm queue. With deprecation in the frontmatter, the orchestrator knows to skip the dispatch.

**Lost institutional memory.** Without strikethrough-with-date in the org chart, the operator three months from now will look at the agent list and ask "what was the old structure? when did this change?" The org chart is the answer.

**Silent retention drift.** Without explicit time windows ("7 days for logs", "30 days for dedup", "90 days for warm memory"), retention rules drift toward "whenever someone notices the disk is full." Explicit windows let the operator tune them and let the cleanup scripts apply them mechanically.

## Cost

The discipline costs disk space (deprecated skills take some) and operator time (curation reviews aren't free). The benefit is that the system has memory: every retirement, every move, every tier-down is documented. When something works, the operator knows what changed; when something breaks, the operator can trace what changed back.

Most systems trade memory for storage. This one trades storage for memory.
