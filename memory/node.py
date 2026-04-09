#!/usr/bin/env python3
"""
IGSL Memory Node CLI v2 — node.py
Manages typed knowledge nodes with weight decay, BM25+semantic search,
temporal validity, contradiction detection, and cross-project linking.

Node types: DEC | PAT | ARCH | ART | LOOP | GEN | ERR
Content format: compressed key-value, max 120 chars

Commands:
  add      --id X --type T --tags "a b" --content "..." --links A B --src xxxx
  update   ID --content "..." [--tags "a b"] [--links A B]
  fetch    ID [--depth 1]
  query    "keywords" [--top 5] [--type T] [--project P] [--all]
  link     FROM_ID TO_ID
  close    LOOP_ID [--note "text"]
  gc       [--dry-run]
  active
  show
"""

import json, sys, re, math, argparse
from pathlib import Path
from datetime import date, datetime
from collections import defaultdict

MEM_DIR    = Path.home() / ".igsl-skills" / "memory"
NODES_FILE = MEM_DIR / "nodes.jsonl"
INDEX_FILE = MEM_DIR / "active-index.json"
ARCH_DIR   = MEM_DIR / "archive"
TODAY      = date.today().isoformat()

# ── Type configuration ────────────────────────────────────────────────────────

HALF_LIFE = {
    "DEC": 99999,
    "PAT": 30,
    "ARCH": 60,
    "ART": 14,
    "LOOP": 99999,
    "GEN": 90,
    "ERR": 180
}

MIN_WEIGHT = {
    "DEC": 0.50,
    "PAT": 0.02,
    "ARCH": 0.10,
    "ART": 0.01,
    "LOOP": 0.30,
    "GEN": 0.05,
    "ERR": 0.20
}

ARCHIVE_THRESH = {
    "DEC": -1.0,
    "PAT": 0.05,
    "ARCH": 0.08,
    "ART": 0.03,
    "LOOP": 0.20,
    "GEN": 0.05,
    "ERR": -1.0
}

VALID_TYPES = set(HALF_LIFE.keys())

STOPWORDS = {
    "the","a","an","is","in","to","of","and","or","for","with","at","by",
    "on","it","this","that","was","are","be","from","as","not","we","i",
    "you","have","had","use","when","what","how","if","do","can","will"
}

# ── I/O ───────────────────────────────────────────────────────────────────────

def load_nodes() -> dict:
    if not NODES_FILE.exists():
        return {}
    nodes = {}
    for line in NODES_FILE.read_text(encoding="utf-8").splitlines():
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

def save_nodes(nodes: dict):
    MEM_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(n, ensure_ascii=False, separators=(",", ":"))
        for n in sorted(nodes.values(), key=lambda x: x.get("id", ""))
    ]
    tmp = NODES_FILE.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(NODES_FILE)

def load_index() -> dict:
    if INDEX_FILE.exists():
        try:
            return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"updated": TODAY, "nodes": []}

def save_index(data: dict):
    MEM_DIR.mkdir(parents=True, exist_ok=True)
    tmp = INDEX_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(INDEX_FILE)

# ── Weight ────────────────────────────────────────────────────────────────────

def compute_weight(node: dict) -> float:
    t = node.get("t", "GEN")
    hl = HALF_LIFE.get(t, 30)
    mn = MIN_WEIGHT.get(t, 0.02)
    base = float(node.get("w", 0.5))
    ts_str = node.get("ts", TODAY)

    try:
        days = (date.today() - date.fromisoformat(ts_str)).days
        decayed = base * (0.5 ** (days / hl))
    except ValueError:
        decayed = base

    refs = int(node.get("refs7d", 0))
    boosted = decayed + 0.15 * min(refs, 5)
    return round(max(mn, min(1.0, boosted)), 4)

def bump_weight(node: dict, amount: float = 0.1) -> dict:
    node["w"] = round(min(1.0, float(node.get("w", 0.5)) + amount), 4)
    node["refs7d"] = node.get("refs7d", 0) + 1
    node["ts"] = TODAY
    return node

