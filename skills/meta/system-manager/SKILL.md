# META-09 — System Manager
**id**: META-09 | **hardness**: hard | **type**: meta

## Purpose
Always-on system health monitoring and management. Provides `igsl_manage.py`
commands for status, integrity checks, SERR cleanup, and link validation.
Runs at session start (check) and session end (cleanup when quality < 50).

## Trigger Keywords
`igsl status`, `manage`, `system check`, `health report`, `integrity`, `fix-serr`

## Activation
Always loaded (hard skill). Commands available every session via `igsl_manage.py`.

## Commands

```bash
python3 ~/.igsl-skills/igsl_manage.py status   # full health report
python3 ~/.igsl-skills/igsl_manage.py check    # pass/fail integrity check
python3 ~/.igsl-skills/igsl_manage.py links    # verify all registry paths exist
python3 ~/.igsl-skills/igsl_manage.py fix-serr # remove duplicate SERR nodes
python3 ~/.igsl-skills/igsl_manage.py gc       # garbage-collect low-weight nodes
```

Slash command: `/igsl status`

## Behaviour

### `status`
- Registry version + node count
- Skill health: avg score, alert count
- Memory: total nodes, by type, open loops
- QA: last run result
- Active index: top-8 active node IDs

### `check`
- Registry YAML parseable: PASS/FAIL
- All hard skill paths exist: PASS/FAIL
- Memory nodes.jsonl valid JSON lines: PASS/FAIL
- Session journal dir writable: PASS/FAIL
- Exits 0 on all PASS, exits 1 if any FAIL

### `links`
- For every node in registry, verify `path` resolves to an existing file
- Reports missing paths

### `fix-serr`
- Scans nodes.jsonl for duplicate ERR nodes with same SID tag
- Keeps the most-recent duplicate, removes the rest
- Reports count removed

### `gc`
- Delegates to `memory/node.py gc` (dry-run safe)

## Hard Rules
1. NEVER auto-run destructive commands without `--confirm`
2. `check` must always be silent on success (only print failures)
3. Status output is for human reading — keep it under 40 lines
