# META-05 — Auto-Improve
**id**: META-05 | **hardness**: hard | **type**: meta

## Purpose
Detect skill gaps and quality issues during sessions; generate structured improvement proposals saved to `~/.igsl-skills/_proposed/`.

## Trigger Keywords
`improve`, `fix skill`, `propose`, `evolve`, `skill gap`, `not working`, `wrong approach`

## Activation
Always loaded (hard skill). Runs implicitly when:
- A task fails or requires multiple retries
- User corrects Claude's approach
- A tool call produces unexpected output
- Session ends (retrospective hook)

## Behaviour

### Gap Detection
Monitor for these signals during a session:
1. Tool failure (exit code ≠ 0, error in output)
2. User correction ("no, not that", "wrong", "that's not right")
3. Fallback to a different approach mid-task
4. Missing skill (tried to load a skill that doesn't exist)

### Proposal Generation
When a gap is detected, create a proposal object:
```json
{
  "proposal_id": "PROP-YYYYMMDD-NNN",
  "type": "skill_patch | new_node | registry_update | user_memory",
  "target": "<skill-id or node-id>",
  "summary": "one-line description",
  "severity": "critical | high | medium | low",
  "detail": "specific change to make",
  "sessions_before_promotion": 1
}
```

### Saving Proposals
```bash
# Proposals accumulate in:
~/.igsl-skills/_proposed/YYYY-MM-DD_proposals.json

# Review interactively:
python3 ~/.igsl-skills/hooks/apply_proposals.py --latest

# List pending:
python3 ~/.igsl-skills/hooks/apply_proposals.py --list
```

### Full Evolve Cycle
```bash
# Run full improvement cycle (explicit request only):
python3 ~/.igsl-skills/skill.py evolve <skill-id> --mode FIX
python3 ~/.igsl-skills/skill.py evolve <skill-id> --mode DERIVED
python3 ~/.igsl-skills/skill.py evolve <skill-id> --mode CAPTURED
```

## Integration
- Feeds into META-02 (memory-system) when memory nodes need updating
- Cascade watcher detects degraded skills: `python3 ~/.igsl-skills/hooks/cascade_watcher.py`
- EvoGraph records all evolutions: `~/.igsl-skills/_evograph.jsonl`

## Rules
- NEVER auto-invoke `/self-improve` or `/evolve` — only on explicit user request
- Proposals must be reviewed via `apply_proposals.py` before application
- Always record `sessions_before_promotion` ≥ 1 for critical changes
