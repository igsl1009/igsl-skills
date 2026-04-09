# META-06 — Gap Filler
**id**: META-06 | **hardness**: hard | **type**: meta

## Purpose
Detect missing skills and knowledge gaps during sessions; propose new skill nodes or memory nodes to fill them. Tracks "unknown unknowns" from failed tasks.

## Trigger Keywords
`missing skill`, `don't know how`, `not sure how to`, `new capability`, `gap`, `skill not found`, `need to learn`

## Activation
Always loaded (hard skill). Passive monitoring during all sessions.

## Gap Detection Signals

### Tool-level signals
- Tool fails with "not found" or "command not found" → possible missing skill
- Bash command times out or produces error → environment gap
- Import error in Python → missing dependency gap

### Task-level signals
- Claude uses >3 search attempts for same topic → knowledge gap
- User says "I thought you knew how to..." → undocumented skill
- Multiple fallback attempts before success → skill needs improvement

### Session-level signals (from retrospective)
- journal events with `type: tool_failure` → aggregate failure patterns
- High `fallback_rate` on specific skill → skill needs FIX evolution

## Gap → Proposal Workflow

### 1. Detect gap
```python
# Gap detected during session → log to journal
{
  "type": "gap_detected",
  "ts": "...",
  "description": "No skill for X",
  "suggested_skill": "SKILL-NAME",
  "evidence": "tool failure / user correction / multiple retries"
}
```

### 2. Generate proposal
```json
{
  "proposal_id": "PROP-2026XXXX-001",
  "type": "new_node",
  "target": "NEW-SKILL-ID",
  "summary": "Add skill for [capability]",
  "severity": "medium",
  "detail": "YAML stub for new skill node",
  "sessions_before_promotion": 2
}
```

### 3. Review at session end
```bash
python3 ~/.igsl-skills/hooks/apply_proposals.py --latest
```

## Priority Matrix
| Impact | Frequency | Priority |
|--------|-----------|---------|
| High   | High      | Critical — propose immediately |
| High   | Low       | High — propose after 1 session |
| Low    | High      | Medium — propose after 2 sessions |
| Low    | Low       | Low — note in journal only |

## Known Gaps (tracked as LOOPs)
- SK-006: Semantic embedding search for skills (OPEN)
- OC-005: Calendar/email integration for OpenClaude (OPEN)
- HMS-015: Options flow alpha signal (OPEN)

## Rules
- Never propose a skill that already exists (check registry first)
- A gap is only "confirmed" after appearing in 2+ sessions
- Soft skills are preferred over hard for narrow capabilities
- Always include evidence when creating a gap proposal