def is_valid(node: dict) -> bool:
    valid_at = node.get("valid_at")
    invalid_at = node.get("invalid_at")
    if valid_at and date.fromisoformat(valid_at) > date.today():
        return False
    if invalid_at and date.fromisoformat(invalid_at) <= date.today():
        return False
    return True

# ── Search ────────────────────────────────────────────────────────────────────

def tokenize(text: str) -> list:
    words = re.findall(r"[a-zA-Z0-9\-\_]+", text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 1]

def bm25(qtoks: list, dtoks: list, k1: float = 1.2, b: float = 0.75,
         avg_dl: float = 15.0) -> float:
    tf = defaultdict(int)
    for t in dtoks:
        tf[t] += 1
    dl = len(dtoks)
    score = 0.0
    for q in qtoks:
        if q in tf:
            f = tf[q]
            idf = math.log(1.0 + 1.0 / (0.5 + f))
            score += idf * f * (k1 + 1.0) / (f + k1 * (1.0 - b + b * dl / avg_dl))
    return score

def score_node(node: dict, qtoks: list) -> float:
    doc = " ".join(node.get("tags", [])) + " " + node.get("c", "")
    dtoks = tokenize(doc)
    text_s = bm25(qtoks, dtoks)
    return text_s * (0.6 + 0.4 * float(node.get("w", 0.5)))

# ── Formatting ────────────────────────────────────────────────────────────────

def fmt_node(node: dict, brief: bool = False) -> str:
    nid   = node.get("id", "?")
    ntype = node.get("t", "?")
    w     = float(node.get("w", 0))
    tags  = " ".join(node.get("tags", []))
    c     = node.get("c", "")
    links = " ".join(node.get("links", []))
    src   = node.get("src", "")
    ts    = node.get("ts", "")

    if brief:
        return f"{nid:<14} w={w:.2f}  [{ntype}]  {c[:75]}"

    lines = [f"[{nid}] {ntype}  w={w:.2f}  ts={ts}  src={src}"]
    if tags:
        lines.append(f"  tags:  {tags}")
    lines.append(f"  c:     {c}")
    if links:
        lines.append(f"  links: {links}")

    valid_at   = node.get("valid_at")
    invalid_at = node.get("invalid_at")
    if valid_at or invalid_at:
        lines.append(f"  valid: {valid_at or 'always'} → {invalid_at or 'never'}")

    return "\n".join(lines)

# ── Contradiction detection ───────────────────────────────────────────────────

def find_contradicting_node(new_content: str, nodes: dict, ntype: str = "DEC") -> tuple:
    if ntype not in ("DEC", "PAT"):
        return (None, 0.0)
    try:
        sys.path.insert(0, str(MEM_DIR))
        from embed import embed_text, cosine_sim
        new_vec = embed_text(new_content)
        best_id, best_score = None, 0.0
        for nid, n in nodes.items():
            if n.get("t") != ntype:
                continue
            if not is_valid(n):
                continue
            existing_vec = embed_text(n.get("c", ""))
            sim = cosine_sim(new_vec, existing_vec)
            if sim > best_score:
                best_score = sim
                best_id = nid
        return (best_id, best_score)
    except Exception:
        return (None, 0.0)

# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_add(args, nodes: dict):
    nid = args.id
    if nid in nodes:
        print(f"ERROR: '{nid}' already exists. Use 'update' instead.")
        sys.exit(1)

    ntype = (args.type or "GEN").upper()
    if ntype not in VALID_TYPES:
        print(f"ERROR: type must be one of {sorted(VALID_TYPES)}")
        sys.exit(1)

    content = (args.content or "").strip()
    if len(content) > 120:
        print(f"WARNING: content {len(content)} chars, truncating to 120")
        content = content[:120]

    tags = (args.tags or "").split()
    links = args.links or []
    src = (args.src or "")[:6]

    # Contradiction check for DEC/PAT nodes
    if ntype in ("DEC", "PAT"):
        contra_id, contra_score = find_contradicting_node(content, nodes, ntype)
        if contra_score > 0.85 and contra_id:
            contra_node = nodes.get(contra_id, {})
            print(f"WARNING: High similarity ({contra_score:.2f}) with existing node [{contra_id}]")
            print(f"  Existing: {contra_node.get('c', '')}")
            print(f"  New:      {content}")
            print(f"  Consider: node.py update {contra_id} --content '...' instead")

    node = {
        "id":     nid,
        "t":      ntype,
        "tags":   tags,
        "w":      0.8,
        "ts":     TODAY,
        "links":  links,
        "src":    src,
        "c":      content,
        "refs7d": 1,
    }
    if hasattr(args, "valid_at") and args.valid_at:
        node["valid_at"] = args.valid_at
    if hasattr(args, "invalid_at") and args.invalid_at:
        node["invalid_at"] = args.invalid_at

    nodes[nid] = node

    for lid in links:
        if lid in nodes:
            nodes[lid] = bump_weight(nodes[lid], 0.05)

    save_nodes(nodes)
    print(f"Added: {fmt_node(node, brief=True)}")


def cmd_update(args, nodes: dict):
    nid = args.id
    if nid not in nodes:
        print(f"ERROR: '{nid}' not found. Use 'add' instead.")
        sys.exit(1)

    node = nodes[nid]
    changed = False

    if args.content:
        c = args.content.strip()
        if len(c) > 120:
            print(f"WARNING: content truncated to 120 chars")
            c = c[:120]
        node["c"] = c
        changed = True

    if args.tags:
        node["tags"] = args.tags.split()
        changed = True

    if args.links:
        new_links = [l for l in args.links if l not in node.get("links", [])]
        node.setdefault("links", []).extend(new_links)
        for lid in new_links:
            if lid in nodes:
                nodes[lid] = bump_weight(nodes[lid], 0.05)
        changed = True

    if changed:
        node["w"] = round(max(float(node.get("w", 0.5)), 0.7), 4)
        node["ts"] = TODAY
        nodes[nid] = node
        save_nodes(nodes)
        print(f"Updated: {fmt_node(node, brief=True)}")
    else:
        print("No changes specified. Use --content, --tags, or --links.")


def cmd_fetch(args, nodes: dict):
    nid = args.id
    if nid not in nodes:
        print(f"ERROR: '{nid}' not found.")
        sys.exit(1)

    node = nodes[nid]
    nodes[nid] = bump_weight(node, 0.1)
    save_nodes(nodes)

    print(fmt_node(node))

    depth = getattr(args, "depth", 1)
    if depth >= 1:
        links = node.get("links", [])
        if links:
            print(f"\n  linked nodes ({len(links)}):")
            for lid in links:
                ln = nodes.get(lid)
                if ln:
                    nodes[lid] = bump_weight(ln, 0.05)
                    print("  " + fmt_node(ln, brief=True))
            save_nodes(nodes)


def cmd_query(args, nodes: dict):
    qtoks = tokenize(args.query)
    if not qtoks:
        print(f"No keywords extracted from: '{args.query}'")
        return

    valid_only = not getattr(args, "all_nodes", False)
    ntype_filter = getattr(args, "type", "").upper()
    proj_filter = getattr(args, "project", "").upper()

    scored = []
    for nid, n in nodes.items():
        if valid_only and not is_valid(n):
            continue
        if ntype_filter and n.get("t") != ntype_filter:
            continue
        if proj_filter and not nid.startswith(proj_filter):
            continue

        s = score_node(n, qtoks)
        if s > 0:
            scored.append((nid, n, s))

    scored.sort(key=lambda x: x[2], reverse=True)
    top = scored[:getattr(args, "top", 5)]

    if not top:
        print(f"No results for: '{args.query}'")
        return

    total_tok_est = len(top) * 15
    link_ids_shown = set()

    print(f"# QUERY: '{args.query}'  |  {len(top)} nodes  |  ~{total_tok_est} tokens")
    print("─" * 56)

    for nid, n, score in top:
        nodes[nid] = bump_weight(n, 0.1)
        print()
        print(fmt_node(n))
        print(f"  relevance={score:.3f}")

        for lid in n.get("links", []):
            if lid not in link_ids_shown and lid in nodes:
                ln = nodes[lid]
                bump_weight(ln, 0.05)
                print(f"  → {fmt_node(ln, brief=True)}")
                link_ids_shown.add(lid)

    save_nodes(nodes)
    print(f"\n─ Retrieved ~{total_tok_est + len(link_ids_shown)*15} tokens total")


