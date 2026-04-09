#!/usr/bin/env python3
"""
IGSL Skill Graph CLI v2 — skill.py
Manages skill nodes: registry, health, evolution, bundle co-occurrence.

Commands:
  scan      [--session-start]
  query     "keywords" [--top 5] [--type T] [--project P]
  load      ID [--dry-run] [--no-health]
  add       --id ID --name N [--type T] [--surface S] [--path P] [--tags "t1 t2"]
            [--hardness H] --keywords "k1 k2" --summary "..." --tier private
  update    ID [--content PATH] [--tags "t1 t2"] [--links "A B"]
  evolve    ID --mode FIX|DERIVED|CAPTURED [--session S] [--trigger T]
  lineage   ID [--depth 2]
  bundle    suggest ID
  bundle    record ID1 ID2 [ID3 ...]
  health    record ID [--applied 1] [--completed 1] [--fallback 0]
  health    show [ID]
  health    alert
  access    check [ID]
  cascade
  gc        [--dry-run]
  show
"""

import json, sys, re, math, argparse, shutil, subprocess, os
from pathlib import Path
from datetime import date, datetime
from collections import defaultdict

# ── Paths ─────────────────────────────────────────────────────────────────────
SKILLS_DIR = Path.home() / ".igsl-skills"
REGISTRY   = SKILLS_DIR / "_registry_v2.yaml"
EVOGRAPH   = SKILLS_DIR / "_evograph.jsonl"
META_SCAN  = SKILLS_DIR / "_meta_scan.md"
TODAY      = date.today().isoformat()

# ── I/O ───────────────────────────────────────────────────────────────────────

