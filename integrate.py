#!/usr/bin/env python3
"""
IGSL Skill-Memory Integration Bridge v2 — integrate.py
Bidirectional connection between Skill Graph and Memory Network.

Five connections:
  ① Skill → Memory: skill applied → bump memory node weights, write ERR on failure
  ② Memory → Skill: memory query results → suggest matching skill bundles
  ③ Health → Memory: low-health skills → ERR memory nodes
  ④ Evolution → Both: journal events → memory nodes + skill evolutions
  ⑤ Session synthesis → Both: post-session journal processing

Commands:
  skill-applied  SKILL_ID [--success] [--no-success] [--session-id S]
  memory-to-skills "query" [--top N]
  health-sync
  session-context
  post-session [--journal PATH]
"""

import json, sys, re, argparse, subprocess
from pathlib import Path
from datetime import date

IGSL     = Path.home() / ".igsl-skills"
MEM_DIR  = IGSL / "memory"
PROPOSED = IGSL / "_proposed"
TODAY    = date.today().isoformat()
SESSION_FILE = Path("/tmp/igsl_session_id")


def run_skill(*cmd_args, timeout: int = 30) -> str:
    result = subprocess.run(
        [sys.executable, str(IGSL / "skill.py")] + list(cmd_args),
        capture_output=True, text=True, timeout=timeout
    )
    return result.stdout.strip()


def run_node(*cmd_args, timeout: int = 30) -> str:
    result = subprocess.run(
        [sys.executable, str(MEM_DIR / "node.py")] + list(cmd_args),
        capture_output=True, text=True, timeout=timeout
    )
    return result.stdout.strip()


def load_registry() -> dict:
    reg_file = IGSL / "_registry_v2.yaml"
    if not reg_file.exists():
        return {"nodes": {}}
    try:
        import yaml
        with open(reg_file, encoding="utf-8") as f:
            return yaml.safe_load(f) or {"nodes": {}}
    except ImportError:
        json_file = IGSL / "_registry_v2.json"
        if json_file.exists():
            return json.loads(json_file.read_text(encoding="utf-8"))
        return {"nodes": {}}


def load_nodes() -> dict:
    nodes_file = MEM_DIR / "nodes.jsonl"
    if not nodes_file.exists():
        return {}
    nodes = {}
    for line in nodes_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            n = json.loads(line)
            if "id" in n:
                nodes[n["id"]] = n
        except json.JSONDecodeError:
            pass
    return nodes


def next_id(prefix: str, nodes: dict) -> str:
    existing = []
    for k in nodes:
        if k.startswith(prefix + "-"):
            suffix = k[len(prefix)+1:]
            if suffix.isdigit():
                existing.append(int(suffix))
    return f"{prefix}-{max(existing or [0]) + 1:03d}"


def session_id() -> str:
    if SESSION_FILE.exists():
        return SESSION_FILE.read_text().strip()
    return "unknown"


# ── Connection ①: Skill Applied → Memory ─────────────────────────────────────

def cmd_skill_applied(args):
    skill_id = args.skill_id
    success = not getattr(args, "no_success", False)
    sess_id = getattr(args, "session_id", None) or session_id()

    reg = load_registry()
    skill_node = reg.get("nodes", {}).get(skill_id, {})
    mem_nodes = skill_node.get("memory_nodes", [])

    applied = 1
    completed = 1 if success else 0
    run_skill("health", "record", skill_id,
              "--applied", str(applied),
              "--completed", str(completed),
              "--fallback", "0")

    bumped = []
    for mnid in mem_nodes:
        result = run_node("fetch", mnid)
        if "ERROR" not in result:
            bumped.append(mnid)

    if not success:
        nodes = load_nodes()
        err_id = next_id("SERR", nodes)
        err_content = f"ERR: skill {skill_node.get('name', skill_id)} failed | session:{sess_id[:8]}"
        tags = ["skill-failure", skill_id] + skill_node.get("tags", [])[:3]
        run_node("add",
                 "--id", err_id,
                 "--type", "ERR",
                 "--tags", " ".join(tags),
                 "--content", err_content[:120],
                 "--src", sess_id[:6])
        print(f"ERR node created: {err_id}")
    else:
        if mem_nodes:
            run_skill("bundle", "record", skill_id, *mem_nodes[:3])

    print(f"Skill-Memory sync complete: {skill_id}")
    print(f"  success={success}  memory_nodes_bumped={bumped}")


