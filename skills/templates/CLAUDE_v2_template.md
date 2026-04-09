# CLAUDE.md — IGSL v2 Template
# Copy this to the project directory and customize PROJECT_NAME and project-specific rules.

## IGSL v2 System
Skills and memory loaded via `~/.igsl-skills/hooks/session_start_v2.sh`.
- Skill registry: `~/.igsl-skills/_registry_v2.yaml`
- Memory nodes: `~/.igsl-skills/memory/nodes.jsonl`
- Proposals: `~/.igsl-skills/_proposed/`

## User Context
- User: igsl | bypassPermissions mode
- Style: concise, direct, no preamble, no trailing summaries
- Platform: macOS Darwin 25.3.0

## Project: {{PROJECT_NAME}}

## Project-Specific Rules
<!-- Add project rules here -->

## Global Rules (always apply)

### Verify-Before-Done
Never report a task complete without confirming system state (check logs, re-run command, tail output). "Command ran without error" is not proof of success.

### Disambiguate-Named-Targets
When a request mentions a name with multiple possible matches, ask ONE clarifying question before acting: "Do you mean X or Y?"

### No-Auto-Self-Improve
Never invoke /self-improve, /evolve, /reflect automatically. Only on explicit user request.

### Read-Before-Write
Always Read a file before Writing. Prefer Edit for modifications to existing files.

### WhatsApp Log-Only
For OpenClaude/WhatsApp: log-only mode. Never reply or act on messages without explicit owner authorization.

## Memory Operations
```bash
# Query memory
python3 ~/.igsl-skills/memory/node.py query "search terms"

# Add a decision
python3 ~/.igsl-skills/memory/node.py add --id {{PREFIX}}-NNN --type DEC --tags "tag1 tag2" --content "decision text"

# Check health
python3 ~/.igsl-skills/skill.py health alert
```
