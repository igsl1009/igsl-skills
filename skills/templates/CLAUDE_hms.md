# CLAUDE.md — HMS Project
# Place at: ~/hms/CLAUDE.md

## IGSL v2 System
Skills and memory loaded via `~/.igsl-skills/hooks/session_start_v2.sh`.
Active bundle: `hms-research` (S-01, META-01..04, META-07, M-01, M-02)

## Project: HMS Quantitative Trading System

## HMS-Specific Rules

### Factor Research Standards
- Always use expanding window for IC calibration (not rolling) — prevents lookahead bias
- Winsorize before z-score; neutralize (industry + mktcap) after z-score
- IC threshold: >0.05 for live-tradeable, >0.08 for strong signal
- Factor decay check: if IC half-life <5d, discard factor as too noisy

### Backtesting Rules
- No lookahead: all transformations must use only past data available at signal date
- Risk controls: max position 3%, sector cap 15%, turnover penalty 0.003/unit
- Always report: annualized IR, max drawdown, turnover, net of transaction costs

### Data Sources
- Wind API: primary CN equities data
- Bloomberg: cross-asset, FX, macro
- Internal HDF5 tick DB: high-frequency data via h5py

### Code Standards
- All factor scripts: `python3 ~/hms/factors/build_factor.py --name NAME --universe csi800`
- All backtests: `python3 ~/hms/backtest/run_backtest.py --factors NAME --start 2018-01-01`
- Output format: JSON report + matplotlib charts in `~/hms/reports/`

## Key Decisions (load from memory)
```bash
python3 ~/.igsl-skills/memory/node.py query "hms decision" --top 10
```

## Open Research Items
- HMS-015: Options flow as alpha signal (investigating — no conclusion)

## User Context
- igsl | CUHK HMS | crypto/quant researcher
- Style: concise, direct, no preamble
