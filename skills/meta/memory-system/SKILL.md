# META-02 — Memory System
**id**: META-02 | **hardness**: hard | **type**: meta

## Purpose
Manage the memory node network: create, update, decay, search, and surface relevant nodes at session start.

## Trigger Keywords
`remember`, `memory`, `recall`, `forget`, `node`, `store`, `what do you know about`, `context`

## Activation
Always loaded (hard skill). Runs at session start (T0+T1 blocks) and on explicit memory operations.

## Node Types & Half-Lives
| Type | Half-life | Purpose |
|------|-----------|---------|
| DEC  | ∞         | Permanent decisions, architectural choices |
| PAT  | 30d       | Patterns, recurring approaches |
| ARCH | 60d       | System architecture snapshots |
| ART  | 14d       | File/artifact references |
| LOOP | ∞ (until closed) | Open items, TODOs |
| GEN  | 90d       | General insights, heuristics |
| ERR  | 180d      | Bug records, error patterns |

## Core Operations

### Add a node
```bash
python3 ~/.igsl-skills/memory/node.py add \
  --id HMS-018 \
  --type DEC \
  --tags "hms factor decision" \
  --content "New factor decision text here" \
  --src "session_id"
```

### Query memory
```bash
python3 ~/.igsl-skills/memory/node.py query "factor IC window hms"
# Returns top-5 by BM25 × weight × recency_factor
```

### Show active nodes
```bash
python3 ~/.igsl-skills/memory/node.py active
python3 ~/.igsl-skills/memory/node.py show
```

### Close a LOOP
```bash
python3 ~/.igsl-skills/memory/node.py close HMS-015 --resolution "Decided not to pursue options flow"
```

### Run GC (remove expired/low-weight nodes)
```bash
python3 ~/.igsl-skills/memory/node.py gc --dry-run   # preview
python3 ~/.igsl-skills/memory/node.py gc              # execute
```

## Weight Decay Formula
```
effective_weight = weight × exp(-ln(2) × age_days / half_life)
```
Nodes with effective_weight < 0.05 are GC candidates.

## Search Ranking
```
score = BM25(query, content+tags) × effective_weight × recency_factor
recency_factor = exp(-age_days / 90)  # independent of half-life
```

## Semantic Search (optional)
```bash
python3 ~/.igsl-skills/memory/embed.py build   # build embeddings
python3 ~/.igsl-skills/memory/embed.py search "query text" --top 5
```
Degrades gracefully to BM25-only if sentence-transformers unavailable.

## Active Index
Rebuilt every session by `session_start_v2.sh`:
```
~/.igsl-skills/memory/active-index.json
```
Contains: all active node IDs, open loops, recent ART nodes.

## Rules
- Always use node IDs with meaningful prefixes (HMS-, OC-, SK-, GEN-, etc.)
- LOOP nodes stay active until explicitly closed with `close` command
- ART nodes are auto-created by `health_recorder.py` on file writes
- Never delete DEC nodes — they are permanent architectural decisions
