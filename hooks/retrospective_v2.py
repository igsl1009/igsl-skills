#!/usr/bin/env python3
"""
IGSL Stop Hook v2 — retrospective_v2.py
Fires when Claude Code session ends.
Reads session journal, synthesises → memory nodes + skill evolutions.
MUST check stop_hook_active to prevent infinite loops.
"""

import json, sys, subprocess
from pathlib import Path
from datetime import date

IGSL     = Path.home() / ".igsl-skills"
PROPOSED = IGSL / "_proposed"
TODAY    = date.today().isoformat()


def main():
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}

    # CRITICAL: prevent infinite loop
    if payload.get("stop_hook_active"):
        sys.exit(0)

    session_file = Path("/tmp/igsl_session_id")
    if not session_file.exists():
        sys.exit(0)

    session_id = session_file.read_text().strip()
    journal_dir = IGSL / "_journal"

    journal = None
    if journal_dir.exists():
        candidates = list(journal_dir.glob(f"*{session_id[:16]}*.jsonl"))
        if candidates:
            journal = candidates[0]

    events = []
    if journal and journal.exists():
        for line in journal.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
                if e.get("type") != "session_start":
                    events.append(e)
            except json.JSONDecodeError:
                pass

    SEP = "═" * 58

    print(f"\n{SEP}")
    print(f"  IGSL v2 SESSION RETROSPECTIVE")
    print(f"  Session: {session_id}")
    print(f"  Events captured: {len(events)}")
    print(SEP)

    if not events:
        print("\n  No events this session. Nothing to synthesise.")
        print(f"{SEP}\n")
        sys.exit(0)

    print("\nRunning post-session synthesis...")
    try:
        cmd = [sys.executable, str(IGSL / "integrate.py"), "post-session"]
        if journal:
            cmd += ["--journal", str(journal)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.stdout:
            for line in result.stdout.splitlines():
                print(f"  {line}")
        if result.returncode != 0 and result.stderr:
            print(f"  [WARN] {result.stderr[:200]}")
    except subprocess.TimeoutExpired:
        print("  [WARN] Post-session synthesis timed out (120s)")
    except Exception as e:
        print(f"  [WARN] Post-session error: {e}")

    print("\nSkill health status:")
    try:
        alert_result = subprocess.run(
            [sys.executable, str(IGSL / "skill.py"), "health", "alert"],
            capture_output=True, text=True, timeout=15
        )
        for line in alert_result.stdout.splitlines():
            print(f"  {line}")
    except Exception:
        print("  (health check failed)")

    print("\nMemory active index:")
    try:
        idx_file = IGSL / "memory" / "active-index.json"
        if idx_file.exists():
            import json as _j
            idx = _j.loads(idx_file.read_text())
            nodes_str = " ".join(idx.get("nodes", [])[:10])
            print(f"  {nodes_str}")
    except Exception:
        print("  (index not available)")

    print("\nNext steps:")
    if PROPOSED.exists():
        proposals = list(PROPOSED.glob("*_proposals.json"))
        if proposals:
            latest = max(proposals, key=lambda p: p.stat().st_mtime)
            print(f"  Review proposals: python3 ~/.igsl-skills/hooks/apply_proposals.py {latest}")
        else:
            print("  No proposals generated this session")
    print(f"  Skill health:  python3 ~/.igsl-skills/skill.py health show")
    print(f"  Memory stats:  python3 ~/.igsl-skills/memory/node.py show")

    print(f"\n{SEP}\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
