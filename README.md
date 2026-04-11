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
