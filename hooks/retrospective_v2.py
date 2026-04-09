#!/usr/bin/env python3
"""
IGSL Stop Hook v2 — retrospective_v2.py (with session quality + auto-cleanup)
Fires when Claude Code session ends.
  1. Score session quality (0-100)
  2. Run post-session memory+skill sync
  3. Auto-cleanup if quality < 50 or errors detected
  4. Print summary with quality badge
MUST check stop_hook_active to prevent infinite loop.
"""
import json, sys, subprocess
from pathlib import Path
from datetime import date

IGSL     = Path.home() / ".igsl-skills"
PROPOSED = IGSL / "_proposed"
HOOKS    = IGSL / "hooks"
TODAY    = date.today().isoformat()


def _run(cmd, timeout=30):
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout
    )


def main():
    # Read stdin payload
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}

    # CRITICAL: prevent infinite loop
    if payload.get("stop_hook_active"):
        sys.exit(0)

    # ── Find session journal ────────────────────────────────────────
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

    # ── Compute session quality ─────────────────────────────────────
    try:
        import sys as _sys
        _sys.path.insert(0, str(HOOKS))
        from session_quality import score_session, format_quality_report
        quality = score_session(journal)
    except Exception:
        # Fallback: no quality scoring available
        class _Q:
            score = 70; grade = "B"; badge = "GOOD"; needs_cleanup = False
            cleanup_reasons = []; reasons = []; gains = []
            icon = "🟡"
            def grade_from_score(self):
                return self.grade, self.badge, self.icon
        quality = _Q()
        def format_quality_report(q, verbose=True):
            return f"\n  Session Quality: {q.icon} {q.score}/100 — {q.badge} (Grade {q.grade})"

    # ── Header ──────────────────────────────────────────────────────
    SEP = "═" * 58
    print(f"\n{SEP}")
    print(f"  IGSL v2 SESSION RETROSPECTIVE")
    print(f"  Session: {session_id[:40]}")
    print(format_quality_report(quality, verbose=True))
    print(SEP)

    # ── Post-session sync ───────────────────────────────────────────
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
            except Exception:
                pass

    if events:
        print(f"\nProcessing {len(events)} journal event(s)...")
        try:
            cmd = [sys.executable, str(IGSL / "integrate.py"), "post-session"]
            if journal:
                cmd += ["--journal", str(journal)]
            r = _run(cmd, timeout=120)
            for line in r.stdout.splitlines():
                print(f"  {line}")
            if r.returncode != 0 and r.stderr:
                print(f"  [WARN] {r.stderr[:120]}")
        except subprocess.TimeoutExpired:
            print("  [WARN] Post-session timed out (120s)")
        except Exception as e:
            print(f"  [WARN] Post-session error: {e}")
    else:
        print("\nNo events to process.")

    # ── AUTO-CLEANUP (quality < 50 or explicit triggers) ───────────
    if quality.needs_cleanup:
        CSEP = "─" * 58
        print(f"\n{CSEP}")
        print(f"  AUTO-CLEANUP  (quality={quality.score}/100)")
        print(CSEP)

        # 1. Fix duplicate SERR nodes
        print("\n  [1/4] Removing duplicate SERR nodes...")
        try:
            r = _run([sys.executable, str(IGSL / "igsl_manage.py"), "fix-serr"], timeout=30)
            for line in r.stdout.splitlines():
                print(f"        {line}")
        except Exception as e:
            print(f"        [SKIP] {e}")

        # 2. Rebuild active memory index
        print("\n  [2/4] Rebuilding active memory index...")
        try:
            r = _run([sys.executable, str(IGSL / "memory" / "node.py"), "active"], timeout=20)
            idx_file = IGSL / "memory" / "active-index.json"
            if idx_file.exists():
                idx = json.loads(idx_file.read_text())
                print(f"        Index rebuilt: {len(idx.get('nodes', []))} nodes")
        except Exception as e:
            print(f"        [SKIP] {e}")

        # 3. System integrity check
        print("\n  [3/4] Running system integrity check...")
        try:
            r = _run([sys.executable, str(IGSL / "igsl_manage.py"), "check"], timeout=20)
            result_line = r.stdout.strip().splitlines()[0] if r.stdout.strip() else "(no output)"
            print(f"        {result_line}")
            if r.returncode != 0:
                print(f"        ⚠ FAILED — run: python3 ~/.igsl-skills/igsl_manage.py status")
        except Exception as e:
            print(f"        [SKIP] {e}")

        # 4. Skill health alerts
        print("\n  [4/4] Checking skill health alerts...")
        try:
            r = _run([sys.executable, str(IGSL / "skill.py"), "health", "alert"], timeout=15)
            for line in r.stdout.splitlines():
                print(f"        {line}")
        except Exception as e:
            print(f"        [SKIP] {e}")

    else:
        # Normal path: just show health
        print("\nSkill health:")
        try:
            r = _run([sys.executable, str(IGSL / "skill.py"), "health", "alert"], timeout=15)
            out = r.stdout.strip()
            if "All skills above" in out or not out:
                print(f"  ✓ All skills above threshold")
            else:
                for line in out.splitlines():
                    print(f"  {line}")
        except Exception as e:
            print(f"  [SKIP] {e}")

    # ── Pending proposals ───────────────────────────────────────────
    if PROPOSED.exists():
        proposals = sorted(PROPOSED.glob("*_proposals.json"),
                           key=lambda p: p.stat().st_mtime, reverse=True)
        if proposals:
            try:
                props = json.loads(proposals[0].read_text())
                print(f"\nPending proposals ({len(props)}):")
                for p in props[:3]:
                    print(f"  [{p.get('type','?')}] {p.get('summary','')}")
                print(f"  Review: python3 ~/.igsl-skills/hooks/apply_proposals.py --latest")
            except Exception:
                pass

    # ── Active memory ───────────────────────────────────────────────
    try:
        idx_file = IGSL / "memory" / "active-index.json"
        if idx_file.exists():
            idx = json.loads(idx_file.read_text())
            top = " ".join(idx.get("nodes", [])[:8])
            if top:
                print(f"\nActive memory: {top}")
    except Exception:
        pass

    # ── Footer ──────────────────────────────────────────────────────
    cleanup_str = "YES" if quality.needs_cleanup else "no"
    print(f"\n  Cleanup ran: {cleanup_str}")
    print(f"  Management:  python3 ~/.igsl-skills/igsl_manage.py status")
    print(f"  Dashboard:   http://127.0.0.1:8765/dashboard.html")
    print(f"{SEP}\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
