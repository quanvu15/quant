## Run 59 Analysis

### Saved artifacts
- Raw result: [run_59_result_raw.json](/home/work/quant-dinger/exports/backtest_run_59/run_59_result_raw.json)
- Config snapshot: [run_59_config_snapshot_raw.json](/home/work/quant-dinger/exports/backtest_run_59/run_59_config_snapshot_raw.json)
- Trades: [run_59_trades.csv](/home/work/quant-dinger/exports/backtest_run_59/run_59_trades.csv)
- Equity curve: [run_59_equity_curve.csv](/home/work/quant-dinger/exports/backtest_run_59/run_59_equity_curve.csv)
- Strategy logs: [run_59_strategy_logs.json](/home/work/quant-dinger/exports/backtest_run_59/run_59_strategy_logs.json)

### Verdict
- The strategy logic is still **not fully aligned** with the backtest execution output.
- The main mismatch is in the **base entry amount** used by the backtest engine versus the **base layer amount** tracked inside the script.
- Because of that mismatch, later `Exit DCA` partial reductions are applied to a larger live/backtest position than the script thinks it has, so the `Amount` column in the trade table becomes too large.

### Key evidence
- Script log at `2026-02-15 14:15:00` says:
  - `Open LONG: amount=0.01809273612829921 @ 69088.5`
  - This matches the intended formula `qty = equity * entry_pct * leverage / price` with `1000 * 0.25 * 5 / 69088.5`.
- But the first persisted trade row says:
  - `open_long amount = 0.0724`
- First DCA row says:
  - `add_long amount = 0.0181`
- First partial exit row says:
  - `reduce_long amount = 0.0452`
  - while `payload_json.targetLayerExpectedAmount = 0.0181`

### What this means
- The script stack believes:
  - base entry is about `0.0181`
  - DCA1 adds about `0.0181`
  - total stack before first exit is about `0.0362`
  - so `Exit DCA` ratio is about `0.0181 / 0.0362 = 0.5`
- The backtest engine actually opened:
  - base entry `0.0724`
  - then DCA1 `0.0181`
  - actual engine position before first exit is about `0.0905`
  - applying script ratio `0.5` to `0.0905` gives about `0.0452`
- That exactly matches the wrong-looking trade table output.

### Root cause in code
- Script-side open amount is produced from the script order in [strategy_dca_grid_script.py](/home/work/quant-dinger/QuantDinger/strategy_dca_grid_script.py:446) and [strategy_dca_grid_script.py](/home/work/quant-dinger/QuantDinger/strategy_dca_grid_script.py:653).
- Script strategy logs confirm that computed amount is `0.01809...`.
- But the backtest engine's `open_long` branch still ignores the script's explicit opening amount and re-sizes the first position from `entryPct` in [backtest.py](/home/work/quant-dinger/backend_api_python/app/services/backtest.py:3782).
- In contrast, DCA adds do respect the script-provided absolute amount through `add_long_amount_arr` in [backtest.py](/home/work/quant-dinger/backend_api_python/app/services/backtest.py:3643).
- Partial exits then use `reduce_ratio` against the engine's actual position in [backtest.py](/home/work/quant-dinger/backend_api_python/app/services/backtest.py:3552), which magnifies the mismatch if the initial base position was oversized.

### Conclusion
- The visible `Amount` problem in run `#59` is real.
- The issue is not primarily the latest script formula.
- The issue is the **backtest engine opening the first script entry with a different sizing path than the script stack uses internally**.
- So the current run cannot be considered a faithful validation of the DCA strategy yet.

### Recommended next step
- Update the backtest script-execution path so `open_long` and `open_short` can also honor the script-provided absolute amount, the same way `add_long` and `add_short` already do.
- After that, rerun the backtest and verify:
  - first `open_long amount` is about `0.0181`
  - first `add_long amount` is about `0.0181`
  - first `reduce_long amount` is about `0.0181`, not `0.0452`
