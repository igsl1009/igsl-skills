#!/usr/bin/env python3
"""
IGSL System Manager — igsl_manage.py  (META-09)
Provides health status, integrity checks, SERR cleanup, and link validation.

Commands:
  status    Full health report
  check     Pass/fail integrity check (exits 1 on failure)
  links     Verify all registry skill paths exist
  fix-serr  Remove duplicate ERR nodes with same SID tag
  gc        Garbage-collect low-weight memory nodes
"""
import json, sys, argparse
from pathlib import Path
from datetime import date

try:
    import yaml
except ImportError:
    import subprocess as _sp
    _sp.check_call([sys.executable, "-m", "pip", "install", "pyyaml", "-q"])
    import yaml

IGSL      = Path.home() / ".igsl-skills"
MEM_DIR   = IGSL / "memory"
NODES_FILE = MEM_DIR / "nodes.jsonl"
REG_FILE  = IGSL / "_registry_v2.yaml"
QA_REPORT = Path("/tmp/igsl_qa_report.json")
TODAY     = date.today().isoformat()


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_registry():
    if not REG_FILE.exists():
        return {}
    return yaml.safe_load(REG_FILE.read_text()) or {}


def load_nodes():
    nodes = {}
    if not NODES_FILE.exists():
        return nodes
    for line in NODES_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            n = json.loads(line)
            nodes[n["id"]] = n
        except Exception:
            pass
    return nodes


def health_score(h: dict) -> float:
    return (float(h.get("applied_rate", 0.5))
            * float(h.get("completion_rate", 0.5))
            * (1 - 0.5 * float(h.get("fallback_rate", 0.0))))


def resolve_path(raw: str) -> Path:
    """Expand ~ and return a Path."""
    return Path(raw).expanduser()


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_status(_args):
    reg = load_registry()
    nodes_map = reg.get("nodes", {})
    mem_nodes = load_nodes()

    # Registry summary
    skill_count = len(nodes_map)
    hard_count  = sum(1 for n in nodes_map.values() if n.get("hardness") == "hard")
    soft_count  = skill_count - hard_count

    # Health stats
    scores = []
    alerts = []
    for nid, n in nodes_map.items():
        h = n.get("health", {})
        hs = h.get("health_score") if h.get("total_applications", 0) > 0 else health_score(h)
        scores.append(hs)
        threshold = h.get("alert_threshold", 0.6)
        if hs < threshold:
            alerts.append(f"{nid} ({hs:.2f} < {threshold:.2f})")
    avg_health = sum(scores) / max(1, len(scores))

    # Memory stats
    by_type: dict = {}
    open_loops = 0
    for n in mem_nodes.values():
        t = n.get("t", "?")
        by_type[t] = by_type.get(t, 0) + 1
        if t == "LOOP" and not n.get("c", "").startswith("✓"):
            open_loops += 1

    # Active index
    idx_file = MEM_DIR / "active-index.json"
    active_ids: list = []
    if idx_file.exists():
        try:
            active_ids = json.loads(idx_file.read_text()).get("nodes", [])
        except Exception:
            pass

    # QA
    qa_passed = qa_failed = 0
    if QA_REPORT.exists():
        try:
            qa = json.loads(QA_REPORT.read_text())
            qa_passed = qa.get("passed", 0)
            qa_failed = qa.get("failed", 0)
        except Exception:
            pass

    SEP = "═" * 58
    print(f"\n{SEP}")
    print(f"  IGSL v2 System Status  [{TODAY}]")
    print(SEP)
    print(f"\n  Registry v{reg.get('version','?')}:")
    print(f"    Skills:  {skill_count} total  ({hard_count} hard, {soft_count} soft/explicit)")
    print(f"    Health:  avg {avg_health:.2f}  |  {len(alerts)} alert(s)")
    if alerts:
        for a in alerts:
            print(f"      ⚠ {a}")

    print(f"\n  Memory:")
    print(f"    Nodes:   {len(mem_nodes)} total  |  {open_loops} open loop(s)")
    dist = "  ".join(f"{t}:{n}" for t, n in sorted(by_type.items()))
    print(f"    Types:   {dist or '(empty)'}")

    print(f"\n  Active index:  {' '.join(active_ids[:8]) or '(none)'}")

    if qa_passed + qa_failed > 0:
        qa_icon = "✓" if qa_failed == 0 else "✗"
        print(f"\n  QA:  {qa_icon} {qa_passed}/{qa_passed+qa_failed} tests passed")

    print(f"\n  Commands:")
    print(f"    python3 {IGSL}/igsl_manage.py check    → integrity check")
    print(f"    python3 {IGSL}/igsl_manage.py links    → verify skill paths")
    print(f"    python3 {IGSL}/igsl_manage.py fix-serr → clean duplicate errors")
    print(f"    http://127.0.0.1:8765/dashboard.html   → visual dashboard")
    print(f"\n{SEP}\n")


