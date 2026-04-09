# META-01 — Graph Manager
**id**: META-01 | **hardness**: hard | **type**: meta

## Purpose
Manage the skill graph: add/update nodes, track health, run evolutions, manage the registry.

## Trigger Keywords
`skill`, `registry`, `add skill`, `update skill`, `health`, `graph`, `evolve skill`, `skill health`

## Activation
Always loaded (hard skill). Used for all skill graph management operations.

## Core Operations

### Query skills (BM25 + health boost)
```bash
python3 ~/.igsl-skills/skill.py query "factor research"
python3 ~/.igsl-skills/skill.py query "latex errors" --top 3
```

### Show skill details
```bash
python3 ~/.igsl-skills/skill.py show           # all nodes summary
python3 ~/.igsl-skills/skill.py show META-01   # specific node
```

### Health management
```bash
python3 ~/.igsl-skills/skill.py health show        # all health scores
python3 ~/.igsl-skills/skill.py health alert       # only alerts (score < threshold)
python3 ~/.igsl-skills/skill.py health record META-01 --applied 1 --completed 1 --fallback 0
```

### Health formula
```
score = applied_rate × completion_rate × (1 - 0.5 × fallback_rate)
EMA update: new = α × observation + (1-α) × old_value  [α = 0.1]
Alert threshold: 0.60 (configurable per node)
```

### Add a new skill node
```bash
python3 ~/.igsl-skills/skill.py add \
  --id NEW-01 \
  --name "skill-name" \
  --type "skill" \
  --path "~/.igsl-skills/skills/category/name/SKILL.md" \
  --tags "tag1 tag2" \
  --hardness "soft-hook"
```

### Evolve a skill
```bash
python3 ~/.igsl-skills/skill.py evolve META-01 --mode FIX       # bug fix
python3 ~/.igsl-skills/skill.py evolve META-01 --mode DERIVED   # new variant
python3 ~/.igsl-skills/skill.py evolve META-01 --mode CAPTURED  # new skill from session
```

### Lineage (EvoGraph)
```bash
python3 ~/.igsl-skills/skill.py lineage META-01     # show ancestry chain
python3 ~/.igsl-skills/skill.py lineage --all       # full graph
```

### Bundle operations
```bash
python3 ~/.igsl-skills/skill.py bundle suggest "hms factor research"
python3 ~/.igsl-skills/skill.py bundle record S-01 --sessions 5 --success 4
```

### Access check (verify skill file matches registry commit)
```bash
python3 ~/.igsl-skills/skill.py access check META-01
```

### GC (remove deprecated nodes with no dependents)
```bash
python3 ~/.igsl-skills/skill.py gc --dry-run
python3 ~/.igsl-skills/skill.py gc
```

### Cascade check
```bash
python3 ~/.igsl-skills/hooks/cascade_watcher.py
python3 ~/.igsl-skills/hooks/cascade_watcher.py --json
python3 ~/.igsl-skills/hooks/cascade_watcher.py --fix
```

## Registry File
```
~/.igsl-skills/_registry_v2.yaml
```
Contains all 13 skill nodes with: name, type, path, tags, hardness, health, lineage, access, bundle, memory_nodes.

## Hardness Levels
| Level | Load behaviour |
|-------|---------------|
| hard | Always in context (460 tokens for all hard skills) |
| soft-hook | Load on keyword match in user message |
| explicit-import | Load only when directly referenced |
| project-hook | Load based on detected project |
