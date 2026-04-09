#!/usr/bin/env bash
# IGSL SessionStart Hook v2 — session_start_v2.sh
# Fires at start of each Claude Code session.
# MUST output valid JSON with additionalContext key.

set -e

IGSL="$HOME/.igsl-skills"
MEM="$IGSL/memory"
TODAY=$(date -u +%Y-%m-%d)
TS=$(date -u +%H%M%S)
DIR_STEM=$(basename "$PWD" | tr ' ' '_' | tr '[:upper:]' '[:lower:]' | cut -c1-20)
SESSION_ID="${TODAY}_${TS}_${DIR_STEM}"

# ── 1. Record session ID ─────────────────────────────────────────────────────
echo "$SESSION_ID" > /tmp/igsl_session_id
mkdir -p "$IGSL/_journal"
JOURNAL="$IGSL/_journal/${SESSION_ID}.jsonl"
echo "{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"type\":\"session_start\",\"session_id\":\"${SESSION_ID}\",\"cwd\":\"$PWD\"}" \
  >> "$JOURNAL" 2>/dev/null || true

# ── 2. Detect project ────────────────────────────────────────────────────────
PROJECT_TAG="general"
PWD_LOWER=$(echo "$PWD" | tr '[:upper:]' '[:lower:]')
GIT_REMOTE=$(git remote get-url origin 2>/dev/null | tr '[:upper:]' '[:lower:]' || echo "")

for hint in "hms" "execution" "trading" "binance" "quant"; do
  if echo "$PWD_LOWER $GIT_REMOTE" | grep -q "$hint"; then
    PROJECT_TAG="hms"; break
  fi
done

if [ "$PROJECT_TAG" = "general" ]; then
  for hint in "openclaude" "telegram" "openclaw"; do
    if echo "$PWD_LOWER $GIT_REMOTE" | grep -q "$hint"; then
      PROJECT_TAG="openclaude"; break
    fi
  done
fi

if [ "$PROJECT_TAG" = "general" ]; then
  for hint in "igsl-skills" "skill" "registry" "graph"; do
    if echo "$PWD_LOWER $GIT_REMOTE" | grep -q "$hint"; then
      PROJECT_TAG="skill-graph"; break
    fi
  done
fi

if [ "$PROJECT_TAG" = "general" ]; then
  for hint in "fina" "math" "rmsc" "csci" "eltu" "cuhk" "coursework"; do
    if echo "$PWD_LOWER $GIT_REMOTE" | grep -q "$hint"; then
      PROJECT_TAG="coursework"; break
    fi
  done
fi

# ── 3. Git context ───────────────────────────────────────────────────────────
GIT_BRANCH=$(git branch --show-current 2>/dev/null | head -c 30 || echo "no-git")
GIT_LAST=$(git log --oneline -1 2>/dev/null | head -c 60 || echo "no-commits")
DIRTY=$(git diff --name-only 2>/dev/null | head -3 | tr '\n' ' ' | head -c 80 || echo "")

# ── 4. Rebuild memory active index ──────────────────────────────────────────
python3 "$MEM/node.py" active > /dev/null 2>&1 || true

# ── 5. Run skill meta-scan ───────────────────────────────────────────────────
python3 "$IGSL/skill.py" scan --session-start > /dev/null 2>&1 || true

# ── 6. Health sync ───────────────────────────────────────────────────────────
python3 "$IGSL/integrate.py" health-sync > /dev/null 2>&1 || true

# ── 7. Get alert count ───────────────────────────────────────────────────────
ALERT_COUNT=$(python3 "$IGSL/skill.py" health alert 2>/dev/null | grep "⚠" | wc -l | tr -d ' ')

# ── 8. Get active memory nodes (top-5 brief) ─────────────────────────────────
ACTIVE_NODES=$(python3 "$MEM/node.py" active 2>/dev/null | tail -5 | \
               sed 's/"/\\"/g' | tr '\n' '|' | sed 's/|/\\n/g' || echo "")

# ── 9. Load T0 identity content ──────────────────────────────────────────────
T0_CONTENT=$(head -8 "$MEM/t0_identity.mem" 2>/dev/null | \
             sed 's/"/\\"/g' | \
             tr '\n' '|' | \
             sed 's/|/\\n/g' || echo "T0: not found")

# ── 10. Build and emit additionalContext JSON ────────────────────────────────
cat << ENDJSON
{
  "additionalContext": "${T0_CONTENT}\\n\\nACTIVE MEMORY NODES:\\n${ACTIVE_NODES}\\n\\nSESSION: ${SESSION_ID}\\nPROJECT: ${PROJECT_TAG}\\nGIT: branch=${GIT_BRANCH} | last: ${GIT_LAST}\\nDIRTY: ${DIRTY:-none}\\nHEALTH ALERTS: ${ALERT_COUNT}\\n\\nSKILL SYSTEM:\\n- Meta-scan: ~/.igsl-skills/_meta_scan.md\\n- Hard skills loaded: META-05 (auto-improve) META-07 (memory-system)\\n- Soft skills: load on keyword match via skill.py load\\n\\nMEMORY WRITE PROTOCOL (use during session):\\n  DEC: python3 ~/.igsl-skills/memory/node.py add --id PREFIX-NNN --type DEC --tags 't1 t2' --content '<120 chars>' --src $(cat /tmp/igsl_session_id 2>/dev/null | head -c 6)\\n  PAT: same but --type PAT --content 'PAT[+/-/!] ...'\\n  LOOP: same but --type LOOP --content '○ task description'\\n  close: python3 ~/.igsl-skills/memory/node.py close LOOP-ID --note 'done'\\n  query: python3 ~/.igsl-skills/memory/node.py query 'keywords'\\n\\nSKILL LOAD PROTOCOL (only load on keyword match):\\n  check: python3 ~/.igsl-skills/skill.py query 'keywords'\\n  load: python3 ~/.igsl-skills/skill.py load S-01\\n  cross: python3 ~/.igsl-skills/integrate.py memory-to-skills 'keywords'\\n\\nNEVER write memory as prose. NEVER load skills without keyword match."
}
ENDJSON