# ── Connection ②: Memory → Skill Bundle Suggestion ───────────────────────────

def cmd_memory_to_skills(args):
    query = args.query
    top_n = getattr(args, "top", 3)

    mem_result = run_node("query", query, "--top", str(top_n))
    if mem_result:
        print("=== Memory results ===")
        print(mem_result)
        print()
    else:
        print("(No memory results)")

    node_ids = re.findall(r'\[([A-Z]+-\d+)\]', mem_result)

    reg = load_registry()
    suggested = {}
    for nid in node_ids:
        for sid, snode in reg.get("nodes", {}).items():
            if nid in snode.get("memory_nodes", []):
                if sid not in suggested:
                    suggested[sid] = {"skill": snode, "via": []}
                suggested[sid]["via"].append(nid)

    if suggested:
        print("=== Skill suggestions (via memory links) ===")
        for sid, info in sorted(suggested.items()):
            sn = info["skill"]
            via = " ".join(info["via"])
            print(f"[{sid}] {sn.get('name', sid):24} via: {via}")
            print(f"  {sn.get('meta_summary', '')}")
            print(f"  load: python3 ~/.igsl-skills/skill.py load {sid}")
            print()

    print("=== Direct skill query ===")
    skill_result = run_skill("query", query, "--top", str(top_n))
    print(skill_result)


# ── Connection ③: Health Sync → ERR Memory Nodes ─────────────────────────────

def cmd_health_sync(args):
    reg = load_registry()
    nodes = load_nodes()
    written = 0

    def health_score(h):
        ar = float(h.get("applied_rate", 0.5))
        cr = float(h.get("completion_rate", 0.5))
        fr = float(h.get("fallback_rate", 0.0))
        return ar * cr * (1.0 - 0.5 * fr)

    for sid, snode in reg.get("nodes", {}).items():
        if snode.get("deprecated"):
            continue
        h = snode.get("health", {})
        hs = health_score(h)
        thresh = h.get("alert_threshold", 0.60)

        if hs < thresh:
            existing = [nid for nid, n in nodes.items()
                       if n.get("t") == "ERR" and sid in n.get("tags", [])]
            if not existing:
                err_id = next_id("SERR", nodes)
                content = (f"ERR: skill {snode.get('name', '?')} "
                          f"health={hs:.2f}<{thresh:.2f} | evolve with FIX mode")
                result = run_node("add",
                                  "--id", err_id,
                                  "--type", "ERR",
                                  "--tags", f"skill-health {sid} low-health",
                                  "--content", content[:120],
                                  "--src", "health-sync")
                print(f"  ERR node: {err_id} — {content[:60]}")
                nodes = load_nodes()
                written += 1

    print(f"Health sync: {written} new ERR nodes")


# ── Session Context Assembly ──────────────────────────────────────────────────

def cmd_session_context(args):
    print("=" * 60)
    print("IGSL v2 SESSION CONTEXT ASSEMBLY")
    print("=" * 60)
    print()

    total_tok = 0

    t0_file = MEM_DIR / "t0_identity.mem"
    if t0_file.exists():
        content = t0_file.read_text(encoding="utf-8")
        tok = len(content.split()) * 1.3
        total_tok += tok
        print(f"[T0] Identity  (~{tok:.0f} tokens, always loaded)")
        print(content[:300])
    else:
        print("[T0] Identity file not found — create memory/t0_identity.mem")
    print()

    t1_file = MEM_DIR / "t1_session.mem"
    if t1_file.exists():
        content = t1_file.read_text(encoding="utf-8")
        tok = len(content.split()) * 1.3
        total_tok += tok
        print(f"[T1] Session context  (~{tok:.0f} tokens)")
        print(content[:200])
    else:
        print("[T1] Session memory not yet written (created by SessionStart hook)")
    print()

    idx_file = MEM_DIR / "active-index.json"
    if idx_file.exists():
        import json as _j
        idx = _j.loads(idx_file.read_text(encoding="utf-8"))
        tok = 50
        total_tok += tok
        print(f"[ACTIVE INDEX]  (~{tok} tokens)")
        print(f"  Top nodes: {' '.join(idx.get('nodes', []))}")
    else:
        print("[ACTIVE INDEX] Not found — run: node.py active")
    print()

    print(f"[SKILL SCAN]  (~150 tokens — all skills, metadata only)")
    scan_result = run_skill("scan")
    total_tok += 150
    lines = scan_result.splitlines()[:30]
    for line in lines:
        print(f"  {line}")
    if len(scan_result.splitlines()) > 30:
        print(f"  ... ({len(scan_result.splitlines())-30} more lines)")
    print()

    print("─" * 60)
    print(f"Base session cost: ~{int(total_tok + 150 + 460)} tokens always loaded")
    print(f"  T0+T1+Index:  ~{int(total_tok)} tok")
    print(f"  Skill scan:   ~150 tok")
    print(f"  Hard skills:  ~460 tok (META-05 + META-07)")
    print()
    print("On-demand additions:")
    print("  Memory query (5 nodes): ~150 tok per call")
    print("  S-01 quant-research:   ~1420 tok if triggered")
    print("  T2 project memory:     ~300 tok if loaded")


