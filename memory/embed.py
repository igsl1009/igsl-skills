#!/usr/bin/env python3
"""
IGSL Embedding Wrapper v2 — embed.py
Local semantic embeddings via sentence-transformers all-MiniLM-L6-v2.
Gracefully degrades to BM25-only if sentence-transformers not installed.

Commands:
  build                 Build embeddings for all nodes
  search "query"        Hybrid BM25+semantic search
  sim NODE_ID1 NODE_ID2 Cosine similarity between two nodes
"""

import sys, json, re, math
from pathlib import Path

MEM_DIR     = Path.home() / ".igsl-skills" / "memory"
NODES_FILE  = MEM_DIR / "nodes.jsonl"
EMBEDS_FILE = MEM_DIR / "nodes.embeddings.npz"
MODEL_NAME  = "all-MiniLM-L6-v2"

_model = None


def _load_model():
    global _model
    if _model is not None:
        return _model
    try:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_NAME)
        return _model
    except ImportError:
        return None
    except Exception as e:
        print(f"[embed] Model load failed: {e}", file=sys.stderr)
        return None


def embed_text(text: str):
    """Embed a single text string. Returns np.ndarray or None."""
    model = _load_model()
    if model is None:
        return None
    try:
        import numpy as np
        vec = model.encode([text], convert_to_numpy=True, normalize_embeddings=True)[0]
        return vec.astype(np.float32)
    except Exception:
        return None


def cosine_sim(a, b) -> float:
    try:
        import numpy as np
        if a is None or b is None:
            return 0.0
        denom = (np.linalg.norm(a) * np.linalg.norm(b))
        if denom < 1e-9:
            return 0.0
        return float(np.dot(a, b) / denom)
    except Exception:
        return 0.0


def cosine_for_query(query: str, node: dict) -> float:
    node_text = " ".join(node.get("tags", [])) + " " + node.get("c", "")
    qvec = embed_text(query)
    nvec = embed_text(node_text)
    return cosine_sim(qvec, nvec)


def node_to_text(node: dict) -> str:
    parts = [
        " ".join(node.get("tags", [])),
        node.get("c", "")
    ]
    return " ".join(p for p in parts if p)


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


def build_embeddings(nodes: dict = None):
    try:
        import numpy as np
    except ImportError:
        print("[embed] numpy not available. Install: pip install numpy --break-system-packages")
        return False

    model = _load_model()
    if model is None:
        print("[embed] sentence-transformers not available.")
        print("Install: pip install sentence-transformers --break-system-packages")
        return False

    if nodes is None:
        nodes = load_nodes()

    if not nodes:
        print("[embed] No nodes to embed.")
        return False

    texts = [node_to_text(n) for n in nodes.values()]
    ids = list(nodes.keys())

    print(f"[embed] Embedding {len(ids)} nodes with {MODEL_NAME}...")
    vecs = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True,
                        show_progress_bar=True, batch_size=32)

    embed_dict = {nid: vecs[i] for i, nid in enumerate(ids)}
    np.savez_compressed(str(EMBEDS_FILE), **embed_dict)
    print(f"[embed] Saved {len(ids)} embeddings to {EMBEDS_FILE}")
    return True


def load_embeddings() -> dict:
    if not EMBEDS_FILE.exists():
        return {}
    try:
        import numpy as np
        data = np.load(str(EMBEDS_FILE))
        return {k: data[k] for k in data.files}
    except Exception as e:
        print(f"[embed] Failed to load embeddings: {e}", file=sys.stderr)
        return {}


def hybrid_search(query: str, nodes: dict, top_k: int = 5,
                  bm25_weight: float = 0.35,
                  semantic_weight: float = 0.45,
                  node_weight: float = 0.20) -> list:
    from collections import defaultdict

    STOP = {"the","a","an","is","in","to","of","and","or","for","with","at","by",
            "on","it","this","that","was","are","be","from","as","not"}

    def tok(text):
        return [w for w in re.findall(r"[a-zA-Z0-9\-\_]+", text.lower())
                if w not in STOP and len(w) > 1]

    def bm25_score(qtoks, dtoks, k1=1.2, b=0.75, avg=15.0):
        tf = defaultdict(int)
        for t in dtoks: tf[t] += 1
        dl = len(dtoks)
        score = 0.0
        for q in qtoks:
            if q in tf:
                f = tf[q]
                idf = math.log(1.0 + 1.0/(0.5+f))
                score += idf * f*(k1+1.0)/(f+k1*(1-b+b*dl/avg))
        return score

    qtoks = tok(query)
    qvec = embed_text(query)
    embeds = load_embeddings() if qvec is not None else {}

    scored = []
    for nid, n in nodes.items():
        doc = " ".join(n.get("tags", [])) + " " + n.get("c", "")
        b_score = bm25_score(qtoks, tok(doc))
        s_score = cosine_sim(qvec, embeds.get(nid)) if nid in embeds else 0.0
        w_score = float(n.get("w", 0.5))

        final = (bm25_weight * b_score +
                 semantic_weight * s_score +
                 node_weight * w_score)

        if final > 0:
            scored.append((nid, final))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


def cmd_build(args):
    nodes = load_nodes()
    success = build_embeddings(nodes)
    if not success:
        sys.exit(1)


def cmd_search(args):
    nodes = load_nodes()
    results = hybrid_search(args.query, nodes, top_k=getattr(args, "top", 5))
    if not results:
        print(f"No results for: '{args.query}'")
        return
    print(f"Hybrid search: '{args.query}'  ({len(results)} results)")
    for nid, score in results:
        n = nodes.get(nid, {})
        print(f"  [{nid}] score={score:.3f}  w={n.get('w', 0):.2f}  [{n.get('t', '?')}]  {n.get('c', '')[:60]}")


def cmd_sim(args):
    nodes = load_nodes()
    n1 = nodes.get(args.id1)
    n2 = nodes.get(args.id2)
    if not n1 or not n2:
        print(f"ERROR: node not found")
        sys.exit(1)
    v1 = embed_text(node_to_text(n1))
    v2 = embed_text(node_to_text(n2))
    sim = cosine_sim(v1, v2)
    print(f"Similarity [{args.id1}] <-> [{args.id2}]: {sim:.4f}")


def main():
    import argparse
    p = argparse.ArgumentParser(description="IGSL Embedding CLI")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("build", help="Build embeddings for all nodes")

    ss = sub.add_parser("search", help="Hybrid search")
    ss.add_argument("query")
    ss.add_argument("--top", type=int, default=5)

    sm = sub.add_parser("sim", help="Node similarity")
    sm.add_argument("id1")
    sm.add_argument("id2")

    args = p.parse_args()
    if not args.cmd:
        model = _load_model()
        if model:
            print(f"[embed] Model available: {MODEL_NAME}")
        else:
            print(f"[embed] sentence-transformers not installed. BM25-only mode.")
            print(f"Install: pip install sentence-transformers --break-system-packages")
        return

    if args.cmd == "build":
        cmd_build(args)
    elif args.cmd == "search":
        cmd_search(args)
    elif args.cmd == "sim":
        cmd_sim(args)


if __name__ == "__main__":
    main()