def cmd_link(args, nodes: dict):
    src, dst = args.from_id, args.to_id
    for nid in [src, dst]:
        if nid not in nodes:
            print(f"ERROR: '{nid}' not found.")
            sys.exit(1)

    if dst not in nodes[src].get("links", []):
        nodes[src].setdefault("links", []).append(dst)
        nodes[dst] = bump_weight(nodes[dst], 0.05)
        save_nodes(nodes)
        print(f"Linked: {src} → {dst}")
    else:
        print(f"Link {src} → {dst} already exists")


def cmd_close(args, nodes: dict):
    nid = args.id
    if nid not in nodes:
        print(f"ERROR: '{nid}' not found.")
        sys.exit(1)

    node = nodes[nid]
    note = (getattr(args, "note", "") or "").strip()
    old_c = node.get("c", "")

    if old_c.startswith("○"):
        new_c = "✓" + old_c[1:]
    else:
        new_c = "✓ " + old_c

    if note:
        new_c = f"{new_c[:100]} | {note}"
    node["c"] = new_c[:120]
    node["w"] = 0.3
    node["ts"] = TODAY
    node["invalid_at"] = TODAY

    nodes[nid] = node
    save_nodes(nodes)
    print(f"Closed: {fmt_node(node, brief=True)}")


def cmd_gc(args, nodes: dict):
    ARCH_DIR.mkdir(parents=True, exist_ok=True)
    dry = getattr(args, "dry_run", False)
    month = date.today().strftime("%Y-%m")
    arch_file = ARCH_DIR / f"nodes_{month}.jsonl"

    archived = []
    kept = {}
    now_iso = datetime.utcnow().isoformat()

    incoming = defaultdict(list)
    for nid, n in nodes.items():
        for lid in n.get("links", []):
            incoming[lid].append(nid)

    for nid, n in nodes.items():
        ntype = n.get("t", "GEN")
        thresh = ARCHIVE_THRESH.get(ntype, 0.05)
        new_w = compute_weight(n)
        n["w"] = new_w

        try:
            age_days = (date.today() - date.fromisoformat(n.get("ts", TODAY))).days
        except ValueError:
            age_days = 0

        has_incoming = bool(incoming.get(nid))
        is_closed_loop = ntype == "LOOP" and n.get("c", "").startswith("✓")

        should_archive = (
            (thresh > 0 and new_w < thresh and not has_incoming and age_days > 90)
            or (is_closed_loop and new_w < 0.2 and age_days > 30)
        )

        if should_archive:
            archived.append({**n, "archived_at": now_iso})
        else:
            kept[nid] = n

    if not dry:
        save_nodes(kept)
        if archived:
            with open(arch_file, "a", encoding="utf-8") as f:
                for n in archived:
                    f.write(json.dumps(n, ensure_ascii=False, separators=(",", ":")) + "\n")

    print(f"GC {'(dry-run) ' if dry else ''}complete:")
    print(f"  Active: {len(kept)}  Archived: {len(archived)}")
    if archived:
        print(f"  Archived to: {arch_file}")
        for n in archived[:5]:
            print(f"    [{n.get('id', '?')}] {n.get('t', '?')} w={n.get('w', 0):.2f} — {n.get('c', '')[:40]}")


