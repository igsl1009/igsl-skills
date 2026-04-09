# S-01 — Quant Research (HMS)
**id**: S-01 | **hardness**: project-hook | **type**: skill
**project-hook**: hms | **bundle**: hms-research

## Purpose
End-to-end quantitative alpha factor research for the HMS trading system. Covers factor construction, IC analysis, risk model, portfolio construction, and execution.

## Trigger Keywords
`factor`, `alpha`, `ic`, `backtest`, `signal`, `portfolio`, `rebalance`, `momentum`, `value`, `quality`, `risk model`, `hms`, `quant`

## HMS System Reference

### Universe
- CSI 500 + CSI 300 constituents
- Exclude: ST stocks, <60d trading history, float <500M CNY
- Data: Wind (primary), Bloomberg (cross-asset), HDF5 tick DB

### Factor Pipeline
```python
# Standard processing chain:
# 1. Winsorize: clip at 1st/99th percentile
# 2. Z-score: cross-sectional standardization
# 3. Neutralize: regress out industry + log(mktcap)
# 4. Combine: IC-weighted blend (expanding window ICs)
```

### IC Calculation
```python
# Spearman rank IC, forward 1-period return
# Window: rolling 252 trading days
# Quality thresholds:
#   IC > 0.05 → live-tradeable
#   IC > 0.08 → strong
#   IC decay half-life < 5d → too noisy, discard
```

### Factor Library
| Factor | Method | IC Range |
|--------|--------|---------|
| Momentum | 12-1 month returns (skip last) | 0.04-0.07 |
| Value | P/B, P/E composite | 0.03-0.06 |
| Quality | ROE, accruals, leverage | 0.03-0.05 |
| Sentiment | NLP (SnowNLP + BERT-zh) | 0.02-0.04 |
| Size | log(mktcap) | varies |

### Risk Model
- Barra-style: 10 style factors + industry dummies + specific risk
- Estimation universe: all A-shares
- Re-estimate: monthly

### Portfolio Construction
```
Max position: 3% | Sector cap: 15%
Turnover penalty: 0.003 per unit of turnover
Rebalance: weekly (Friday close)
Min turnover to trade: 1%
```

### Execution
- TWAP over 30min for positions >0.5% ADV
- Slippage estimate: 5bps per side for liquid stocks

## Research Workflow

### New Factor Research
```bash
# 1. Build factor values
python3 ~/hms/factors/build_factor.py --name FACTOR_NAME --universe csi800

# 2. Calculate IC
python3 ~/hms/analysis/ic_analysis.py --factor FACTOR_NAME --periods 1,5,10,20

# 3. Backtest portfolio
python3 ~/hms/backtest/run_backtest.py --factors FACTOR_NAME --start 2018-01-01

# 4. Generate report
python3 ~/hms/reports/factor_report.py --factor FACTOR_NAME
```

### Daily Routine (auto via launchd)
```
08:30 HKT: ~/hms/scheduler/daily_run.py
  → fetch yesterday's data (Wind API)
  → update factor values
  → recalculate signals
  → generate signal report
  → check rebalance threshold
```

## Open Items
- HMS-015: Options flow as alpha signal (investigating)

## Key Files
```
~/hms/
  factors/          # factor construction scripts
  analysis/         # IC analysis, decay curves
  backtest/         # portfolio backtesting engine
  reports/          # daily/weekly report generation
  scheduler/        # launchd automation scripts
  data/             # HDF5 tick database
```
