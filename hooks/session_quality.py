#!/usr/bin/env python3
"""
IGSL Session Quality Scorer — session_quality.py
Analyzes session journal events to compute a quality score 0–100.

Score interpretation:
  90-100: EXCELLENT — clean session, no issues       🟢
  75-89:  GOOD      — minor issues                   🟢
  60-74:  ADEQUATE  — some corrections               🟡
  45-59:  POOR      — auto-cleanup runs              🟠
  0-44:   FAILED    — full cleanup + alert           🔴

Event types recognized in journal:
  tool_failure     (-10 each, max -40)
  correction       (-15 each, max -45)  user corrected Claude
  self_correction  (-20 each, max -40)  Claude self-corrected
  pattern_fail     (-5 each, max -20)   anti-pattern violated
  pattern_win      (+10 each, max +20)  pattern applied successfully
  new_edge         (+5 each, max +15)   new knowledge connection found
  gap_found        (+5 each, max +10)   skill gap documented
"""

import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class SessionQuality:
    """Result of quality analysis."""
    score: int = 100
    grade: str = "A"
    badge: str = "EXCELLENT"
    icon: str = "🟢"
    reasons: List[str] = field(default_factory=list)
    gains: List[str] = field(default_factory=list)
    needs_cleanup: bool = False
    cleanup_reasons: List[str] = field(default_factory=list)

    def grade_from_score(self) -> Tuple[str, str, str]:
        if self.score >= 90: return "A", "EXCELLENT",  "🟢"
        if self.score >= 75: return "B", "GOOD",       "🟢"
        if self.score >= 60: return "C", "ADEQUATE",   "🟡"
        if self.score >= 45: return "D", "POOR",       "🟠"
        return "F", "FAILED", "🔴"


def score_session(journal_path: Path) -> SessionQuality:
    """Compute quality score from session journal JSONL."""
    q = SessionQuality()

    if not journal_path or not journal_path.exists():
        q.score = 0
        q.reasons = ["No journal found"]
        q.grade, q.badge, q.icon = q.grade_from_score()
        return q

    events = []
    for line in journal_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
            if e.get("type") != "session_start":
                events.append(e)
        except Exception:
            pass

    if not events:
        q.score = 50
        q.reasons = ["No events recorded (session may have been trivial)"]
        q.grade, q.badge, q.icon = q.grade_from_score()
        return q

    # Count event types
    counts: dict = {}
    for e in events:
        t = e.get("type", "unknown")
        counts[t] = counts.get(t, 0) + 1

    score = 100

    # ── Deductions ────────────────────────────────────────────────
    tool_failures = counts.get("tool_failure", 0)
    if tool_failures > 0:
        deduction = min(40, tool_failures * 10)
        score -= deduction
        q.reasons.append(f"{tool_failures} tool failure(s) (−{deduction})")

    corrections = counts.get("correction", 0)
    if corrections > 0:
        deduction = min(45, corrections * 15)
        score -= deduction
        q.reasons.append(f"{corrections} user correction(s) (−{deduction})")

    self_corrections = counts.get("self_correction", 0)
    if self_corrections > 0:
        deduction = min(40, self_corrections * 20)
        score -= deduction
        q.reasons.append(f"{self_corrections} self-correction(s) (−{deduction})")

    pattern_fails = counts.get("pattern_fail", 0)
    if pattern_fails > 0:
        deduction = min(20, pattern_fails * 5)
        score -= deduction
        q.reasons.append(f"{pattern_fails} anti-pattern violation(s) (−{deduction})")

    # ── Gains ─────────────────────────────────────────────────────
    pattern_wins = counts.get("pattern_win", 0)
    if pattern_wins > 0:
        gain = min(20, pattern_wins * 10)
        score = min(100, score + gain)
        q.gains.append(f"{pattern_wins} pattern win(s) (+{gain})")

    new_edges = counts.get("new_edge", 0)
    if new_edges > 0:
        gain = min(15, new_edges * 5)
        score = min(100, score + gain)
        q.gains.append(f"{new_edges} new edge(s) discovered (+{gain})")

    gaps_found = counts.get("gap_found", 0)
    if gaps_found > 0:
        gain = min(10, gaps_found * 5)
        score = min(100, score + gain)
        q.gains.append(f"{gaps_found} gap(s) documented (+{gain})")

    q.score = max(0, min(100, score))
    q.grade, q.badge, q.icon = q.grade_from_score()

    # ── Cleanup triggers ──────────────────────────────────────────
    if corrections + self_corrections >= 3:
        q.needs_cleanup = True
        q.cleanup_reasons.append(
            f"{corrections + self_corrections} corrections → rebuild indices"
        )

    if tool_failures >= 5:
        q.needs_cleanup = True
        q.cleanup_reasons.append(f"{tool_failures} tool failures → rebuild indices")

    if q.score < 50:
        q.needs_cleanup = True
        q.cleanup_reasons.append(f"Quality score {q.score} < 50 → full cleanup")

    return q


def format_quality_report(q: SessionQuality, verbose: bool = True) -> str:
    grade_str, badge_str, icon = q.grade_from_score()
    lines = [
        f"\n  Session Quality: {icon} {q.score}/100 — {badge_str} (Grade {q.grade})"
    ]

    if verbose:
        if q.reasons:
            lines.append("\n  Issues:")
            for r in q.reasons:
                lines.append(f"    − {r}")
        if q.gains:
            lines.append("\n  Gains:")
            for g in q.gains:
                lines.append(f"    + {g}")
        if q.needs_cleanup:
            lines.append("\n  Auto-cleanup triggered:")
            for r in q.cleanup_reasons:
                lines.append(f"    → {r}")

    return "\n".join(lines)


if __name__ == "__main__":
    # Quick self-test
    import tempfile, sys
    tmp = Path(tempfile.mktemp(suffix=".jsonl"))
    events = [
        {"type": "session_start", "session_id": "test"},
        {"type": "correction", "what_was_wrong": "x", "what_is_correct": "y"},
        {"type": "tool_failure", "tool": "Bash"},
        {"type": "pattern_win", "pattern": "async gather 3x faster"},
    ]
    tmp.write_text("\n".join(json.dumps(e) for e in events))
    q = score_session(tmp)
    print(format_quality_report(q))
    print(f"needs_cleanup={q.needs_cleanup}")
    tmp.unlink()
    sys.exit(0 if q.score > 0 else 1)
