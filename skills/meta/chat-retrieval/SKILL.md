# META-08 — Chat Retrieval
**id**: META-08 | **hardness**: hard | **type**: meta

## Purpose
Search past conversation history and session journals to retrieve relevant context, decisions, and patterns from previous sessions.

## Trigger Keywords
`what did we decide`, `previous session`, `recall`, `chat history`, `past conversation`, `last time`, `what was the`, `search history`

## Activation
Always loaded (hard skill). Derived from META-03 (graph-manager) via EvoGraph DERIVED edge.

## Data Sources

### Chat Index (BM25 search)
```bash
python3 ~/.igsl-skills/memory/query.py search "factor IC lookahead"
# Searches chat-index.jsonl for relevant session summaries
```

### Session Journals
```
~/.igsl-skills/_journal/YYYY-MM-DD_SESSIONID.jsonl
```
Each line is a journal event: `session_start`, `tool_failure`, `skill_applied`, `gap_detected`, `skill_evolved`

### Tool Logs
```
~/.igsl-skills/memory/tool-log/YYYY-MM-DD.jsonl
```
Records every tool call: tool name, input summary, success/fail, session ID.

## Retrieval Operations

### Search chat history
```bash
python3 ~/.igsl-skills/memory/query.py search "HMS momentum factor" --top 5
python3 ~/.igsl-skills/memory/query.py search "openclaude timeout" --date-range 2026-04-01:2026-04-09
```

### Index a new session (usually automatic)
```bash
python3 ~/.igsl-skills/memory/query.py index --session SESS_ID
# Reads journal, extracts summary, appends to chat-index.jsonl
```

### Show chat index stats
```bash
python3 ~/.igsl-skills/memory/query.py show
# Lists sessions, projects, date range, entry count
```

### Search memory nodes (cross-session facts)
```bash
python3 ~/.igsl-skills/memory/node.py query "factor pipeline winsorize"
# Returns nodes ranked by BM25 × weight × recency
```

### Semantic search (if embeddings available)
```bash
python3 ~/.igsl-skills/memory/embed.py search "fix lookahead bias factor"
# Uses all-MiniLM-L6-v2 cosine similarity
```

## Retrieval Ranking
```
# Chat index:
score = BM25(query, summary+tags) × recency_factor

# Memory nodes:
score = BM25(query, content+tags) × weight × exp(-age/90)

# Combined:
Merge and re-rank; prefer memory nodes for facts, chat index for episodic context
```

## Chunking for Long Sessions
```bash
python3 ~/.igsl-skills/memory/query.py chunk --session SESS_ID --size 1000
# Splits long session transcripts into overlapping 1000-token chunks for search
```

## Rules
- Always prefer memory nodes over chat index for stable facts (decisions, patterns)
- Use chat index for episodic context ("what did we do last Tuesday")
- If embedding search conflicts with BM25: trust BM25 for keyword queries, embedding for semantic
- Chat index entries are summaries only — never store raw conversation text