def load_registry() -> dict:
    if not REGISTRY.exists():
        return {"version": "2.0", "nodes": {}, "next_ids": {}}
    try:
        import yaml
        with open(REGISTRY, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data or {"version": "2.0", "nodes": {}}
    except ImportError:
        json_path = SKILLS_DIR / "_registry_v2.json"
        if json_path.exists():
            return json.loads(json_path.read_text(encoding="utf-8"))
        return {"version": "2.0", "nodes": {}}

def save_registry(reg: dict):
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        import yaml
        content = yaml.dump(reg, default_flow_style=False, allow_unicode=True,
                           sort_keys=False, indent=2)
        tmp = REGISTRY.with_suffix(".tmp")
        tmp.write_text(content, encoding="utf-8")
        tmp.replace(REGISTRY)
    except ImportError:
        json_path = SKILLS_DIR / "_registry_v2.json"
        tmp = json_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(reg, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(json_path)

# ── Health scoring ────────────────────────────────────────────────────────────

def health_score(h: dict) -> float:
    ar = float(h.get("applied_rate", 0.5))
    cr = float(h.get("completion_rate", 0.5))
    fr = float(h.get("fallback_rate", 0.0))
    return round(ar * cr * (1.0 - 0.5 * fr), 4)

def update_health_ema(h: dict, applied: bool, completed: bool, fallback: bool) -> dict:
    alpha = 0.1
    h["applied_rate"]    = round(h.get("applied_rate", 0.5) * (1-alpha) + (1.0 if applied else 0.0) * alpha, 4)
    h["completion_rate"] = round(h.get("completion_rate", 0.5) * (1-alpha) + (1.0 if completed else 0.0) * alpha, 4)
    h["fallback_rate"]   = round(h.get("fallback_rate", 0.0) * (1-alpha) + (1.0 if fallback else 0.0) * alpha, 4)
    h["total_applications"] = h.get("total_applications", 0) + 1
    h["health_score"]    = max(0.05, health_score(h))
    h["last_applied"]    = TODAY
    return h

def default_health(full_tokens: int = 300) -> dict:
    return {
        "applied_rate": 0.5, "completion_rate": 0.5, "fallback_rate": 0.0,
        "health_score": 0.5, "alert_threshold": 0.60, "total_applications": 0,
        "token_cost_avg": full_tokens, "last_applied": TODAY
    }

def fmt_health_bar(h: dict) -> str:
    hs = health_score(h)
    filled = int(hs * 10)
    bar = "█" * filled + "░" * (10 - filled)
    ar  = h.get("applied_rate", 0)
    cr  = h.get("completion_rate", 0)
    fr  = h.get("fallback_rate", 0)
    n   = h.get("total_applications", 0)
    return f"{bar} {hs:.2f}  applied={ar:.0%} done={cr:.0%} fallback={fr:.0%} n={n}"

# ── BM25 search ───────────────────────────────────────────────────────────────

STOPWORDS = {
    "the","a","an","is","in","to","of","and","or","for","with","at","by",
    "on","it","this","that","was","are","be","from","as","not","we","i","you",
    "have","had","use","when","what","how","if","do","can","will","make"
}

def tokenize(text: str) -> list:
    words = re.findall(r"[a-zA-Z0-9\-\_]+", text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 1]

def bm25_score(qtoks: list, dtoks: list, k1: float = 1.2, b: float = 0.75) -> float:
    avg_dl = 15.0
    tf = defaultdict(int)
    for t in dtoks:
        tf[t] += 1
    dl = len(dtoks)
    score = 0.0
    for q in qtoks:
        if q in tf:
            f = tf[q]
            idf = math.log(1.0 + 1.0 / (0.5 + f))
            numerator = f * (k1 + 1.0)
            denominator = f + k1 * (1.0 - b + b * dl / avg_dl)
            score += idf * numerator / denominator
    return score

def score_node_for_query(node: dict, qtoks: list) -> float:
    doc = (
        " ".join(node.get("tags", [])) + " "
        + " ".join(node.get("trigger_keywords", [])) + " "
        + node.get("meta_summary", "")
    )
    dtoks = tokenize(doc)
    text_score = bm25_score(qtoks, dtoks)
    hs = health_score(node.get("health", {}))
    return text_score * (0.6 + 0.4 * hs)

# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_scan(args, reg: dict):
    nodes = reg.get("nodes", {})
    hard_nodes = [(nid, n) for nid, n in nodes.items()
                  if n.get("hardness") == "hard" and not n.get("deprecated")]
    soft_nodes = [(nid, n) for nid, n in nodes.items()
                  if n.get("hardness") != "hard" and not n.get("deprecated")]
    soft_nodes.sort(key=lambda x: health_score(x[1].get("health", {})), reverse=True)

    lines = [
        f"# IGSL SKILL META-SCAN | {TODAY} | {len(nodes)} nodes",
        "",
        "## HARD SKILLS (auto-loaded every session)"
    ]
    hard_total = 0
    for nid, n in hard_nodes:
        hs = health_score(n.get("health", {}))
        tok = n.get("full_tokens", 0)
        hard_total += tok
        lines.append(f"  [{nid:<12}] {n['name']:<22} {tok:>5}tok  h={hs:.2f}  {n.get('meta_summary','')[:55]}")
    lines.append(f"  Hard skill total: {hard_total} tokens")

    lines.append("")
    lines.append("## SOFT-HOOK SKILLS (load when keywords match)")
    for nid, n in soft_nodes:
        hs = health_score(n.get("health", {}))
        tok = n.get("full_tokens", 0)
        kws = " ".join(n.get("trigger_keywords", [])[:5])
        lines.append(f"  [{nid:<12}] {n['name']:<22} {tok:>5}tok  h={hs:.2f}  triggers:[{kws}]")

    lines.append("")
    lines.append("## SUMMARY")
    lines.append(f"  Hard skills: {len(hard_nodes)} nodes, {hard_total} tokens always")
    lines.append(f"  Soft skills: {len(soft_nodes)} nodes, load on match")
    lines.append(f"  Total registry: {len(nodes)} nodes")

    output = "\n".join(lines)

    if getattr(args, "session_start", False):
        META_SCAN.write_text(output, encoding="utf-8")
        print(f"[SCAN] Meta-scan written to {META_SCAN}")
        for nid, n in hard_nodes:
            path = Path(n.get("path", "").replace("~", str(Path.home())))
            if path.exists():
                print(f"[HARD] {n['name']} ({n.get('full_tokens', 0)} tok) — content available at {path}")
            else:
                print(f"[HARD] {n['name']} — path not found: {path}")
    else:
        print(output)


def cmd_query(args, reg: dict):
    nodes = reg.get("nodes", {})
    qtoks = tokenize(args.query)
    if not qtoks:
        print(f"No keywords extracted from: {args.query}")
        return

    scored = []
    for nid, n in nodes.items():
        if n.get("deprecated"):
            continue
        if getattr(args, "type", "") and n.get("type") != args.type:
            continue
        if getattr(args, "project", "") and not nid.startswith(args.project.upper()):
            continue
        s = score_node_for_query(n, qtoks)
        if s > 0:
            scored.append((nid, n, s))
    scored.sort(key=lambda x: x[2], reverse=True)
    top = scored[:getattr(args, "top", 5)]

    if not top:
        print(f"No skills matched: '{args.query}'")
        print("Try: skill.py scan  to see all available skills")
        return

    total_tok = 0
    print(f"# SKILL QUERY: '{args.query}' | {len(top)} match(es)")
    print("─" * 64)

    seen_bundles = set(nid for nid, _, _ in top)
    bundle_suggestions = []

    for nid, n, score in top:
        tok = n.get("full_tokens", 0)
        total_tok += tok
        hs = health_score(n.get("health", {}))
        hardness = n.get("hardness", "?")

        print(f"\n[{nid}] {n['name']}")
        print(f"  score={score:.3f}  health={hs:.2f}  hardness={hardness}  {tok} tokens")
        print(f"  {n.get('meta_summary', '')}")
        print(f"  triggers: {' '.join(n.get('trigger_keywords', [])[:7])}")

        bundle = n.get("bundle", {}).get("co_occurs_with", {})
        for bid, bscore in sorted(bundle.items(), key=lambda x: x[1], reverse=True):
            if bid not in seen_bundles and bscore >= 0.3:
                bn = nodes.get(bid, {})
                if bn and not bn.get("deprecated"):
                    btok = bn.get("full_tokens", 0)
                    total_tok += btok
                    seen_bundles.add(bid)
                    bundle_suggestions.append((bid, bn, bscore, btok))

    if bundle_suggestions:
        print(f"\n  Bundle co-loads (high co-occurrence):")
        for bid, bn, bscore, btok in bundle_suggestions:
            print(f"    [{bid}] {bn.get('name', '?'):20} co={bscore:.2f}  {btok} tok")

    print(f"\n{'─'*64}")
    print(f"Total if all loaded: ~{total_tok} tokens")
    if top:
        print(f"Load command: python3 ~/.igsl-skills/skill.py load {top[0][0]}")


def cmd_load(args, reg: dict):
    nodes = reg.get("nodes", {})
    nid = args.id
    n = nodes.get(nid)
    if not n:
        print(f"ERROR: '{nid}' not found in registry.")
        sys.exit(1)

    path = Path(n.get("path", "").replace("~", str(Path.home())))

    if getattr(args, "dry_run", False):
        print(f"[DRY-RUN] Would load: {path}")
        print(f"  Name: {n['name']}  Tokens: {n.get('full_tokens', 0)}  Health: {health_score(n.get('health', {})):.2f}")
        return

    if not path.exists():
        print(f"WARNING: Skill file not found: {path}")
        print(f"Meta summary: {n.get('meta_summary', '(none)')}")
        return

    print(path.read_text(encoding="utf-8"))

    if not getattr(args, "no_health", False):
        h = n.setdefault("health", default_health(n.get("full_tokens", 300)))
        update_health_ema(h, applied=True, completed=True, fallback=False)
        nodes[nid] = n
        save_registry(reg)


def cmd_health_record(args, reg: dict):
    nodes = reg.get("nodes", {})
    nid = args.id
    if nid not in nodes:
        print(f"ERROR: '{nid}' not found"); sys.exit(1)
    n = nodes[nid]
    applied   = getattr(args, "applied", 1) == 1
    completed = getattr(args, "completed", 1) == 1
    fallback  = getattr(args, "fallback", 0) == 1

    h = n.setdefault("health", default_health(n.get("full_tokens", 300)))
    update_health_ema(h, applied=applied, completed=completed, fallback=fallback)
    nodes[nid] = n
    save_registry(reg)
    print(f"Health updated [{nid}]: {fmt_health_bar(h)}")


def cmd_health_show(args, reg: dict):
    nodes = reg.get("nodes", {})
    nid = getattr(args, "id", None)
    if nid:
        targets = {nid: nodes[nid]} if nid in nodes else {}
        if not targets:
            print(f"ERROR: '{nid}' not found"); sys.exit(1)
    else:
        targets = {k: v for k, v in nodes.items() if not v.get("deprecated")}

    sorted_nodes = sorted(targets.items(),
                          key=lambda x: health_score(x[1].get("health", {})),
                          reverse=True)
    for nid, n in sorted_nodes:
        h = n.get("health", {})
        hs = health_score(h)
        thresh = h.get("alert_threshold", 0.60)
        alert = " ⚠ ALERT" if hs < thresh else ""
        print(f"[{nid:<12}] {n.get('name', '?'):<24} {fmt_health_bar(h)}{alert}")


def cmd_health_alert(args, reg: dict):
    nodes = reg.get("nodes", {})
    alerts = []
    for nid, n in nodes.items():
        if n.get("deprecated"):
            continue
        h = n.get("health", {})
        hs = health_score(h)
        thresh = h.get("alert_threshold", 0.60)
        if hs < thresh:
            alerts.append((nid, n, hs, thresh))
    alerts.sort(key=lambda x: x[2])

    if not alerts:
        print("✓ All skills above alert threshold")
        return
    print(f"⚠ {len(alerts)} skill(s) below alert threshold:")
    for nid, n, hs, thresh in alerts:
        print(f"  [{nid}] {n.get('name', '?'):24} health={hs:.2f} < threshold={thresh:.2f}")
        print(f"         → skill.py evolve {nid} --mode FIX")


def cmd_evolve(args, reg: dict):
    nodes = reg.get("nodes", {})
    nid = args.id
    mode = args.mode
    if nid not in nodes:
        print(f"ERROR: '{nid}' not found"); sys.exit(1)

    n = nodes[nid]
    lineage = n.setdefault("lineage", {})
    old_ver = lineage.get("version", "1.0")

    parts = str(old_ver).split(".")
    if len(parts) >= 2:
        new_ver = f"{parts[0]}.{int(parts[1]) + 1}"
    else:
        new_ver = f"{old_ver}.1"

    parent_id = f"{nid}@{old_ver}"
    diff_path = f"_archive/{nid}@{old_ver}-to-{new_ver}.diff"
    session = getattr(args, "session", "manual")
    trigger = getattr(args, "trigger", "manual")

    EVOGRAPH.parent.mkdir(parents=True, exist_ok=True)
    edge = {
        "ts": TODAY,
        "from": parent_id,
        "to": nid,
        "mode": mode,
        "old_ver": old_ver,
        "new_ver": new_ver,
        "diff_path": diff_path,
        "session": session,
        "trigger": trigger
    }
    with open(EVOGRAPH, "a", encoding="utf-8") as f:
        f.write(json.dumps(edge) + "\n")

    lineage["version"] = new_ver
    lineage["parent"] = parent_id
    lineage["evolution_mode"] = mode
    lineage["diff_path"] = diff_path
    lineage["session_source"] = session
    n["last_updated"] = TODAY
    n.setdefault("health", {})["total_applications"] = 0

    nodes[nid] = n
    save_registry(reg)

    try:
        subprocess.run(["git", "-C", str(SKILLS_DIR), "add", "-A"], capture_output=True, timeout=10)
        subprocess.run(
            ["git", "-C", str(SKILLS_DIR), "commit", "-m",
             f"evolve({nid}): {mode} v{old_ver}->v{new_ver} [{trigger}]"],
            capture_output=True, timeout=10
        )
    except Exception:
        pass

    print(f"Evolution recorded: {parent_id} → {nid}@{new_ver}")
    print(f"Mode: {mode}  Session: {session}")
    print(f"EvoGraph edge written to {EVOGRAPH}")
    print(f"\nNext steps:")
    print(f"  1. Edit the skill file: {n.get('path', '?')}")
    print(f"  2. Create diff: diff old new > {diff_path}")


def cmd_lineage(args, reg: dict):
    nid = args.id
    n = reg.get("nodes", {}).get(nid, {})
    print(f"Lineage: [{nid}] {n.get('name', nid)}")
    print(f"Current version: {n.get('lineage', {}).get('version', '?')}")

    if not EVOGRAPH.exists():
        print("No evolution history (EvoGraph not found)")
        return

    edges = []
    try:
        for line in EVOGRAPH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            e = json.loads(line)
            if nid in e.get("from", "") or nid == e.get("to", ""):
                edges.append(e)
    except Exception as ex:
        print(f"Error reading EvoGraph: {ex}")
        return

    if not edges:
        print("No evolution history (root skill — never evolved)")
        return

    print(f"\nEvolution history ({len(edges)} transitions):")
    for e in sorted(edges, key=lambda x: x.get("ts", "")):
        print(f"  [{e['ts']}] {e['from']:20} → {e.get('to', '?')}")
        print(f"          mode={e['mode']}  trigger={e.get('trigger', '?')}")
        print(f"          diff: {e.get('diff_path', 'none')}")


def cmd_bundle_suggest(args, reg: dict):
    nodes = reg.get("nodes", {})
    nid = args.id
    n = nodes.get(nid)
    if not n:
        print(f"ERROR: '{nid}' not found"); sys.exit(1)

    bundle = n.get("bundle", {}).get("co_occurs_with", {})
    print(f"Bundle suggestions for [{nid}] {n['name']}:")
    print(f"  Primary: {n.get('full_tokens', 0)} tok")

    if not bundle:
        print("  No co-occurrence data yet.")
        return

    total = n.get("full_tokens", 0)
    for bid, score in sorted(bundle.items(), key=lambda x: x[1], reverse=True):
        bn = nodes.get(bid, {})
        btok = bn.get("full_tokens", 0)
        total += btok
        print(f"  + [{bid}] {bn.get('name', bid):20} co={score:.2f}  {btok} tok")

    print(f"\n  Total bundle: ~{total} tokens")


def cmd_bundle_record(args, reg: dict):
    nodes = reg.get("nodes", {})
    ids = args.ids
    alpha = 0.05

    for i, ida in enumerate(ids):
        for idb in ids[i+1:]:
            for src, dst in [(ida, idb), (idb, ida)]:
                if src in nodes:
                    co = nodes[src].setdefault("bundle", {}).setdefault("co_occurs_with", {})
                    prev = float(co.get(dst, 0.0))
                    co[dst] = round(prev * (1 - alpha) + 1.0 * alpha, 4)

    save_registry(reg)
    print(f"Co-occurrence recorded: {' + '.join(ids)}")


def cmd_access_check(args, reg: dict):
    nodes = reg.get("nodes", {})
    nid = getattr(args, "id", None)
    targets = {nid: nodes[nid]} if nid and nid in nodes else nodes

    for nid, n in sorted(targets.items()):
        if n.get("deprecated"):
            continue
        access = n.get("access", {})
        tier = access.get("tier", "?")
        src_commit = access.get("source_commit", "?")
        path_str = n.get("path", "").replace("~", str(Path.home()))
        path = Path(path_str)

        drift_status = "?"
        if path.exists():
            try:
                result = subprocess.run(
                    ["git", "log", "--oneline", "-1", "--", str(path)],
                    capture_output=True, text=True, cwd=str(SKILLS_DIR), timeout=5
                )
                if result.stdout.strip():
                    current = result.stdout.strip().split()[0]
                    drift_status = "CLEAN" if current == src_commit else f"DRIFT ({src_commit[:7]}->{current[:7]})"
                else:
                    drift_status = "untracked"
            except Exception:
                drift_status = "no-git"
        else:
            drift_status = "missing"

        icon = "✓" if drift_status in ("CLEAN", "untracked") else "⚠"
        print(f"{icon} [{nid:<12}] {n.get('name', '?'):<24} tier={tier:<8} {drift_status}")


def cmd_cascade(args, reg: dict):
    import time
    nodes = reg.get("nodes", {})
    issues = []

    now = time.time()
    for nid, n in nodes.items():
        if n.get("type") != "mcp":
            continue
        path = Path(n.get("path", "").replace("~", str(Path.home())))
        if path.exists():
            age_days = (now - path.stat().st_mtime) / 86400
            if age_days < 7:
                issues.append((nid, n, f"MCP file modified {age_days:.1f} days ago"))

    changed_ids = {i for i, _, _ in issues}
    for nid, n in nodes.items():
        if n.get("deprecated"):
            continue
        for dep in n.get("connects_to", []) + n.get("cross_applies", []):
            if dep in changed_ids and nid not in changed_ids:
                dep_n = nodes.get(dep, {})
                issues.append((nid, n, f"depends on recently changed {dep} ({dep_n.get('name', '?')})"))

    if not issues:
        print("✓ No cascade issues detected")
        return

    print(f"⚠ {len(issues)} cascade issue(s):")
    for nid, n, reason in issues:
        print(f"  [{nid}] {n.get('name', '?'):24} — {reason}")
        print(f"         → skill.py evolve {nid} --mode FIX --trigger cascade")


def cmd_add(args, reg: dict):
    nodes = reg.setdefault("nodes", {})
    nid = args.id
    if nid in nodes:
        print(f"ERROR: '{nid}' already exists. Use 'update' command.")
        sys.exit(1)

    full_tok = getattr(args, "full_tokens", 300)
    nodes[nid] = {
        "name": args.name,
        "type": getattr(args, "type", "skill"),
        "surface": getattr(args, "surface", "claude-code"),
        "path": getattr(args, "path", ""),
        "tags": (getattr(args, "tags", "") or "").split(),
        "connects_to": [],
        "cross_applies": [],
        "hardness": getattr(args, "hardness", "soft-hook"),
        "trigger_keywords": (getattr(args, "keywords", "") or "").split(),
        "meta_summary": getattr(args, "summary", ""),
        "meta_tokens": 60,
        "full_tokens": full_tok,
        "health": default_health(full_tok),
        "lineage": {
            "version": "1.0", "parent": None, "evolution_mode": None,
            "created": TODAY, "diff_path": None, "session_source": None
        },
        "access": {
            "tier": getattr(args, "tier", "private"),
            "source_commit": "000000",
            "installed_at": TODAY
        },
        "bundle": {"co_occurs_with": {}, "never_with": [], "bundle_score": 0.5},
        "memory_nodes": [],
        "last_updated": TODAY,
        "deprecated": False
    }
    save_registry(reg)
    print(f"Added: [{nid}] {args.name}")

    try:
        subprocess.run(["git", "-C", str(SKILLS_DIR), "add", "-A"], capture_output=True, timeout=10)
        subprocess.run(["git", "-C", str(SKILLS_DIR), "commit", "-m", f"registry: add {nid} ({args.name})"],
                       capture_output=True, timeout=10)
    except Exception:
        pass


def cmd_gc(args, reg: dict):
    ARCHIVE_DIR = SKILLS_DIR / "_archive"
    ARCHIVE_DIR.mkdir(exist_ok=True)
    nodes = reg.get("nodes", {})
    dry = getattr(args, "dry_run", False)

    THRESHOLDS = {"DEC": -1, "ERR": -1, "skill": 0.08, "mcp": 0.05, "meta-skill": -1}
    now_ts = datetime.utcnow().isoformat()
    archived = []
    kept = {}

    for nid, n in nodes.items():
        ntype = n.get("type", "skill")
        thresh = THRESHOLDS.get(ntype, 0.08)
        hs = health_score(n.get("health", {}))
        is_deprecated = n.get("deprecated", False)

        has_incoming = any(
            nid in other.get("connects_to", []) + other.get("cross_applies", []) + other.get("memory_nodes", [])
            for other in nodes.values()
        )

        should_archive = (
            is_deprecated or
            (thresh > 0 and hs < thresh and not has_incoming)
        )

        if should_archive:
            archived.append(n)
        else:
            kept[nid] = n

    if not dry:
        month = date.today().strftime("%Y-%m")
        arch_file = ARCHIVE_DIR / f"skills_{month}.jsonl"
        with open(arch_file, "a", encoding="utf-8") as f:
            for n in archived:
                f.write(json.dumps({"archived_at": now_ts, **n}) + "\n")
        reg["nodes"] = kept
        save_registry(reg)

    print(f"GC {'(dry-run) ' if dry else ''}complete:")
    print(f"  Kept: {len(kept)}  Archived: {len(archived)}")
    if archived:
        for n in archived:
            print(f"    [{n.get('name', '?')}] health={health_score(n.get('health', {})):.2f}  deprecated={n.get('deprecated', False)}")


def cmd_show(reg: dict):
    nodes = reg.get("nodes", {})
    if not nodes:
        print("Registry is empty")
        return

    by_type = defaultdict(int)
    by_tier = defaultdict(int)
    by_hardness = defaultdict(int)
    total_health = 0.0
    alerts = 0
    deprecated = 0

    for n in nodes.values():
        by_type[n.get("type", "?")] += 1
        by_tier[n.get("access", {}).get("tier", "?")] += 1
        by_hardness[n.get("hardness", "?")] += 1
        h = n.get("health", {})
        hs = health_score(h)
        total_health += hs
        if hs < h.get("alert_threshold", 0.60) and not n.get("deprecated"):
            alerts += 1
        if n.get("deprecated"):
            deprecated += 1

    avg_h = total_health / max(1, len(nodes))
    evograph_edges = 0
    if EVOGRAPH.exists():
        evograph_edges = sum(1 for l in EVOGRAPH.read_text().splitlines() if l.strip())

    print(f"IGSL Skill Registry v{reg.get('version', '?')}")
    print(f"  Total nodes:   {len(nodes)}")
    print(f"  Deprecated:    {deprecated}")
    print(f"  Avg health:    {avg_h:.2f}")
    print(f"  Health alerts: {alerts}")
    print(f"  EvoGraph:      {evograph_edges} evolution edges")
    print(f"\nBy type:     {dict(sorted(by_type.items()))}")
    print(f"By tier:     {dict(sorted(by_tier.items()))}")
    print(f"By hardness: {dict(sorted(by_hardness.items()))}")
    print(f"\nRegistry path: {REGISTRY}")
    if EVOGRAPH.exists():
        print(f"EvoGraph path: {EVOGRAPH}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        description="IGSL Skill Graph CLI v2",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd")

    # scan
    sc = sub.add_parser("scan")
    sc.add_argument("--session-start", action="store_true", dest="session_start")

    # query
    sq = sub.add_parser("query")
    sq.add_argument("query")
    sq.add_argument("--top", type=int, default=5)
    sq.add_argument("--type", default="")
    sq.add_argument("--project", default="")

    # load
    sl = sub.add_parser("load")
    sl.add_argument("id")
    sl.add_argument("--dry-run", action="store_true", dest="dry_run")
    sl.add_argument("--no-health", action="store_true", dest="no_health")

    # health
    sh = sub.add_parser("health")
    sh_sub = sh.add_subparsers(dest="hcmd")
    sh_r = sh_sub.add_parser("record")
    sh_r.add_argument("id")
    sh_r.add_argument("--applied", type=int, default=1, choices=[0, 1])
    sh_r.add_argument("--completed", type=int, default=1, choices=[0, 1])
    sh_r.add_argument("--fallback", type=int, default=0, choices=[0, 1])
    sh_s = sh_sub.add_parser("show")
    sh_s.add_argument("id", nargs="?")
    sh_sub.add_parser("alert")

    # evolve
    ev = sub.add_parser("evolve")
    ev.add_argument("id")
    ev.add_argument("--mode", required=True, choices=["FIX", "DERIVED", "CAPTURED"])
    ev.add_argument("--session", default="manual")
    ev.add_argument("--trigger", default="manual")

    # lineage
    li = sub.add_parser("lineage")
    li.add_argument("id")

    # bundle
    bu = sub.add_parser("bundle")
    bu_sub = bu.add_subparsers(dest="bcmd")
    bu_sg = bu_sub.add_parser("suggest")
    bu_sg.add_argument("id")
    bu_rec = bu_sub.add_parser("record")
    bu_rec.add_argument("ids", nargs="+")

    # access
    ac = sub.add_parser("access")
    ac.add_argument("id", nargs="?")

    # cascade
    sub.add_parser("cascade")

    # add
    ad = sub.add_parser("add")
    ad.add_argument("--id", required=True)
    ad.add_argument("--name", required=True)
    ad.add_argument("--type", default="skill", dest="type")
    ad.add_argument("--surface", default="claude-code")
    ad.add_argument("--path", default="")
    ad.add_argument("--tags", default="")
    ad.add_argument("--hardness", default="soft-hook")
    ad.add_argument("--keywords", default="")
    ad.add_argument("--summary", default="")
    ad.add_argument("--tier", default="private")
    ad.add_argument("--full-tokens", type=int, default=300, dest="full_tokens")

    # gc
    gc_p = sub.add_parser("gc")
    gc_p.add_argument("--dry-run", action="store_true", dest="dry_run")

    # show
    sub.add_parser("show")

    args = p.parse_args()
    if not args.cmd:
        p.print_help()
        sys.exit(0)

    reg = load_registry()

    if args.cmd == "scan":
        cmd_scan(args, reg)
    elif args.cmd == "query":
        cmd_query(args, reg)
    elif args.cmd == "load":
        cmd_load(args, reg)
    elif args.cmd == "health":
        if not args.hcmd:
            sh.print_help(); sys.exit(0)
        if args.hcmd == "record":
            cmd_health_record(args, reg)
        elif args.hcmd == "show":
            cmd_health_show(args, reg)
        elif args.hcmd == "alert":
            cmd_health_alert(args, reg)
    elif args.cmd == "evolve":
        cmd_evolve(args, reg)
    elif args.cmd == "lineage":
        cmd_lineage(args, reg)
    elif args.cmd == "bundle":
        if args.bcmd == "suggest":
            cmd_bundle_suggest(args, reg)
        elif args.bcmd == "record":
            cmd_bundle_record(args, reg)
    elif args.cmd == "access":
        cmd_access_check(args, reg)
    elif args.cmd == "cascade":
        cmd_cascade(args, reg)
    elif args.cmd == "add":
        cmd_add(args, reg)
    elif args.cmd == "gc":
        cmd_gc(args, reg)
    elif args.cmd == "show":
        cmd_show(reg)


if __name__ == "__main__":
    main()
