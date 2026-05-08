# Friction as feature

A lot of operator-facing software is designed to remove steps. Click fewer buttons. Skip confirmations. Trust the defaults.

This system goes the other direction in specific places. The friction is the feature.

## Where the system makes the operator do work

**Every job must be rated.** No skipping. Unrated items roll forward to the next day's standup. There is no "skip this one" button. After 3 days of carryover, you're rating 60+ items in one evening, which is the point. You can't pretend the queue is empty when it isn't.

**Silence never counts as approval.** A draft sitting in review for 3 hours doesn't auto-publish at the timeout. It stays in review until the operator explicitly says "publish" or "edit." The system would rather hold a piece of work indefinitely than ship something the operator didn't see.

**Issue dismissal is manual.** The dashboard shows alarms for capability drift, schedule misses, scan errors. None of them clear automatically with the passage of time. The operator must explicitly dismiss the issue to acknowledge it was handled. This produces an audit trail of "here's what I noticed and what I did about it" that an auto-clearing alarm system loses.

**Multi-platform ratings require explicit platform.** When a bundled scan that hits 4 sources gets a rating, the operator must specify *which* platform the rating is for. If they say "rate this 3 stars" without naming a platform, the recorder rejects the rating with `missing_platform`. Better to drop a rating than guess the wrong attribution.

**Token-budget warnings interrupt.** When a chat session crosses an 85% context-window threshold, the dashboard shows a "consider fresh-session" prompt. It doesn't auto-fork. The operator must decide whether the current thread's context is worth keeping.

## The principle

Friction prevents two failure modes that are usually invisible:

1. **Silent quality decay.** If carryover auto-clears, mediocre outputs are forgotten. Quality drifts down because the operator never confronts the bad work. The friction of seeing every item, even the boring ones, is what catches the drift.

2. **Loss of operator situational awareness.** If approvals auto-resolve at a timeout, the operator stops reading the queue. If alarms auto-dismiss, the operator stops investigating drift. The system runs without an attentive operator, which means the operator's mental model goes stale, which means when something genuinely surprising happens, the operator doesn't have the context to diagnose it.

Friction in specific places keeps the operator engaged. The cost is real (more clicks, more reading, more "do you really want to do this?"). The benefit is that the operator stays an operator instead of becoming a passive observer.

## Where this is wrong

Friction in *every* place would be paralysis. The system has aggressive friction in places where mistakes compound (publishing, ratings, drift acknowledgment) and aggressive smoothness in places where mistakes don't (logging into the dashboard, refreshing the calendar, re-checking a status that's already shown).

The rule isn't "more friction is better." It's "friction goes where mistakes compound."
