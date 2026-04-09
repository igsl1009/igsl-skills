#!/usr/bin/env python3
"""
IGSL Cascade Watcher v2 — cascade_watcher.py
Detects external changes that may invalidate skills.

Usage:
  python3 cascade_watcher.py
  python3 cascade_watcher.py --json
  python3 cascade_watcher.py --fix
"""

import json, sys, argparse, subprocess, time
from pathlib import Path
from datetime import date

IGSL     = Path.home() / ".igsl-skills"
REGISTRY = IGSL / "_registry_v2.yaml"
TODAY    = date.today().isoformat()


def load_registry() -> dict:
    if not REGISTRY.exists():
        return {"nodes": {}}
    try:
        import yaml
        with open(REGISTRY, encoding="utf-8") as f:
            return yaml.safe_load(f) or {"nodes": {}}
    except ImportError:
        json_r = IGSL / "_registry_v2.json"
        if json_r.exists():
            return json.loads(json_r.read_text(encoding="utf-8"))
        return {"nodes": {}}


def health_score(h: dict) -> float:
    ar = float(h.get("applied_rate", 0.5))
    cr = float(h.get("completion_rate", 0.5))
    fr = float(h.get("fallback_rate", 0.0))
    return ar * cr * (1.0 - 0.5 * fr)


def find_dependents(nid: str, nodes: dict) -> list:
    deps = []
    for sid, n in nodes.items():
        if sid == nid:
            continue
        if (nid in n.get("connects_to", []) or
            nid in n.get("cross_applies", []) or
            nid in n.get("memory_nodes", [])):
            deps.append(sid)
    return deps


def check_mcp_modifications(nodes: dict) -> list:
    issues = []
    now = time.time()
    for nid, n in nodes.items():
        if n.get("type") not in ("mcp", "connector"):
            continue
        path_str = n.get("path", "").replace("~", str(Path.home()))
        if path_str.startswith("remote:") or path_str.startswith("http"):
            continue
        path = Path(path_str)
        if not path.exists():
            issues.append({
                "node": nid,
                "name": n.get("name", "?"),
                "severity": "warning",
                "reason": f"MCP file not found: {path}",
                "dependent_skills": find_dependents(nid, nodes)
            })
            continue
        age_days = (now - path.stat().st_mtime) / 86400
        if age_days < 7:
            issues.append({
                "node": nid,
                "name": n.get("name", "?"),
                "severity": "info",
                "reason": f"MCP file modified {age_days:.1f}d ago — verify skill still valid",
                "dependent_skills": find_dependents(nid, nodes)
            })
    return issues


def check_git_drift(nodes: dict) -> list:
    issues = []
    for nid, n in nodes.items():
        if n.get("deprecated"):
            continue
        access = n.get("access", {})
        src_commit = access.get("source_commit", "000000")
        if src_commit in ("000000", "?", ""):
            continue
        path_str = n.get("path", "").replace("~", str(Path.home()))
        path = Path(path_str)
        if not path.exists():
            continue
        try:
            result = subprocess.run(
                ["git", "log", "--oneline", "-1", "--", str(path)],
                capture_output=True, text=True, cwd=str(IGSL), timeout=5
            )
            if result.stdout.strip():
                current = result.stdout.strip().split()[0]
                if current != src_commit:
                    issues.append({
                        "node": nid,
                        "name": n.get("name", "?"),
                        "severity": "warning",
                        "reason": f"Drift detected: registered={src_commit[:7]} current={current[:7]}",
                        "fix": f"python3 ~/.igsl-skills/skill.py access check {nid}"
                    })
        except Exception:
            pass
    return issues


def check_health_degradation(nodes: dict) -> list:
    issues = []
    for nid, n in nodes.items():
        if n.get("deprecated"):
            continue
        h = n.get("health", {})
        score = health_score(h)
        thresh = h.get("alert_threshold", 0.60)
        if score < thresh:
            issues.append({
                "node": nid,
                "name": n.get("name", "?"),
                "severity": "alert",
                "reason": f"Health {score:.2f} < threshold {thresh:.2f}",
                "fix": f"python3 ~/.igsl-skills/skill.py evolve {nid} --mode FIX",
                "dependent_skills": find_dependents(nid, nodes)
            })
    return issues


def check_dependent_cascade(issues: list, nodes: dict) -> list:
    cascade_issues = []
    affected_directly = {i["node"] for i in issues}
    for issue in issues:
        for dep_id in issue.get("dependent_skills", []):
            if dep_id not in affected_directly:
                n = nodes.get(dep_id, {})
                cascade_issues.append({
                    "node": dep_id,
                    "name": n.get("name", "?"),
                    "severity": "cascade",
                    "reason": f"Depends on {issue['node']} ({issue.get('name','?')}) which has issues",
                    "fix": f"python3 ~/.igsl-skills/skill.py evolve {dep_id} --mode FIX --trigger cascade"
                })
                affected_directly.add(dep_id)
    return cascade_issues


def run(args):
    reg = load_registry()
    nodes = reg.get("nodes", {})

    all_issues = []
    all_issues += check_mcp_modifications(nodes)
    all_issues += check_git_drift(nodes)
    all_issues += check_health_degradation(nodes)

    primary_issues = [i for i in all_issues if i.get("severity") in ("alert", "warning")]
    cascade_issues = check_dependent_cascade(primary_issues, nodes)
    all_issues += cascade_issues

    if getattr(args, "json_output", False):
        print(json.dumps(all_issues, indent=2))
        return

    if not all_issues:
        print(f"✓ Cascade check: no issues detected [{TODAY}]")
        return

    by_sev = {"alert": [], "warning": [], "cascade": [], "info": []}
    for issue in all_issues:
        sev = issue.get("severity", "info")
        by_sev.setdefault(sev, []).append(issue)

    total = len(all_issues)
    print(f"⚠ Cascade check: {total} issue(s) found [{TODAY}]")
    print()

    for sev, label in [("alert", "HEALTH ALERTS"), ("warning", "WARNINGS"),
                       ("cascade", "CASCADE"), ("info", "INFO")]:
        group = by_sev.get(sev, [])
        if not group:
            continue
        print(f"── {label} ({len(group)}) ──")
        for issue in group:
            nid = issue.get("node", "?")
            name = issue.get("name", "?")
            reason = issue.get("reason", "?")
            fix = issue.get("fix", "")
            deps = issue.get("dependent_skills", [])
            print(f"  [{nid}] {name}")
            print(f"    {reason}")
            if fix:
                print(f"    Fix: {fix}")
            if deps:
                print(f"    Affects: {' '.join(deps[:3])}")
        print()

    if getattr(args, "fix", False):
        print("── AUTO-GENERATED FIX COMMANDS ──")
        for issue in all_issues:
            fix = issue.get("fix", "")
            if fix:
                print(f"  {fix}")


def main():
    p = argparse.ArgumentParser(description="IGSL Cascade Watcher v2")
    p.add_argument("--json", action="store_true", dest="json_output")
    p.add_argument("--fix", action="store_true")
    args = p.parse_args()
    run(args)


if __name__ == "__main__":
    main()