def cmd_check(_args):
    """Integrity check. Exits 0 on all PASS, exits 1 on any FAIL."""
    failures = []

    # 1. Registry parseable
    try:
        reg = load_registry()
        if not reg:
            failures.append("Registry empty or unparseable")
        else:
            pass  # PASS
    except Exception as e:
        failures.append(f"Registry parse error: {e}")

    # 2. Hard skill paths exist
    nodes_map = reg.get("nodes", {}) if 'reg' in dir() else {}
    for nid, n in nodes_map.items():
        if n.get("hardness") == "hard" and n.get("path"):
            p = resolve_path(n["path"])
            if not p.exists():
                failures.append(f"Hard skill {nid} path missing: {p}")

    # 3. nodes.jsonl valid JSON lines
    if NODES_FILE.exists():
        bad_lines = 0
        for i, line in enumerate(NODES_FILE.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                json.loads(line)
            except Exception:
                bad_lines += 1
        if bad_lines:
            failures.append(f"nodes.jsonl has {bad_lines} invalid JSON line(s)")
    else:
        failures.append("nodes.jsonl not found")

    # 4. Journal dir writable
    journal_dir = IGSL / "_journal"
    journal_dir.mkdir(parents=True, exist_ok=True)
    test_file = journal_dir / ".write_test"
    try:
        test_file.write_text("ok")
        test_file.unlink()
    except Exception as e:
        failures.append(f"Journal dir not writable: {e}")

    if failures:
        print("FAIL")
        for f in failures:
            print(f"  ✗ {f}")
        sys.exit(1)
    else:
        print("PASS")
        sys.exit(0)


def cmd_links(_args):
    """Verify all registry skill paths exist."""
    reg = load_registry()
    nodes_map = reg.get("nodes", {})
    missing = []
    ok = 0

    # Skip remote/mcp/external paths (not local filesystem)
    SKIP_PREFIXES = ("remote:", "http:", "https:", "mcp:")

    def is_external(raw: str) -> bool:
        if any(raw.startswith(pfx) for pfx in SKIP_PREFIXES):
            return True
        # Bare domain-like paths (no leading ~ / . or /) are external
        if raw and raw[0] not in ("~", "/", "."):
            return True
        return False

    for nid, n in nodes_map.items():
        raw = n.get("path", "")
        if not raw:
            continue
        if is_external(raw):
            ok += 1
            continue
        p = resolve_path(raw)
        if p.exists():
            ok += 1
        else:
            missing.append(f"{nid}: {p}")

    if missing:
        print(f"LINKS: {ok} ok, {len(missing)} missing")
        for m in missing:
            print(f"  ✗ {m}")
        sys.exit(1)
    else:
        print(f"LINKS: all {ok} paths verified")
        sys.exit(0)


def cmd_fix_serr(_args):
    """Remove duplicate ERR nodes that share the same SID tag."""
    nodes = load_nodes()

    # Group ERR nodes by SID tag
    by_sid: dict = {}
    for nid, n in nodes.items():
        if n.get("t") != "ERR":
            continue
        tags = n.get("tags", [])
        sid = next((t for t in tags if t.startswith("S-") or t.startswith("META-")), None)
        if sid:
            by_sid.setdefault(sid, []).append((nid, n.get("ts", ""), n))

    removed = []
    for sid, entries in by_sid.items():
        if len(entries) <= 1:
            continue
        # Sort by timestamp descending, keep newest
        entries.sort(key=lambda x: x[1], reverse=True)
        for nid, ts, _ in entries[1:]:  # remove all but the newest
            removed.append(nid)
            del nodes[nid]

    if not removed:
        print("fix-serr: no duplicate SERR nodes found")
        return

    # Rewrite nodes.jsonl
    lines = [json.dumps(n, ensure_ascii=False) for n in nodes.values()]
    NODES_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"fix-serr: removed {len(removed)} duplicate(s): {' '.join(removed)}")


def cmd_gc(_args):
    """Delegate to memory/node.py gc."""
    import subprocess
    dry = "--dry-run" if getattr(_args, "dry_run", False) else ""
    cmd = [sys.executable, str(IGSL / "memory" / "node.py"), "gc"]
    if dry:
        cmd.append(dry)
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(r.stdout.strip())
    if r.returncode != 0 and r.stderr:
        print(r.stderr.strip(), file=sys.stderr)
    sys.exit(r.returncode)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        description="IGSL System Manager (META-09)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("status",   help="Full health report")
    sub.add_parser("check",    help="Integrity check (exits 1 on failure)")
    sub.add_parser("links",    help="Verify all registry skill paths")
    sub.add_parser("fix-serr", help="Remove duplicate SERR nodes")
    gc_p = sub.add_parser("gc", help="Garbage-collect low-weight memory nodes")
    gc_p.add_argument("--dry-run", action="store_true", dest="dry_run")

    args = p.parse_args()
    if not args.cmd:
        p.print_help()
        sys.exit(0)

    if args.cmd == "status":
        cmd_status(args)
    elif args.cmd == "check":
        cmd_check(args)
    elif args.cmd == "links":
        cmd_links(args)
    elif args.cmd == "fix-serr":
        cmd_fix_serr(args)
    elif args.cmd == "gc":
        cmd_gc(args)


if __name__ == "__main__":
    main()
