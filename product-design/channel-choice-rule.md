# Channel-choice rule

The system has four channels for communicating with the operator: chat (a messaging-app bot with inline buttons), email (Mail.app via AppleScript), the dashboard (live HTTP + SSE), and file-state (markdown / JSONL committed to the workspace).

There's an explicit rule for when each channel gets used. Most operator-tool systems blur these. This one doesn't.

## The rule

| Channel | Use it for | Don't use it for |
|---|---|---|
| Chat (synchronous) | Things the operator should notice *right now*. Ratings prompts. "Draft ready for review." "Scan crashed." Approvals that need a tap response. | Long-form data. Reports. Anything the operator would rather read carefully later. |
| Email (asynchronous) | Things to read carefully later. Weekly memos with CSV attachments. Daily intel digests. Long competitive briefs. | Time-sensitive alerts. Anything that needs operator action in <1 hour. |
| Dashboard (status surface) | Operational state. What's running, what failed, what cost what. Capability drift alarms. The continuous "where do I stand right now?" view. | One-off events. Approvals. Anything that requires the operator's attention even when they're not looking at the dashboard. |
| File-state (persistent) | Audit trail. What ran, when, with what model, what it produced. Anything that needs to be queryable months later. | Synchronous communication of any kind. |

## Specific applications

**Approvals always go to chat, never email.** A draft awaiting review goes to chat with `[publish]` and `[edit]` inline buttons. The operator sees it on their phone, taps within minutes, the system continues. If approvals went to email, they'd sit in an inbox for hours.

**Long-form findings always go to email, never chat.** A daily intel digest with 15 candidates and 8 paragraphs of context goes to email. Chat is for "intel digest sent: 15 candidates" if the operator wants a confirmation, or silence if they don't.

**System failures go to chat AND get logged in file-state.** "Scan crashed at 14:03, Chrome lost session" goes to chat for the immediate alert. The same failure is recorded in `runs.jsonl` so the weekly memo can spot the pattern.

**Status questions always go to dashboard, never chat.** "Is the publishing skill running today?" is answered by opening the dashboard. The system never sends "publishing skill ran successfully" as an unprompted chat message. That would be noise.

## Why this matters

Each channel has a cost the operator pays:
- Chat costs attention *right now*.
- Email costs attention *later*, batch-amortized.
- Dashboard costs attention *only when the operator chooses to look*.
- File-state costs no attention (machines read it).

Mixing them (sending a weekly memo to chat, sending an approval to email, putting a one-time failure only on the dashboard) wastes the budget of one channel and underuses another.

A specific subtlety: the chat channel is reserved for things that need operator response. Status updates ("scanner just ran successfully") explicitly do *not* go to chat, because they teach the operator that chat messages can be ignored. The first time the operator ignores a chat message because "it's probably just status," they'll miss a real approval. So chat stays scarce.

## How this plays out as code

The rule is encoded mostly in skill prompts and dispatch wrappers, not in a single config:

- Skills that produce digests have `--send-email` flags, never `--send-chat` for the digest body
- The standup-rating skill explicitly only uses chat (rating prompts must be synchronous)
- The dashboard's auto-update over SSE means status info flows there continuously without any agent having to push it
- The run-tracker writes to `runs.jsonl` (file-state) regardless of which other channel notified the operator

When a new skill is added, the question "which channel does this output use?" is part of its design, not an afterthought.
