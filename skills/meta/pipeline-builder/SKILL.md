# META-05 — Pipeline Builder
**id**: META-05 | **hardness**: hard | **type**: meta

## Purpose
Build, debug, and optimize multi-step data and automation pipelines. Applies to HMS factor pipelines, OpenClaude message routing, research automation, and launchd scheduling.

## Trigger Keywords
`pipeline`, `workflow`, `automate`, `scheduler`, `launchd`, `cron`, `etl`, `data flow`, `orchestrate`, `chain`

## Activation
Always loaded (hard skill). Health is recorded by `health_recorder.py` every 10 tool calls.

## Pipeline Patterns

### Factor Research Pipeline (HMS)
```
raw data → winsorize(1%,99%) → cross-section z-score → neutralize(industry,mktcap) → IC calc → blend
```
- Always use expanding window for calibration (not rolling) to avoid lookahead
- Winsorize before z-score; neutralize after z-score
- IC calculation: Spearman rank correlation, forward 1-period return

### Data ETL Pattern
```python
# Standard steps:
# 1. Extract with retry (exponential backoff, max 4 attempts)
# 2. Validate schema before transform
# 3. Transform in memory; write atomically (tmp → rename)
# 4. Log success/failure to structured log
```

### macOS Automation with launchd
```xml
<!-- ~/Library/LaunchAgents/com.igsl.JOBNAME.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "...">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.igsl.JOBNAME</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>/path/to/script.py</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>8</integer><key>Minute</key><integer>30</integer></dict>
  <key>StandardOutPath</key><string>/tmp/JOBNAME.log</string>
  <key>StandardErrorPath</key><string>/tmp/JOBNAME.err</string>
</dict>
</plist>
```
```bash
launchctl load ~/Library/LaunchAgents/com.igsl.JOBNAME.plist
launchctl list | grep igsl  # verify loaded
```

### Multi-Agent Pipeline (Claude Swarm v2)
```bash
# Launch coordinator + workers
python3 ~/claude-swarm/swarm.py start --config ~/claude-swarm/configs/hms_research.yaml
# Monitor via blackboard MCP
```

## Debug Protocol for Pipeline Failures
1. Check last exit code: `echo $?`
2. Tail stderr log: last 50 lines
3. Reproduce with minimal input (1 row / 1 file)
4. Binary search: bisect pipeline stages to find failing step
5. Fix one thing, re-run, verify

## Rules
- Always write atomic outputs (write to .tmp, then rename)
- Always log structured JSON to stderr or log file
- Never hardcode credentials — use env vars or keychain
- For pipelines >3 steps: draw the DAG before coding
