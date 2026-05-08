# Product-Design Choices

Engineering depth alone doesn't make a multi-agent system usable by an operator. The patterns here are the design decisions I made about *how the operator interacts with the system*: what gets surfaced, what gets hidden, what the operator must do, what the system must never decide alone.

Most of these aren't visible in the code samples elsewhere in this repo. They live in the choices: status taxonomies, channel rules, what fields the run record carries, when to send an email vs. silence.

> **Note on what's evidenced where.** Several patterns below describe production-system behavior that the curated subset in this repo doesn't fully implement. The status taxonomy, usage-classification frontmatter, and capability-conflict detector are real in the production system but not visible as code in this excerpt. The friction-as-feature and channel-choice patterns are demonstrably implemented in [`skill-rating-eval/`](../skill-rating-eval/) and [`dashboard-visualization/`](../dashboard-visualization/). The cost-reconciliation file maps to [`dashboard-visualization/cost_reconciliation.py`](../dashboard-visualization/cost_reconciliation.py). The folder is design-pattern documentation; not every pattern lives in this repo's code.

| Pattern | One-line summary |
|---|---|
| [Show, don't decide](show-dont-decide.md) | Surface problems to the operator. Don't auto-fix. |
| [Friction as feature](friction-as-feature.md) | Make the operator do the work. Silence is never approval. |
| [Status taxonomy](status-taxonomy.md) | 8 categories, not binary ok/fail. Each maps to a different operator action. |
| [Channel-choice rule](channel-choice-rule.md) | Chat for synchronous, email for reports, dashboard for status. Never broadcast. |
| [Cost reconciliation UX](cost-reconciliation.md) | Surface variance early. Operator anxiety about cost is legitimate; the UI reduces it through transparency. |
| [Usage classification](usage-classification.md) | `usage: cron / manual / subprocess / chained / emergency / deprecated` as a queryable manifest field. |
| [Lifecycle + retention](lifecycle-and-retention.md) | Nothing disappears. Things age explicitly. Old skills become `deprecated`, not deleted. |

## A meta-observation

A lot of these patterns are the opposite of what an engineer would naturally choose. Engineers optimize for fewer steps, faster paths, automatic resolution. Operators want to know what's happening and decide what to do about it.

Most of the patterns here trade engineering efficiency for operator clarity. The carryover discipline (every job must be rated) is more friction than auto-clearing the queue. The status taxonomy is more code than `bool ok`. The conflict detector that surfaces drift but doesn't fix it is more confusing than one that silently corrects.

Each tradeoff is on purpose. The system is supposed to be operated, not just deployed.
