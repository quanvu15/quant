## Run 60 Analysis

### Saved artifacts
- Raw result: [run_60_result_raw.json](/home/work/quant-dinger/exports/backtest_run_60/run_60_result_raw.json)
- Config snapshot: [run_60_config_snapshot_raw.json](/home/work/quant-dinger/exports/backtest_run_60/run_60_config_snapshot_raw.json)
- Trades: [run_60_trades.csv](/home/work/quant-dinger/exports/backtest_run_60/run_60_trades.csv)
- Equity curve: [run_60_equity_curve.csv](/home/work/quant-dinger/exports/backtest_run_60/run_60_equity_curve.csv)
- Strategy logs: [run_60_strategy_logs.json](/home/work/quant-dinger/exports/backtest_run_60/run_60_strategy_logs.json)

### Verdict
- Backtest run `#60` is now aligned with the intended DCA strategy logic much better than run `#59`.
- The previous `Amount` mismatch on the first entry and later `Exit DCA` trades appears fixed.

### What was checked
- Compared the first entry in `strategyLogs` with the first persisted trade row.
- Compared every `add_long` trade amount with `payload_json.targetLayerExpectedAmount`.
- Compared every `reduce_long` trade amount with `payload_json.targetLayerExpectedAmount`.
- Checked that entry notional stays close to the expected base allocation of about `1250 USDT` per initial layer (`1000 * 0.25 * 5`), allowing for display rounding to 4 decimals.

### Key findings
- First entry now matches the script logic:
  - `strategyLogs`: `Open LONG: amount=0.018092736... @ 69088.5`
  - first trade row: `open_long amount = 0.0181`
- First DCA / exit sequence is consistent:
  - `add_long amount = 0.0181`
  - `reduce_long amount = 0.0181`
  - `targetLayerExpectedAmount = 0.0181`
- Full-run consistency checks:
  - `31` `add_long` trades matched `targetLayerExpectedAmount`
  - `31` `reduce_long` trades matched `targetLayerExpectedAmount`
  - maximum detected difference was `0.0` in the exported trade data

### Example: DCA3 -> DCA2 -> DCA1 unwind
- `trade_index 13`: `reduce_long amount = 0.0199`, expected `0.0199` for layer entry `63961.55`
- `trade_index 14`: `reduce_long amount = 0.0190`, expected `0.0190` for layer entry `65481.74`
- `trade_index 15`: `reduce_long amount = 0.0181`, expected `0.0181` for layer entry `67633.61`
- This matches the intended LIFO exit behavior.

### Important note
- The saved config snapshot still shows `positionConfig.entryPct = 1.0`.
- Despite that, run `#60` no longer exhibits the old oversized first-entry behavior from run `#59`, which indicates the script-provided opening qty is now being respected in the backtest execution path.

### Conclusion
- Based on the exported artifacts, run `#60` looks correct with respect to:
  - initial entry sizing
  - DCA layer sizing
  - partial `Exit DCA` sizing
  - LIFO layer unwind behavior
- The DCA backtest path now appears consistent with the current intended strategy logic.
