# META-02 — Skill Selector
**id**: META-02 | **hardness**: hard | **type**: meta

## Purpose
Intelligently select and load the right skills for each session based on project context, user message keywords, and health scores. Manages the progressive disclosure loading system.

## Trigger Keywords
`load skill`, `which skill`, `skill for`, `what skills`, `context`, `session start`

## Activation
Always loaded (hard skill). Runs automatically during `session_start_v2.sh`.

## Loading Tiers

### T0 — Identity Block (~80 tokens, always)
```
~/.igsl-skills/memory/t0_identity.mem
```
User profile, active projects, token budget summary.

### T1 — Session Block (~50 tokens, always)
```
~/.igsl-skills/memory/t1_session.mem  (populated fresh each session)
```
Session ID, today's date, project, recent nodes, open loops.

### Index Block (~50 tokens, always)
```
~/.igsl-skills/memory/active-index.json  (top 10 node IDs)
```
Snapshot of active memory network.

### Hard Skills (~460 tokens, always)
META-01..08 condensed summaries. All skill IDs and trigger keywords for routing.

### Soft Skills (load on demand)
Loaded when keyword match detected in user message:
```bash
python3 ~/.igsl-skills/skill.py scan --message "user message text"
# Returns list of skill IDs to load
```

### T2 Project Context (load on project match)
```
~/.igsl-skills/memory/t2/hms.mem       # loads on: hms, factor, alpha, quant
~/.igsl-skills/memory/t2/openclaude.mem # loads on: openclaude, whatsapp, voice
~/.igsl-skills/memory/t2/skill-graph.mem # loads on: igsl, skill, memory, hook
```

## Skill Selection Algorithm
```python
# 1. Always load T0 + T1 + Index + Hard skills
# 2. Detect project from pwd + git remote
# 3. Load matching T2 context block
# 4. Scan user message for soft-skill keywords
# 5. Load matching soft skills (up to 3, sorted by health score)
# 6. Total budget: 640 base + up to 3×200 soft = ~1240 tokens max
```

## Scan Command
```bash
python3 ~/.igsl-skills/skill.py scan --message "debug latex compilation error"
# → suggests: GEN-ERR-001 (latex-errors), META-02 (memory-system)

python3 ~/.igsl-skills/skill.py scan --project hms
# → suggests: S-01 (quant-research), M-01 (blackboard-mcp)
```

## Load Command
```bash
python3 ~/.igsl-skills/skill.py load META-01 META-03
# Outputs: skill content formatted for additionalContext injection
```

## Rules
- Never load more than 3 soft skills simultaneously (token budget)
- Prefer high-health skills when multiple options match same keyword
- Always refresh T1 block at session start
- Log which skills were loaded to journal for retrospective analysis
