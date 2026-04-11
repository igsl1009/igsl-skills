# IGSL v2 — Personal Skill Graph for Claude Code

A self-improving skill and memory system that loads automatically into every [Claude Code](https://claude.ai/code) session. Claude knows what it knows, learns from sessions, and improves over time.

---

## What It Does

- **Always-on skills** — 3 hard skills load every session (auto-improve, memory-system, system-manager)
- **Soft skills** — 11 skills load on keyword match via `skill.py`
- **Memory graph** — Persistent nodes (DEC, PAT, LOOP, ERR, etc.) with BM25 search and weight decay
- **Session hooks** — Session start injects full context; session end scores quality (0–100) and auto-cleans on low scores
- **Dashboard** — Live visual dashboard at `http://127.0.0.1:8765/dashboard.html`
- **System manager** — `igsl_manage.py` for health checks, integrity, and maintenance

---

## Directory Structure

```
~/.igsl-skills/
├── skill.py              # Skill loader, scanner, health tracker
├── integrate.py          # Cross-system sync (memory ↔ skills)
├── igsl_manage.py        # System manager (status/check/links/fix-serr/gc)
├── dashboard.html        # Live visual dashboard (D3 + Chart.js)
├── _registry_v2.yaml     # Skill registry — all nodes, health, paths
│
├── skills/               # Skill definitions
│   └── meta/
│       ├── auto-improve/SKILL.md     # META-05 — gap detection + proposals
│       ├── memory-system/SKILL.md    # META-07 — memory node operations
│       └── system-manager/SKILL.md  # META-09 — health monitoring
│
├── memory/
│   ├── node.py           # Memory node CRUD, BM25 search, GC, fcntl locking
│   ├── nodes.jsonl       # Memory node store (JSONL)
│   ├── t0_identity.mem   # Permanent identity block (@imported in CLAUDE.md)
│   ├── t1_session.mem    # Live session block (written each session start)
│   └── active-index.json # Top active nodes by weight × recency
│
└── hooks/
    ├── session_start_v2.sh    # SessionStart hook — injects full context JSON
    ├── retrospective_v2.py    # Stop hook — quality score + auto-cleanup
    ├── session_quality.py     # 0–100 session scorer from journal events
    └── health_recorder.py     # PostToolUse hook — records skill health
```

---

## Installation

### 1. Clone to `~/.igsl-skills`

```bash
git clone https://github.com/igsl1009/igsl-skills ~/.igsl-skills
```

### 2. Add to `~/.claude/CLAUDE.md`

```
@~/.igsl-skills/memory/t0_identity.mem
@~/.igsl-skills/memory/t1_session.mem
@~/.igsl-skills/memory/active-index.json
@~/.igsl-skills/skills/meta/auto-improve/SKILL.md
@~/.igsl-skills/skills/meta/memory-system/SKILL.md
@~/.igsl-skills/skills/meta/system-manager/SKILL.md
```

### 3. Add hooks to `~/.claude/settings.json`

```json
{
  "hooks": {
    "SessionStart": [
      { "hooks": [{ "type": "command", "command": "bash ~/.igsl-skills/hooks/session_start_v2.sh" }] }
    ],
    "Stop": [
      { "hooks": [{ "type": "command", "command": "python3 ~/.igsl-skills/hooks/retrospective_v2.py" }] }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit|Bash",
        "hooks": [{ "type": "command", "command": "python3 ~/.igsl-skills/hooks/health_recorder.py" }]
      }
    ]
  }
}
```

### 4. Verify

```bash
python3 ~/.igsl-skills/igsl_manage.py check   # should print PASS
python3 ~/.igsl-skills/igsl_manage.py status  # full health report
```

---

## Tutorial

### 1. Check the system is alive

Start a new Claude Code session. The session start hook fires automatically and injects context. To verify:

```bash
python3 ~/.igsl-skills/igsl_manage.py check
# PASS

python3 ~/.igsl-skills/igsl_manage.py status
# Shows: registry version, skill count, memory nodes, health alerts, active index
```

Or just ask Claude in the session:
> "What IGSL skills are loaded right now?"

Claude should respond with META-05, META-07, META-09 and your session ID.

---

### 2. Store a memory node

When you make an important decision, learn something, or want to track a TODO — save it as a memory node. Claude can do this for you, or you can run it directly:

```bash
# A permanent decision (never decays)
python3 ~/.igsl-skills/memory/node.py add \
  --id DEC-001 \
  --type DEC \
  --tags "architecture api decision" \
  --content "Use REST not GraphQL for external API — simpler for mobile clients"

# A pattern you want to remember (decays after 30 days if unused)
python3 ~/.igsl-skills/memory/node.py add \
  --id PAT-001 \
  --type PAT \
  --tags "debugging pattern" \
  --content "PAT[+] When tests pass but prod fails: check mock/real DB divergence"

# An open TODO (stays active until you close it)
python3 ~/.igsl-skills/memory/node.py add \
  --id LOOP-001 \
  --type LOOP \
  --tags "feature todo" \
  --content "○ Add rate limiting to the /api/search endpoint"
```

Node IDs can use any prefix. Convention: use project prefix (e.g. `HMS-`, `OC-`, `GEN-`).

---

### 3. Search memory

Find relevant nodes using BM25 keyword search:

```bash
python3 ~/.igsl-skills/memory/node.py query "api authentication"
# Returns top-5 nodes scored by relevance × weight × recency
```

Or ask Claude:
> "What do you know about our API design decisions?"

Claude will query memory and surface relevant nodes.

---

### 4. Close a completed TODO

When a LOOP node is done:

```bash
python3 ~/.igsl-skills/memory/node.py close LOOP-001 --note "Done — rate limiter deployed"
```

The node is marked resolved and removed from the active index.

---

### 5. Work with skills

Skills are reusable instruction sets. Hard skills (META-05/07/09) always load. Soft skills load when relevant keywords appear.

```bash
# See all skills and their health scores
python3 ~/.igsl-skills/skill.py scan

# Find which skill covers a topic
python3 ~/.igsl-skills/skill.py query "quant research alpha"

# Manually load a soft skill into the current session
python3 ~/.igsl-skills/skill.py load S-01
```

To add your own skill, create a `SKILL.md` file and register it in `_registry_v2.yaml`:

```yaml
nodes:
  S-99:
    name: my-skill
    hardness: soft
    path: ~/.igsl-skills/skills/my-skill/SKILL.md
    trigger_keywords: ["keyword1", "keyword2"]
    health:
      alert_threshold: 0.6
```

---

### 6. View the dashboard

```bash
cd ~/.igsl-skills && python3 -m http.server 8765 &
open http://127.0.0.1:8765/dashboard.html
```

| View | What you see |
|------|-------------|
| Overview | Skill count, memory stats, health score, QA results |
| Skill Graph | D3 force graph — nodes = skills, edges = connections |
| Memory Network | D3 graph of memory nodes colored by type |
| Health | Per-skill health scores with applied/completion/fallback rates |
| Activity | Session journal timeline |
| QA | Test suite results (81 tests) |
| Settings | Registry config, paths, thresholds |

---

### 7. Run the QA test suite

```bash
python3 ~/.igsl-skills/igsl_v2_test_suite.py
# Should output: 81/81 PASS
```

Run this after making changes to the registry or core scripts to catch regressions.

---

### 8. Understand session end (retrospective)

When you end a Claude Code session, `retrospective_v2.py` fires automatically and:

1. Scores the session 0–100 based on journal events
2. Prints a quality badge (A/B/C/D/F)
3. If score < 50: auto-runs fix-serr, rebuilds memory index, re-checks integrity

Example output:
```
══════════════════════════════════════════════════════════
  IGSL v2 SESSION RETROSPECTIVE
  Session: 2026-04-10_143022_hms-crypto
  Session Quality: 🟢 87/100 — EXCELLENT (Grade A)
══════════════════════════════════════════════════════════
```

---

### 9. Maintenance

```bash
# Remove duplicate error nodes (same skill, multiple ERR records)
python3 ~/.igsl-skills/igsl_manage.py fix-serr

# Preview which memory nodes would be garbage-collected
python3 ~/.igsl-skills/memory/node.py gc --dry-run

# Actually GC (removes nodes with effective_weight < 0.05)
python3 ~/.igsl-skills/memory/node.py gc

# Verify all skill file paths in the registry still exist
python3 ~/.igsl-skills/igsl_manage.py links
```

---

### 10. Multi-account (Claude Swarm)

If you run multiple Claude Code accounts for parallel work, each needs the hooks and CLAUDE.md configured. Copy the setup to each account's config dir:

```bash
# Account A
mkdir -p ~/.claude-account-a/commands
cp ~/.claude/commands/igsl.md ~/.claude-account-a/commands/
# Add CLAUDE.md with @imports and hooks in settings.json — see Installation above
```

All accounts share the same `~/.igsl-skills/` directory — one memory graph, one registry, consistent state across instances.

---

## Key Commands

```bash
# System health
python3 ~/.igsl-skills/igsl_manage.py status    # full report
python3 ~/.igsl-skills/igsl_manage.py check     # integrity check (PASS/FAIL)
python3 ~/.igsl-skills/igsl_manage.py links     # verify all skill paths
python3 ~/.igsl-skills/igsl_manage.py fix-serr  # clean duplicate error nodes
python3 ~/.igsl-skills/igsl_manage.py gc        # garbage-collect old nodes

# Skills
python3 ~/.igsl-skills/skill.py scan            # list all skills + health
python3 ~/.igsl-skills/skill.py query 'topic'   # find relevant skills
python3 ~/.igsl-skills/skill.py load S-01       # load a soft skill

# Memory
python3 ~/.igsl-skills/memory/node.py active    # show active nodes
python3 ~/.igsl-skills/memory/node.py query 'keywords'  # BM25 search
python3 ~/.igsl-skills/memory/node.py add --id GEN-001 --type DEC --tags 'tag1 tag2' --content 'text'
python3 ~/.igsl-skills/memory/node.py gc --dry-run  # preview GC candidates
```

---

## Memory Node Types

| Type | Half-life | Purpose |
|------|-----------|---------|
| DEC  | ∞         | Permanent decisions, architectural choices |
| PAT  | 30d       | Patterns, recurring approaches |
| ARCH | 60d       | System architecture snapshots |
| ART  | 14d       | File/artifact references |
| LOOP | ∞ (until closed) | Open items, TODOs |
| GEN  | 90d       | General insights |
| ERR  | 180d      | Bug records, error patterns |

---

## Session Quality Scoring

The retrospective hook scores each session 0–100:

- **Deductions**: tool failures (−10 each, max −40), user corrections (−15, max −45), self-corrections (−20, max −40)
- **Gains**: pattern wins (+10, max +20), new knowledge edges (+5), gaps found (+5)
- **Auto-cleanup** triggers when score < 50 or ≥3 corrections or ≥5 failures

---

## Dashboard

Start a local server and open:

```bash
cd ~/.igsl-skills && python3 -m http.server 8765 &
open http://127.0.0.1:8765/dashboard.html
```

Views: Overview · Skill Graph · Memory Network · Health · Activity · QA · Settings

---

## Requirements

- Claude Code (any version)
- Python 3.9+
- `pyyaml` (`pip install pyyaml`)
- Optional: `sentence-transformers` for semantic memory search

---

## License

MIT
