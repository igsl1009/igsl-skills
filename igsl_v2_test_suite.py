#!/usr/bin/env python3
"""IGSL v2 Unit Test Suite — igsl_v2_test_suite.py
Tests skill.py health system via CLI (_health_record command) and direct imports.
"""

import json, sys, subprocess, tempfile, shutil, unittest
from pathlib import Path

IGSL     = Path.home() / ".igsl-skills"
SKILL_PY = IGSL / "skill.py"
INTEG_PY = IGSL / "integrate.py"

def run(cmd, **kw):
    r = subprocess.run(cmd, shell=isinstance(cmd, str),
                       capture_output=True, text=True, timeout=15, **kw)
    return r.returncode, r.stdout, r.stderr

# Import skill module functions directly
sys.path.insert(0, str(IGSL))
import skill as sk


# ── helpers ──────────────────────────────────────────────────────────────────

def fresh_health(**overrides) -> dict:
    h = {"applied_rate": 0.5, "completion_rate": 0.5, "fallback_rate": 0.0,
         "health_score": 0.25, "alert_threshold": 0.60, "total_applications": 0,
         "token_cost_avg": 300, "last_applied": "2026-01-01"}
    h.update(overrides)
    return h


# ── TestHealthScore ───────────────────────────────────────────────────────────

class TestHealthScore(unittest.TestCase):

    def test_formula_perfect(self):
        h = {"applied_rate": 1.0, "completion_rate": 1.0, "fallback_rate": 0.0}
        self.assertAlmostEqual(sk.health_score(h), 1.0)

    def test_formula_zero_applied(self):
        h = {"applied_rate": 0.0, "completion_rate": 1.0, "fallback_rate": 0.0}
        self.assertAlmostEqual(sk.health_score(h), 0.0)

    def test_formula_fallback_penalty(self):
        # ar=1, cr=1, fr=1 → 1 * 1 * (1 - 0.5) = 0.5
        h = {"applied_rate": 1.0, "completion_rate": 1.0, "fallback_rate": 1.0}
        self.assertAlmostEqual(sk.health_score(h), 0.5)

    def test_formula_typical(self):
        # ar=0.8, cr=0.92, fr=0.08 → 0.8 * 0.92 * (1 - 0.04) = 0.7066…
        h = {"applied_rate": 0.8, "completion_rate": 0.92, "fallback_rate": 0.08}
        result = sk.health_score(h)
        self.assertGreater(result, 0.70)
        self.assertLess(result, 0.72)

    def test_missing_keys_defaults(self):
        # Empty dict → 0.5 * 0.5 * 1.0 = 0.25
        self.assertAlmostEqual(sk.health_score({}), 0.25)


# ── TestHealthEMA ─────────────────────────────────────────────────────────────

class TestHealthEMA(unittest.TestCase):

    def test_applied_increments_rate(self):
        h = fresh_health(applied_rate=0.5)
        sk.update_health_ema(h, applied=True, completed=True, fallback=False)
        self.assertGreater(h["applied_rate"], 0.5)

    def test_not_applied_decrements_rate(self):
        h = fresh_health(applied_rate=0.5)
        sk.update_health_ema(h, applied=False, completed=False, fallback=False)
        self.assertLess(h["applied_rate"], 0.5)

    def test_total_applications_increments(self):
        h = fresh_health()
        sk.update_health_ema(h, applied=True, completed=True, fallback=False)
        self.assertEqual(h["total_applications"], 1)
        sk.update_health_ema(h, applied=True, completed=True, fallback=False)
        self.assertEqual(h["total_applications"], 2)

    def test_health_floor_prevents_zero(self):
        """Even with all-zero rates, health_score must be >= 0.05."""
        h = fresh_health(applied_rate=0.0, completion_rate=0.0, fallback_rate=1.0)
        for _ in range(50):
            sk.update_health_ema(h, applied=False, completed=False, fallback=True)
        self.assertGreaterEqual(h["health_score"], 0.05,
            f"health_score fell below floor: {h['health_score']}")

    def test_health_score_stored_in_dict(self):
        h = fresh_health()
        sk.update_health_ema(h, applied=True, completed=True, fallback=False)
        self.assertIn("health_score", h)
        self.assertAlmostEqual(h["health_score"], sk.health_score(h))

    def test_alpha_convergence(self):
        """100 perfect applies should push health_score above 0.9."""
        h = fresh_health()
        for _ in range(100):
            sk.update_health_ema(h, applied=True, completed=True, fallback=False)
        self.assertGreater(h["health_score"], 0.9)


