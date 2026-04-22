# Query Workflow

Use this workflow whenever answering from the KMspace.

## Answer Order

1. start with `wiki/index.md`
2. read the most relevant wiki pages
3. if needed, check `sources/` for canonical grounding
4. if still missing, inspect `raw/` for recent unpromoted evidence
5. answer from the wiki, not from ad hoc retrieval alone

## Answer Modes

### Mode A: supported answer

Use when the wiki already has enough support.

Output:

- concise answer
- cite the wiki pages used

### Mode B: provisional answer

Use when `raw/` or `sources/` contain evidence but the wiki is incomplete.

Output:

- answer with explicit note that the knowledge should be promoted
- list the exact pages to update

### Mode C: durable answer

Use when the answer creates reusable synthesis.

Action:

- save the answer into `wiki/` or `output/`
- log it in `../output/writeback-log.md`

## Writeback Triggers

Write back if the answer:

- unifies multiple existing pages
- creates a reusable comparison or thesis framing
- resolves a recurring ambiguity
- should be reused by Tommy, Matt, or Meta7 later
