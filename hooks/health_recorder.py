#!/usr/bin/env python3
"""
IGSL PostToolUse Hook — health_recorder.py
Fires after every tool call. Records tool log, ART nodes for file writes,
failure events to journal. Always exits 0 (PostToolUse cannot block).
"""

import json, sys, os, subprocess
from pathlib import Path
from datetime import date, datetime

IGSL     = Path.home() / ".igsl-skills"
MEM_DIR  = IGSL / "memory"
LOG_DIR  = MEM_DIR / "tool-log"
TODAY    = date.today().isoformat()
SESSION_FILE = Path("/tmp/igsl_session_id")

ART_EXTENSIONS = {".pdf", ".tex", ".py", ".md", ".html", ".ipynb",
                  ".xlsx", ".pptx", ".docx", ".png", ".svg", ".json"}

ERROR_INDICATORS = ["error", "exception", "failed", "filenotfounderror",
                    "traceback", "syntaxerror", "typeerror"]


def get_session_id() -> str:
    try:
        return SESSION_FILE.read_text().strip()
    except Exception:
        return "unknown"


def detect_success(tool_response: str) -> bool:
    resp_lower = str(tool_response).lower()
    return not any(indicator in resp_lower for indicator in ERROR_INDICATORS)


def write_tool_log(entry: dict):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"{TODAY}.jsonl"
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
    except Exception:
        pass


def write_art_node(file_path: str, session_id: str):
    ext = Path(file_path).suffix.lower()
    if ext not in ART_EXTENSIONS:
        return

    ts_suffix = datetime.now().strftime("%H%M%S")
    art_id = f"ART-{ts_suffix}"
    content = f"ART[{TODAY}] {file_path}"
    if len(content) > 120:
        content = f"ART[{TODAY}] ...{file_path[-85:]}"

    try:
        subprocess.run(
            [sys.executable, str(MEM_DIR / "node.py"), "add",
             "--id", art_id,
             "--type", "ART",
             "--tags", f"artifact {ext[1:]}",
             "--content", content[:120],
             "--src", session_id[:6]],
            capture_output=True, timeout=10
        )
    except Exception:
        pass


def write_failure_journal(tool_name: str, tool_input: dict,
                           session_id: str, journal_dir: Path):
    journal_files = list(journal_dir.glob(f"*{session_id[:16]}*.jsonl"))
    if not journal_files:
        return

    event = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "type": "tool_failure",
        "tool": tool_name,
        "input": str(tool_input)[:80],
        "affected_skill": None,
        "severity": "minor"
    }
    try:
        with open(journal_files[0], "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
    except Exception:
        pass


def update_skill_health(session_id: str, success: bool):
    hard_skills = ["META-05", "META-07"]
    for sid in hard_skills:
        try:
            subprocess.run(
                [sys.executable, str(IGSL / "skill.py"), "health", "record", sid,
                 "--applied", "1",
                 "--completed", "1" if success else "0",
                 "--fallback", "0"],
                capture_output=True, timeout=5
            )
        except Exception:
            pass


def main():
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        payload = {}

    tool_name     = payload.get("tool_name", "unknown")
    tool_input    = payload.get("tool_input", {})
    tool_response = payload.get("tool_response", "")
    session_id    = get_session_id()

    success = detect_success(tool_response)

    log_entry = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "tool": tool_name,
        "input": str(tool_input)[:100],
        "status": "ok" if success else "fail",
        "session": session_id[:20]
    }
    write_tool_log(log_entry)

    write_tools = {"Write", "Create", "create_file", "str_replace_based_edit_tool",
                   "Edit", "MultiEdit", "NotebookEditCell"}
    if tool_name in write_tools and success:
        file_path = (
            tool_input.get("file_path") or
            tool_input.get("path") or
            tool_input.get("new_path") or
            ""
        )
        if file_path:
            write_art_node(file_path, session_id)

    if not success and tool_name not in {"Read", "Glob", "Grep", "LS", "ls"}:
        journal_dir = IGSL / "_journal"
        if journal_dir.exists():
            write_failure_journal(tool_name, tool_input, session_id, journal_dir)

    try:
        log_file = LOG_DIR / f"{TODAY}.jsonl"
        if log_file.exists():
            with open(log_file, encoding="utf-8") as f:
                line_count = sum(1 for _ in f)
            if line_count % 10 == 0:
                update_skill_health(session_id, success)
    except Exception:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
