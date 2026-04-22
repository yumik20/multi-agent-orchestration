# Lint Checklist

Run these checks before calling the wiki healthy.

## Page Quality

- every maintained wiki page has frontmatter
- every maintained wiki page has at least one source path
- every maintained wiki page has an updated date
- no page is both `active` and clearly unsupported

## Structure

- every important page is linked from `wiki/index.md`
- related pages are cross-linked where useful
- duplicate concepts are merged or explicitly split

## Source Integrity

- cited source paths exist
- raw material referenced by wiki pages still exists
- canonical source references still resolve

## Knowledge Health

- stale pages are marked `stale` or `needs-review`
- unsupported claims are downgraded or removed
- contradictions with `claims-and-guardrails.md` are flagged

## Broken Link Check

- internal markdown file references resolve
- output files referenced in logs exist
