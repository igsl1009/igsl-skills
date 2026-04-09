#!/usr/bin/env python3
"""
IGSL Chat Retrieval CLI v2 — query.py
Searches pre-indexed chat history using BM25 on chat-index.jsonl.

Commands:
  search   "keywords" [--top N] [--since YYYY-MM] [--tag t1 t2]
  index    [--rebuild]    Stats / rebuild chat-index.jsonl
  show                    List all indexed chats
  chunk    CHAT_ID        Load pre-chunked content for a chat
"""

import json, sys, re, math, argparse
from pathlib import Path
from datetime import date, datetime
from collections import defaultdict

MEM_DIR    = Path.home() / ".igsl-skills" / "memory"
INDEX_FILE = MEM_DIR / "chat-index.jsonl"
CHUNKS_DIR = MEM_DIR / "chunks"
TODAY      = date.today().isoformat()

STOPWORDS = {
    "the","a","an","is","in","to","of","and","or","for","with","at","by",
    "on","it","this","that","was","are","be","from","as","not","we","i",
    "you","have","had","use","when","what","how","if","do","can","will",
    "also","about","after","into","then","there","these","they","so"
}


def tokenize(text: str) -> list:
    words = re.findall(r"[a-zA-Z0-9\-\_]+", text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 1]


def bm25_score(qtoks: list, dtoks: list, k1: float = 1.5, b: float = 0.75,
               avg_dl: float = 20.0) -> float:
    tf = defaultdict(int)
    for t in dtoks: tf[t] += 1
    dl = len(dtoks)
    score = 0.0
    for q in qtoks:
        if q in tf:
            f = tf[q]
            idf = math.log(1.0 + 1.0 / (0.5 + f))
            score += idf * f * (k1 + 1.0) / (f + k1 * (1.0 - b + b * dl / avg_dl))
    return score


def load_index() -> list:
    if not INDEX_FILE.exists():
        return []
    chats = []
    for line in INDEX_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            chats.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return chats


def score_chat(chat: dict, qtoks: list) -> float:
    doc = (
        chat.get("title", "") + " "
        + " ".join(chat.get("tags", [])) + " "
        + " ".join(chat.get("concepts", []))
    )
    dtoks = tokenize(doc)
    return bm25_score(qtoks, dtoks)


def parse_date(s: str):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        try:
            return datetime.strptime(s, "%Y-%m").date()
        except ValueError:
            return None


def cmd_search(args, chats: list):
    qtoks = tokenize(args.query)
    if not qtoks:
        print(f"No keywords extracted from: '{args.query}'")
        return

    since_str = getattr(args, "since", None)
    since_date = parse_date(since_str) if since_str else None
    tag_filter = getattr(args, "tag", [])

    scored = []
    for chat in chats:
        if since_date:
            chat_date = parse_date(chat.get("d", "2000-01-01"))
            if chat_date and chat_date < since_date:
                continue
        if tag_filter:
            chat_tags = set(chat.get("tags", []))
            if not any(t in chat_tags for t in tag_filter):
                continue

        s = score_chat(chat, qtoks)
        if s > 0:
            scored.append((chat, s))

    scored.sort(key=lambda x: x[1], reverse=True)
    top = scored[:getattr(args, "top", 5)]

    if not top:
        print(f"No chats matched: '{args.query}'")
        return

    print(f"# CHAT SEARCH: '{args.query}' | {len(top)} match(es)")
    print("─" * 60)

    for chat, score in top:
        chat_id = chat.get("id", "?")
        chat_date = chat.get("d", "?")
        title = chat.get("title", "(no title)")
        tags = " ".join(chat.get("tags", []))
        concepts = " ".join(chat.get("concepts", [])[:5])

        print(f"\n[{chat_id}] {chat_date}  score={score:.3f}")
        print(f"  Title:    {title}")
        print(f"  Tags:     {tags}")
        print(f"  Concepts: {concepts}")

        chunk_file = CHUNKS_DIR / f"{chat_id}.md"
        if chunk_file.exists():
            print(f"  Chunk:    python3 ~/.igsl-skills/memory/query.py chunk {chat_id}")

    print(f"\n─ {len(top)} chat(s) shown")


def cmd_index(args, chats: list):
    rebuild = getattr(args, "rebuild", False)

    if rebuild:
        print("Rebuild would scan ~/.claude/conversations/ or transcript archives.")
        print(f"Current index: {INDEX_FILE}")
        return

    if not chats:
        print("chat-index.jsonl is empty or not found.")
        return

    by_tag = defaultdict(int)
    by_month = defaultdict(int)

    for chat in chats:
        for tag in chat.get("tags", []):
            by_tag[tag] += 1
        d = chat.get("d", "")
        if len(d) >= 7:
            by_month[d[:7]] += 1

    print(f"Chat Index Stats")
    print(f"  Total chats indexed: {len(chats)}")
    print(f"  Date range: {min(c.get('d','?') for c in chats)} → {max(c.get('d','?') for c in chats)}")
    print(f"\nTop tags:")
    for tag, count in sorted(by_tag.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"  {tag:<20} {count}")
    print(f"\nBy month:")
    for month, count in sorted(by_month.items(), reverse=True)[:6]:
        print(f"  {month}  {count} chat(s)")


def cmd_show(chats: list):
    if not chats:
        print("No chats indexed.")
        return

    sorted_chats = sorted(chats, key=lambda c: c.get("d", ""), reverse=True)
    print(f"Indexed chats ({len(sorted_chats)} total):")
    print("─" * 60)
    for c in sorted_chats:
        cid = c.get("id", "?")
        d   = c.get("d", "?")
        title = c.get("title", "?")[:50]
        tags = " ".join(c.get("tags", [])[:4])
        chunk_exists = "📄" if (CHUNKS_DIR / f"{cid}.md").exists() else "  "
        print(f"  {chunk_exists} [{cid}] {d}  {title}  |{tags}|")


def cmd_chunk(args, chats: list):
    chat_id = args.id
    chunk_file = CHUNKS_DIR / f"{chat_id}.md"

    if not chunk_file.exists():
        chat = next((c for c in chats if c.get("id") == chat_id), None)
        if chat:
            print(f"[{chat_id}] {chat.get('d','?')}: {chat.get('title','?')}")
            print(f"  Concepts: {' '.join(chat.get('concepts',[]))}")
            print(f"\nChunk file not found: {chunk_file}")
        else:
            print(f"Chat '{chat_id}' not found in index.")
        return

    print(f"# Chunk: {chat_id}")
    print(chunk_file.read_text(encoding="utf-8"))


def main():
    p = argparse.ArgumentParser(
        description="IGSL Chat Retrieval CLI v2",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd")

    ss = sub.add_parser("search")
    ss.add_argument("query")
    ss.add_argument("--top", type=int, default=5)
    ss.add_argument("--since", default=None)
    ss.add_argument("--tag", nargs="*", default=[])

    si = sub.add_parser("index")
    si.add_argument("--rebuild", action="store_true")

    sub.add_parser("show")

    sc = sub.add_parser("chunk")
    sc.add_argument("id")

    args = p.parse_args()
    if not args.cmd:
        p.print_help()
        sys.exit(0)

    chats = load_index()

    if args.cmd == "search":
        cmd_search(args, chats)
    elif args.cmd == "index":
        cmd_index(args, chats)
    elif args.cmd == "show":
        cmd_show(chats)
    elif args.cmd == "chunk":
        cmd_chunk(args, chats)


if __name__ == "__main__":
    main()
