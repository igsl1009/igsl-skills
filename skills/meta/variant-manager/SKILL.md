# META-06 — Variant Manager
**id**: META-06 | **hardness**: hard | **type**: meta

## Purpose
Manage skill variants: A/B testing approaches, maintaining multiple versions of a skill, promoting winners, deprecating losers. Tracks which skill variant performs best across sessions.

## Trigger Keywords
`variant`, `version`, `a/b test`, `compare approaches`, `which is better`, `skill version`, `promote`, `deprecate`

## Activation
Always loaded (hard skill). Derived from META-03 (graph-manager) via EvoGraph DERIVED edge.

## Variant Concepts

### What is a variant?
A variant is a DERIVED evolution of a parent skill with a different approach to the same problem. Example:
- `S-01` — base quant-research skill
- `S-01-v2` — variant with revised IC calculation method
- `S-01-momentum` — momentum-specific specialization

### Variant Registry
Variants are tracked via EvoGraph lineage:
```bash
python3 ~/.igsl-skills/skill.py lineage S-01
# Shows: S-01 → S-01-v2 (DERIVED) → S-01-momentum (DERIVED)
```

## Variant Operations

### Create a variant
```bash
python3 ~/.igsl-skills/skill.py evolve S-01 --mode DERIVED --name "S-01-v2" \
  --delta "Revised IC window from 252d to 126d for faster regime adaptation"
```

### Track variant health
```bash
python3 ~/.igsl-skills/skill.py health show --filter "S-01"
# Shows health scores for S-01 and all its variants
```

### A/B Test Protocol
1. Run parent skill for N sessions → record health
2. Create DERIVED variant with modified approach
3. Run variant for N sessions → record health
4. Compare scores: `health_score(variant) vs health_score(parent)`
5. If variant wins by >10%: promote (deprecate parent)
6. If parent wins: deprecate variant

### Promote a variant
```bash
# Mark old version deprecated
python3 ~/.igsl-skills/skill.py evolve S-01 --mode FIX --deprecate

# Make variant the canonical version (rename in registry)
# Edit _registry_v2.yaml: change S-01-v2 id to S-01, update lineage
```

### Deprecate a skill
```yaml
# In _registry_v2.yaml:
S-01-old:
  deprecated: true
  deprecated_reason: "superseded by S-01-v2 (higher IC consistency)"
  deprecated_date: "2026-04-09"
```

## Variant Naming Convention
- Feature variant: `{parent-id}-{feature}` (e.g., `S-01-momentum`)
- Version variant: `{parent-id}-v{N}` (e.g., `S-01-v2`)
- Fix variant: same ID, new lineage entry with mode=FIX

## Bundle Compatibility
When a skill is part of a bundle and gets deprecated:
```bash
python3 ~/.igsl-skills/skill.py bundle suggest "hms research"
# Automatically excludes deprecated nodes from suggestions
```

## Rules
- Never delete a skill — only deprecate
- Keep deprecated nodes in registry for lineage tracing
- A/B test minimum: 3 sessions each before deciding winner
- Document the reason for deprecation in `deprecated_reason`