# ── TestHealthRecordCLI ───────────────────────────────────────────────────────

class TestHealthRecordCLI(unittest.TestCase):
    """Tests via CLI: python3 skill.py health record — NOT direct update_health_ema."""

    def test_record_success_exit0(self):
        rc, out, err = run([sys.executable, str(SKILL_PY), "health", "record",
                            "META-05", "--applied", "1", "--completed", "1", "--fallback", "0"])
        self.assertEqual(rc, 0, f"stderr: {err}")

    def test_record_prints_bar(self):
        rc, out, _ = run([sys.executable, str(SKILL_PY), "health", "record",
                          "S-01", "--applied", "1", "--completed", "1", "--fallback", "0"])
        self.assertEqual(rc, 0)
        self.assertIn("█", out)

    def test_record_failure_updates_health(self):
        """Failure apply should decrease health over 5 calls (or keep above floor)."""
        import yaml
        reg = yaml.safe_load((IGSL / "_registry_v2.yaml").read_text())
        before = sk.health_score(reg["nodes"]["S-01"].get("health", {}))

        for _ in range(5):
            run([sys.executable, str(SKILL_PY), "health", "record",
                 "S-01", "--applied", "0", "--completed", "0", "--fallback", "1"])

        reg2 = yaml.safe_load((IGSL / "_registry_v2.yaml").read_text())
        after = sk.health_score(reg2["nodes"]["S-01"].get("health", {}))
        self.assertGreaterEqual(after, 0.05, f"health fell below floor: {after}")

    def test_record_unknown_id_exits_nonzero(self):
        rc, out, err = run([sys.executable, str(SKILL_PY), "health", "record", "NONEXIST-999"])
        self.assertNotEqual(rc, 0)

    def test_record_increments_total_applications(self):
        import yaml
        reg_before = yaml.safe_load((IGSL / "_registry_v2.yaml").read_text())
        t_before = reg_before["nodes"]["META-07"].get("health", {}).get("total_applications", 0)

        run([sys.executable, str(SKILL_PY), "health", "record",
             "META-07", "--applied", "1", "--completed", "1"])

        reg_after = yaml.safe_load((IGSL / "_registry_v2.yaml").read_text())
        t_after = reg_after["nodes"]["META-07"].get("health", {}).get("total_applications", 0)
        self.assertEqual(t_after, t_before + 1)


# ── TestSerrDedup ─────────────────────────────────────────────────────────────

class TestSerrDedup(unittest.TestCase):
    """Verify integrate.py health-sync doesn't create duplicate SERR nodes."""

    def _count_serr(self) -> int:
        from pathlib import Path
        nodes_text = (IGSL / "memory" / "nodes.jsonl").read_text()
        return nodes_text.count('"SERR-')

    def test_double_sync_no_new_serr(self):
        """Running health-sync twice must not double SERR nodes."""
        run([sys.executable, str(INTEG_PY), "health-sync"])
        count_after_first  = self._count_serr()
        run([sys.executable, str(INTEG_PY), "health-sync"])
        count_after_second = self._count_serr()
        self.assertEqual(count_after_first, count_after_second,
            f"SERR count grew: {count_after_first} → {count_after_second} (dedup broken)")


# ── TestEvograph ──────────────────────────────────────────────────────────────

class TestEvograph(unittest.TestCase):

    def test_valid_jsonl(self):
        evo_path = IGSL / "_evograph.jsonl"
        self.assertTrue(evo_path.exists())
        for i, line in enumerate(evo_path.read_text().splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                json.loads(line)
            except json.JSONDecodeError as e:
                self.fail(f"Invalid JSON on line {i+1}: {e}")

    def test_no_stress_contamination(self):
        evo_path = IGSL / "_evograph.jsonl"
        for line in evo_path.read_text().splitlines():
            self.assertNotIn("stress_test", line.lower(),
                f"stress contamination in evograph: {line[:80]}")

    def test_gen_err_entry_present(self):
        text = (IGSL / "_evograph.jsonl").read_text()
        self.assertIn("GEN-ERR-001", text)
        self.assertIn("pattern-capture", text)


# ── main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
