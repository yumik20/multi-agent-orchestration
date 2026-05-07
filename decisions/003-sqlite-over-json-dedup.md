# ADR-003: SQLite over JSON files for the dedup cache

**Status:** accepted  
**Date:** 2026-04

## Context

Each scanner skill maintained its own JSON file mapping `url → seen_at_iso`. Reading meant parsing the whole file; writing meant rewriting the whole file. With four scanners and ~thousand URLs each in the rolling 30-day window, this was already the slowest part of the qualify pipeline by month two.

Worse: the four files drifted. A URL qualified by the morning scan would re-appear in the afternoon scan because they kept separate state. Cross-skill state should have been one store, not four.

## Options considered

**Option A: Status quo.** Live with the rewrites. They're fast enough on a laptop SSD; the drift problem could be solved by having all four scanners read all four files. But "read all four files" multiplies parse cost by 4 and the file-write race condition gets worse.

**Option B: A single shared JSON file.** One file, all four scanners read it on start, append to it on finish. Solves the drift, doesn't solve the rewrite-the-whole-file cost. And introduces a write race when two scanners finish near-simultaneously (which they do — most run on a stagger of 10-20 seconds).

**Option C: SQLite.** Single file, WAL-mode incremental writes, indexed lookups in microseconds, cross-process safe by design. Standard library — no new dependencies.

**Option D: Redis or a real DB.** Overkill. This is a personal system with thousands-not-millions of URLs. A daemon to manage, ports to claim, ops complexity I don't want.

## Decision

Option C. One SQLite file at `mcp-server/state.db`. Two tables: `runs` (the run history that powers `scan_status`) and `seen_urls` (the dedup window). Migrating the four JSON files was a one-shot replay loaded into the new schema with `INSERT OR IGNORE`.

The decision was over-determined: SQLite is stdlib, has WAL-mode incremental writes, gives us indexed lookups for free, and is queryable by ad-hoc tools when something looks weird. JSON-as-database has none of those properties.

## Consequences

- **Microsecond lookups.** A `SELECT 1 FROM seen_urls WHERE url=? AND last_seen > date('now', '-30 days')` resolves in a few microseconds with the right index. The previous JSON-parse approach was milliseconds-per-check, which compounded across batched calls.
- **No more rewrite-on-update.** WAL-mode means an update is an append to the WAL, not a rewrite of the database file. Concurrent reads continue without blocking on the writer.
- **Cross-skill queries.** The `smart_dedup` MCP tool takes a list of URLs and returns which ones any scanner has seen. Skill A's qualifications are now visible to skill B in the same query.
- **Inspection-friendly.** When a scan looks weird, I can `sqlite3 state.db "SELECT * FROM runs WHERE started_at > date('now','-1 day')"` and see what happened. The previous JSON files were inspectable only via `cat` + `jq` and didn't capture run metadata.
- **One file to back up.** Trivial to rsync to an external drive nightly. The four JSON files were always slightly out of sync depending on which scanner had finished writing.

## What we'd do differently

- **Add the run history table from day one.** The dedup table came first; the runs table came two weeks later when I needed to debug a scan that had silently failed. The runs table is the foundational observability layer; should have been first.
- **Document the indices.** The default schema had a primary key on `url` but no index on `last_seen`. Date-range queries were slow until I added it. The index list belongs in the schema definition with a comment, not in tribal knowledge.

## Lesson named

When a JSON file becomes a database, make it a database. SQLite is stdlib; there's no excuse to keep parsing files when indexed queries are one `CREATE INDEX` away.
