# CLAUDE.md — IGSL Skill Graph Development
# Place at: ~/.igsl-skills/CLAUDE.md

## IGSL v2 System
This IS the skill graph system. Self-referential: uses IGSL to improve IGSL.
All META skills are relevant here.

## Project: IGSL v2 Skill Graph

## Skill Graph Rules

### Adding New Skills
```bash
# 1. Create SKILL.md at appropriate path
mkdir -p ~/.igsl-skills/skills/CATEGORY/SKILL-NAME/
# Write SKILL.md with standard header

# 2. Register in _registry_v2.yaml
python3 ~/.igsl-skills/skill.py add \
  --id NEW-01 \
  --name "skill-name" \
  --type skill \
  --path "~/.igsl-skills/skills/CATEGORY/SKILL-NAME/SKILL.md" \
  --tags "tag1 tag2" \
  --hardness soft-hook

# 3. Verify
python3 ~/.igsl-skills/skill.py show NEW-01
```

### Health Monitoring
```bash
python3 ~/.igsl-skills/skill.py health show          # all scores
python3 ~/.igsl-skills/skill.py health alert         # only alerts
python3 ~/.igsl-skills/hooks/cascade_watcher.py      # cascade issues
```

### Improving Skills
```bash
# Review pending proposals
python3 ~/.igsl-skills/hooks/apply_proposals.py --list
python3 ~/.igsl-skills/hooks/apply_proposals.py --latest

# Evolve a skill (explicit request only)
python3 ~/.igsl-skills/skill.py evolve META-01 --mode FIX
```

### Memory Operations
```bash
python3 ~/.igsl-skills/memory/node.py show            # all nodes
python3 ~/.igsl-skills/memory/node.py gc --dry-run    # preview GC
python3 ~/.igsl-skills/memory/node.py active          # active index
```

### Integration
```bash
python3 ~/.igsl-skills/integrate.py session-context   # token budget
python3 ~/.igsl-skills/integrate.py health-sync       # sync health to memory
python3 ~/.igsl-skills/integrate.py post-session --journal PATH  # manual retro
```

### Git Operations
```bash
git -C ~/.igsl-skills status
git -C ~/.igsl-skills log --oneline -10
git -C ~/.igsl-skills add -A && git -C ~/.igsl-skills commit -m "message"
```

## Architecture Reference
```bash
python3 ~/.igsl-skills/memory/node.py query "igsl architecture"
# Returns SK-001..008 + ARCH nodes
```

## No-Auto-Self-Improve Rule
NEVER invoke /self-improve, /evolve, /reflect automatically.
Only on explicit user request by name in current message.

## User Context
- igsl | power user | building self-improving Claude system
- Style: concise, direct, no preamble, no trailing summaries