def cmd_active(nodes: dict):
    scored = []
    for nid, n in nodes.items():
        if not is_valid(n):
            continue
        w = compute_weight(n)
        n["w"] = w
        scored.append((nid, w))

    scored.sort(key=lambda x: x[1], reverse=True)
    top10 = [nid for nid, _ in scored[:10]]

    data = {
        "updated": TODAY,
        "nodes": top10,
        "weights": {nid: w for nid, w in scored[:10]}
    }
    save_index(data)

    print(f"ACTIVE[{TODAY}] — top {len(top10)} nodes by weight")
    for nid, w in scored[:10]:
        n = nodes.get(nid, {})
        print(f"  {nid:<14} w={w:.2f}  [{n.get('t', '?')}]  {n.get('c', '')[:50]}")


def cmd_show(nodes: dict):
    if not nodes:
        print("nodes.jsonl is empty or not found")
        return

    by_type = defaultdict(int)
    by_proj = defaultdict(int)
    total_w = 0.0
    open_loops = 0
    closed_loops = 0

    for nid, n in nodes.items():
        by_type[n.get("t", "?")] += 1
        proj = nid.split("-")[0] if "-" in nid else "?"
        by_proj[proj] += 1
        total_w += float(n.get("w", 0))
        if n.get("t") == "LOOP":
            if n.get("c", "").startswith("✓"):
                closed_loops += 1
            else:
                open_loops += 1

    avg_w = total_w / max(1, len(nodes))

    print(f"IGSL Memory Node Network v2")
    print(f"  Total nodes:  {len(nodes)}")
    print(f"  Avg weight:   {avg_w:.2f}")
    print(f"  Open loops:   {open_loops}")
    print(f"  Closed loops: {closed_loops}")
    print(f"\nBy type:    {dict(sorted(by_type.items()))}")
    print(f"By project: {dict(sorted(by_proj.items()))}")

    idx = load_index()
    print(f"\nActive index: {len(idx.get('nodes', []))} nodes  updated={idx.get('updated', '?')}")
    print(f"Nodes file: {NODES_FILE}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(
        description="IGSL Memory Node CLI v2",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd")

    # add
    a = sub.add_parser("add")
    a.add_argument("--id", required=True)
    a.add_argument("--type", default="GEN")
    a.add_argument("--tags", default="")
    a.add_argument("--content", required=True)
    a.add_argument("--links", nargs="*", default=[])
    a.add_argument("--src", default="")
    a.add_argument("--valid-at", default=None, dest="valid_at")
    a.add_argument("--invalid-at", default=None, dest="invalid_at")

    # update
    u = sub.add_parser("update")
    u.add_argument("id")
    u.add_argument("--content", default="")
    u.add_argument("--tags", default="")
    u.add_argument("--links", nargs="*", default=[])

    # fetch
    fe = sub.add_parser("fetch")
    fe.add_argument("id")
    fe.add_argument("--depth", type=int, default=1)

    # query
    q = sub.add_parser("query")
    q.add_argument("query")
    q.add_argument("--top", type=int, default=5)
    q.add_argument("--type", default="")
    q.add_argument("--project", default="")
    q.add_argument("--all", action="store_true", dest="all_nodes")

    # link
    lk = sub.add_parser("link")
    lk.add_argument("from_id")
    lk.add_argument("to_id")

    # close
    cl = sub.add_parser("close")
    cl.add_argument("id")
    cl.add_argument("--note", default="")

    # gc
    gc = sub.add_parser("gc")
    gc.add_argument("--dry-run", action="store_true", dest="dry_run")

    # active
    sub.add_parser("active")

    # show
    sub.add_parser("show")

    args = p.parse_args()
    if not args.cmd:
        p.print_help()
        sys.exit(0)

    nodes = load_nodes()

    if args.cmd == "add":
        cmd_add(args, nodes)
    elif args.cmd == "update":
        cmd_update(args, nodes)
    elif args.cmd == "fetch":
        cmd_fetch(args, nodes)
    elif args.cmd == "query":
        cmd_query(args, nodes)
    elif args.cmd == "link":
        cmd_link(args, nodes)
    elif args.cmd == "close":
        cmd_close(args, nodes)
    elif args.cmd == "gc":
        cmd_gc(args, nodes)
    elif args.cmd == "active":
        cmd_active(nodes)
    elif args.cmd == "show":
        cmd_show(nodes)


if __name__ == "__main__":
    main()