# ── Connection ④: Post-Session Synthesis ─────────────────────────────────────

def cmd_post_session(args):
    journal_path = getattr(args, "journal", None)

    if not journal_path:
        journal_dir = IGSL / "_journal"
        if journal_dir.exists():
            files = sorted(journal_dir.glob("*.jsonl"), reverse=True)
            if files:
                journal_path = str(files[0])

    if not journal_path or not Path(journal_path).exists():
        print("No journal file found. Use --journal PATH")
        return

    events = []
    for line in Path(journal_path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
            if e.get("type") != "session_start":
                events.append(e)
        except json.JSONDecodeError:
            pass

    if not events:
        print("No events in journal (or only session_start).")
        return

    print(f"Processing {len(events)} journal events...")
    nodes = load_nodes()
    mem_written = 0
    skill_evolved = 0

    for e in events:
        etype = e.get("type", "")
        skill_id = e.get("affected_skill")
        sess_src = session_id()[:6]

        if etype == "correction":
            nid = next_id("GEN", nodes)
            wrong = e.get("what_was_wrong", "?")[:40]
            correct = e.get("what_is_correct", "?")[:40]
            content = f"ERR: {wrong} → correct:{correct}"
            run_node("add", "--id", nid, "--type", "ERR",
                     "--tags", "correction session",
                     "--content", content[:120],
                     "--src", sess_src)
            nodes = load_nodes()
            mem_written += 1

            if skill_id:
                severity = e.get("severity", "minor")
                if severity == "minor":
                    run_skill("evolve", skill_id, "--mode", "FIX",
                              "--session", journal_path,
                              "--trigger", "correction")
                    skill_evolved += 1

        elif etype == "self_correction":
            nid = next_id("GEN", nodes)
            root = e.get("root_cause", "?")[:60]
            content = f"ERR: self-corrected | cause:{root}"
            run_node("add", "--id", nid, "--type", "ERR",
                     "--tags", "self-correction session",
                     "--content", content[:120],
                     "--src", sess_src)
            nodes = load_nodes()
            mem_written += 1

        elif etype == "pattern_win":
            nid = next_id("GEN", nodes)
            pattern = e.get("pattern", "?")[:80]
            content = f"PAT[+] {pattern}"
            run_node("add", "--id", nid, "--type", "PAT",
                     "--tags", "pattern-win session",
                     "--content", content[:120],
                     "--src", sess_src)
            nodes = load_nodes()
            mem_written += 1

            if e.get("reusable") and skill_id:
                run_skill("evolve", skill_id, "--mode", "CAPTURED",
                          "--session", journal_path,
                          "--trigger", "pattern-win")
                skill_evolved += 1

        elif etype == "pattern_fail":
            nid = next_id("GEN", nodes)
            pattern = e.get("pattern", "?")[:60]
            why = e.get("why_it_failed", "?")[:40]
            content = f"PAT[-] {pattern} | {why}"
            run_node("add", "--id", nid, "--type", "ERR",
                     "--tags", "pattern-fail session",
                     "--content", content[:120],
                     "--src", sess_src)
            nodes = load_nodes()
            mem_written += 1

        elif etype == "new_edge":
            from_id = e.get("from")
            to_id = e.get("to")
            if from_id and to_id:
                result = run_node("link", from_id, to_id)
                if "ERROR" not in result:
                    mem_written += 1

        elif etype == "gap_found":
            nid = next_id("GEN", nodes)
            desc = e.get("description", "?")[:80]
            urgency = e.get("urgency", "backlog")
            content = f"○ skill-gap[{urgency}]: {desc}"
            run_node("add", "--id", nid, "--type", "LOOP",
                     "--tags", "skill-gap gap new-node",
                     "--content", content[:120],
                     "--src", sess_src)
            nodes = load_nodes()
            mem_written += 1

    print("\nRebuilding active memory index...")
    run_node("active")

    print("Running cascade check...")
    run_skill("cascade")

    print("\nSynthesising improvement proposals...")
    _synthesise_proposals(events[:10], journal_path)

    print(f"\nPost-session complete:")
    print(f"  Memory nodes written: {mem_written}")
    print(f"  Skill evolutions triggered: {skill_evolved}")
    print(f"  Active index rebuilt")
    print(f"  Run: python3 ~/.igsl-skills/hooks/apply_proposals.py  to review proposals")


def _synthesise_proposals(events: list, journal_path: str):
    PROPOSED.mkdir(exist_ok=True)

    events_json = json.dumps(events, indent=2)
    prompt = f"""You are the IGSL auto-improve system [META-05].

Session journal events:
{events_json}

Produce a JSON array of max 3 concrete improvement proposals.
Each proposal:
{{"proposal_id":"P_{TODAY}_N","type":"skill_patch|new_edge|new_node|user_memory",
  "target":"node-id or NEW","summary":"one line","detail":"exact change","severity":"minor|major",
  "sessions_before_promotion":1}}

Output ONLY the JSON array. No markdown, no prose."""

    try:
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True, text=True, timeout=60
        )
        raw = result.stdout.strip()
        if "```" in raw:
            parts = raw.split("```")
            raw = parts[1] if len(parts) > 1 else raw
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        if raw.startswith("["):
            proposals = json.loads(raw)
            journal_stem = Path(journal_path).stem[:20]
            pfile = PROPOSED / f"{journal_stem}_proposals.json"
            pfile.write_text(json.dumps(proposals, indent=2), encoding="utf-8")
            print(f"  {len(proposals)} proposals → {pfile}")
            for p in proposals:
                print(f"    [{p.get('type', '?')}] {p.get('summary', '')}")
        else:
            print("  Proposal synthesis returned unexpected format")
    except FileNotFoundError:
        print("  claude CLI not available — skipping proposal synthesis")
    except subprocess.TimeoutExpired:
        print("  Proposal synthesis timed out — skipping")
    except json.JSONDecodeError:
        print("  Proposal JSON parse failed — raw output saved")
        (PROPOSED / f"raw_{TODAY}.txt").write_text(raw or "", encoding="utf-8")
    except Exception as e:
        print(f"  Proposal synthesis error: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        description="IGSL Skill-Memory Integration Bridge v2",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd")

    sa = sub.add_parser("skill-applied")
    sa.add_argument("skill_id")
    sa.add_argument("--success", action="store_true", default=True)
    sa.add_argument("--no-success", action="store_true", dest="no_success")
    sa.add_argument("--session-id", default="", dest="session_id")

    ms = sub.add_parser("memory-to-skills")
    ms.add_argument("query")
    ms.add_argument("--top", type=int, default=3)

    sub.add_parser("health-sync")

    sub.add_parser("session-context")

    ps = sub.add_parser("post-session")
    ps.add_argument("--journal", default=None)

    args = p.parse_args()
    if not args.cmd:
        p.print_help()
        sys.exit(0)

    if args.cmd == "skill-applied":
        cmd_skill_applied(args)
    elif args.cmd == "memory-to-skills":
        cmd_memory_to_skills(args)
    elif args.cmd == "health-sync":
        cmd_health_sync(args)
    elif args.cmd == "session-context":
        cmd_session_context(args)
    elif args.cmd == "post-session":
        cmd_post_session(args)


if __name__ == "__main__":
    main()
