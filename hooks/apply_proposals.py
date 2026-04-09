#!/usr/bin/env python3
"""
IGSL Proposal Review — apply_proposals.py
Interactive review and application of improvement proposals from _proposed/.

Usage:
  python3 apply_proposals.py [proposal_file]
  python3 apply_proposals.py --latest
  python3 apply_proposals.py --list
"""

import json, sys, argparse, shutil, subprocess
from pathlib import Path
from datetime import date

IGSL     = Path.home() / ".igsl-skills"
PROPOSED = IGSL / "_proposed"
APPLIED  = PROPOSED / "applied"
TODAY    = date.today().isoformat()


def load_proposals(path: Path) -> list:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"ERROR: Could not read proposals: {e}")
        return []


def apply_skill_patch(proposal: dict) -> bool:
    target = proposal.get("target", "")
    detail = proposal.get("detail", "")

    try:
        import yaml
        reg_file = IGSL / "_registry_v2.yaml"
        if reg_file.exists():
            with open(reg_file, encoding="utf-8") as f:
                reg = yaml.safe_load(f) or {}
            node = reg.get("nodes", {}).get(target, {})
            path_str = node.get("path", "").replace("~", str(Path.home()))
            skill_path = Path(path_str)
        else:
            print(f"  Registry not found")
            return False
    except ImportError:
        print("  yaml not available; edit skill file manually")
        print(f"  Detail: {detail}")
        return True

    if not skill_path.exists():
        print(f"  Skill file not found: {skill_path}")
        return False

    patch = f"\n\n<!-- auto-improve patch {TODAY} [{proposal.get('proposal_id', '')}] -->\n{detail}\n"
    with open(skill_path, "a", encoding="utf-8") as f:
        f.write(patch)
    print(f"  Appended to: {skill_path}")
    return True


def apply_registry_edge(proposal: dict) -> bool:
    print(f"  Manual registry update required:")
    print(f"  {proposal.get('detail', '')}")
    print(f"  Edit: ~/.igsl-skills/_registry_v2.yaml")
    return True


def apply_user_memory(proposal: dict) -> bool:
    print(f"\n  *** UPDATE userMemories in Claude.ai chat ***")
    print(f"  Add this line:")
    print(f"  \"{proposal.get('detail', '')}\"")
    return True


def apply_new_node(proposal: dict) -> bool:
    stub_path = PROPOSED / f"{proposal.get('proposal_id', 'new')}_node_spec.yaml"
    stub_path.write_text(proposal.get("detail", ""), encoding="utf-8")
    print(f"  Node spec saved: {stub_path}")
    print(f"  Next: python3 ~/.igsl-skills/skill.py add --id <ID> --name <n> ...")
    return True


def git_commit(summary: str):
    try:
        subprocess.run(["git", "-C", str(IGSL), "add", "-A"],
                       capture_output=True, timeout=10)
        subprocess.run(["git", "-C", str(IGSL), "commit", "-m",
                        f"improve: {summary} [auto-improve]"],
                       capture_output=True, timeout=10)
    except Exception:
        pass


def review_proposals(proposal_file: Path):
    proposals = load_proposals(proposal_file)
    if not proposals:
        print("No proposals to review.")
        return

    SEP = "═" * 56
    print(f"\n{SEP}")
    print(f"  IGSL PROPOSAL REVIEW")
    print(f"  File: {proposal_file.name}")
    print(f"  {len(proposals)} proposals to review")
    print(SEP)

    approved = []
    skipped_all = False

    for i, p in enumerate(proposals, 1):
        if skipped_all:
            break

        print(f"\n[{i}/{len(proposals)}] {p.get('type', '?').upper()} → {p.get('target', '?')}")
        print(f"Summary:  {p.get('summary', '')}")
        print(f"Severity: {p.get('severity', '?')}")
        print(f"Sessions before promotion: {p.get('sessions_before_promotion', 1)}")
        print(f"\nDetail:")
        print(f"  {p.get('detail', '')[:300]}")
        print()

        try:
            choice = input("Apply? [y]es / [n]o / [e]dit / [s]kip all: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nReview interrupted.")
            break

        if choice == "s":
            skipped_all = True
            break
        elif choice == "y":
            ptype = p.get("type", "")
            ok = False

            if ptype == "skill_patch":
                ok = apply_skill_patch(p)
            elif ptype in ("new_edge", "registry_update"):
                ok = apply_registry_edge(p)
            elif ptype == "user_memory":
                ok = apply_user_memory(p)
            elif ptype == "new_node":
                ok = apply_new_node(p)
            else:
                print(f"  Unknown proposal type: {ptype}")
                ok = True

            if ok:
                approved.append(p)
                print(f"  ✓ Applied")
            else:
                print(f"  ✗ Failed — skipping")

        elif choice == "e":
            print("Enter new detail (press Enter twice to finish):")
            lines = []
            try:
                while True:
                    line = input()
                    if line == "" and lines and lines[-1] == "":
                        break
                    lines.append(line)
                p["detail"] = "\n".join(lines[:-1] if lines else lines)
                approved.append(p)
                print(f"  ✓ Edited and queued")
            except (EOFError, KeyboardInterrupt):
                print("\nEdit cancelled.")
        else:
            print(f"  → Skipped")

    if approved:
        summary = f"{len(approved)} proposals from {proposal_file.stem[:20]}"
        git_commit(summary)
        print(f"\n✓ {len(approved)} improvement(s) applied and committed")

        mem_proposals = [p for p in approved if p.get("type") == "user_memory"]
        if mem_proposals:
            print(f"\n*** Remember to update userMemories in Claude.ai ***")

    APPLIED.mkdir(exist_ok=True)
    archive_path = APPLIED / proposal_file.name
    shutil.move(str(proposal_file), str(archive_path))
    print(f"\nProposal file archived: {archive_path}")
    print(f"\n{SEP}\n")


def main():
    p = argparse.ArgumentParser(description="IGSL Proposal Review")
    p.add_argument("file", nargs="?", help="Proposal JSON file path")
    p.add_argument("--latest", action="store_true")
    p.add_argument("--list", action="store_true")
    args = p.parse_args()

    PROPOSED.mkdir(exist_ok=True)

    if args.list:
        files = sorted(PROPOSED.glob("*_proposals.json"))
        if not files:
            print("No pending proposals.")
            return
        print(f"Pending proposals ({len(files)} files):")
        for f in files:
            props = load_proposals(f)
            print(f"  {f.name}  ({len(props)} proposals)")
        return

    if args.file:
        pfile = Path(args.file)
    else:
        files = sorted(PROPOSED.glob("*_proposals.json"),
                       key=lambda x: x.stat().st_mtime, reverse=True)
        if not files:
            print("No pending proposals found.")
            return
        pfile = files[0]
        print(f"Using most recent: {pfile.name}")

    if not pfile.exists():
        print(f"ERROR: File not found: {pfile}")
        sys.exit(1)

    review_proposals(pfile)


if __name__ == "__main__":
    main()
