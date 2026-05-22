# Backtest Run 61 Analysis

- Raw result: [run_61_result_raw.json](/home/work/quant-dinger/exports/backtest_run_61/run_61_result_raw.json)
- Pretty result: [run_61_result_pretty.json](/home/work/quant-dinger/exports/backtest_run_61/run_61_result_pretty.json)
- Config snapshot: [run_61_config_snapshot_raw.json](/home/work/quant-dinger/exports/backtest_run_61/run_61_config_snapshot_raw.json)
- Trades: [run_61_trades.csv](/home/work/quant-dinger/exports/backtest_run_61/run_61_trades.csv)
- Equity curve: [run_61_equity_curve.csv](/home/work/quant-dinger/exports/backtest_run_61/run_61_equity_curve.csv)
- Strategy logs: [run_61_strategy_logs.json](/home/work/quant-dinger/exports/backtest_run_61/run_61_strategy_logs.json)

## Snapshot

- Run id: `61`
- Strategy: `dca_grid` (`strategy_script`)
- Symbol / timeframe: `BTC/USDT` / `1H`
- Range: `2023-05-16` to `2026-05-15`
- Initial capital: `1000`
- Leverage: `5`
- Result:
  - `totalReturn = 126.49%`
  - `annualReturn = 42.17%`
  - `maxDrawdown = -66.1%`
  - `winRate = 85.24%`
  - `profitFactor = 1.32`
  - `totalProfit = 1264.86`

## Order Flow Summary

- Exported trade ledger contains:
  - `83` `open_long`
  - `166` `add_long`
  - `127` `reduce_long`
  - `83` `close_long`
- Full close classification from `strategyLogs`:
  - `66` trailing-stop closes
  - `16` hard-stop closes
  - `1` forced close at backtest end
- There were `0` fixed `Take profit global (LONG)` closes in this run.
- There were `127` `Exit DCA partial (LONG)` events in the logs, matching the `127` `reduce_long` rows.

## Validation

### 1. Entry orders

- The exported `open_long.amount` values are internally consistent with the current script-runtime behavior.
- Example:
  - Trade `#1`: `price=26649.67`, `amount=0.0469`
  - This matches `1000 * 0.25 * 5 / 26649.67 ≈ 0.046905`
- Important caveat:
  - New entries are **not compounding with the real post-trade balance** in this backtest path.
  - Evidence:
    - Trade `#458`: `balance` before entry was `2230.69`
    - If entry used current equity, expected size would be about `0.0351`
    - Actual size is `0.0157`, which matches using the original `1000` balance instead
- Root cause is in the script backtest context: `ctx.equity` / `ctx.balance` are seeded once and not updated with realized PnL during `_execute_script_strategy`.
- Conclusion:
  - Entry sizing is consistent with the current engine implementation.
  - Entry sizing is **not correct** if the intended behavior is to use current equity for compounding, because the script code in `_entry_order_amount(...)` clearly intends that.

### 2. DCA add orders

- `add_long` rows are structurally correct for the current engine:
  - `166 / 166` rows preserve the script-produced absolute amount in the trade ledger.
- The actual fill price can differ from the DCA trigger price because this run uses `signalTiming = next_bar_open`.
- Example:
  - Trade `#6`: actual fill `25809.05`
  - Payload target layer trigger price `26007.53`
  - This is acceptable because the trigger happens on one bar and execution occurs at the next bar open.
- The `displayLabel` / `layerNumber` in payload reflect the current active DCA layer.
- The `reason` field such as `dca_166` is a global action counter across the run, not the visual layer number.

### 3. Exit DCA orders

- `reduce_long` amount handling is correct:
  - `127 / 127` rows match `payload_json.targetLayerExpectedAmount`
- Exit trigger handling is also correct for the current logic:
  - `127 / 127` `reduce_long` rows executed at `price >= targetLayerExitPrice`
- As with DCA adds, fill price can be better than the trigger because execution is at next bar open.

### 4. Profit calculation on `reduce_long`

- This is the most important semantic caveat in the export.
- Current backtest engine formula for `reduce_long.profit` is:

```text
profit = (exec_price - position_entry_price) * reduced_amount
```

- Here, `position_entry_price` is the **blended average cost of the whole remaining position**, not the entry price of the specific DCA layer being exited.
- Therefore:
  - `reduce_long.profit` is **not layer PnL**
  - it is the realized PnL of the reduced quantity against the whole-position average cost
- Consequence in run `61`:
  - `13` `Exit DCA` rows show a negative `profit`
  - but those same rows are still valid DCA recoveries because the exited layer itself was profitable
- Example:
  - Trade `#40`
  - Exported `profit = -3.67`
  - Layer-specific PnL from payload prices is about `+14.29`
  - Why different:
    - blended `positionEntryPrice = 25853.10`
    - target DCA layer entry price `= 25478.86`
    - exit price `= 25776.62`
- Conclusion:
  - If your question is “trade table profit of `Exit DCA` has been calculated as whole-position realized PnL, is that consistent with current engine?”: yes.
  - If your question is “does `Exit DCA` profit represent the profit of the recovered DCA layer itself?”: no, it does not.

### 5. Profit calculation on full close / trailing / hard stop

- Full close rows are correct for the current engine semantics.
- They close the remaining position against the current blended `positionEntryPrice`.
- Since those trades are full exits of the remaining stack, this is the expected cost basis to use.
- In this run:
  - `66` closes came from trailing-stop logic in the script
  - `16` closes came from hard-stop logic in the script
  - final trade `#459` is a forced close at backtest end, not a strategy-triggered TP/stop event

### 6. ROI calculation

- ROI is not stored in the trade CSV; it is emitted in `strategyLogs`.
- The script uses this long-side formula:

```text
roi = (price * remaining_amount + total_exit_value - total_entry_value)
      / total_entry_value * 100
```

- This is the correct whole-position ROI formula for a DCA stack with partial exits, because it includes:
  - current mark-to-market value of the remaining layers
  - realized value from prior `Exit DCA` reductions
  - total capital deployed into the stack
- Validation result:
  - Recomputed against all `11,705` `LONG monitor` log lines
  - Maximum absolute difference from logged ROI was about `0.0046%`
  - That residual is only from log rounding
- Conclusion:
  - The ROI formula in the script for run `61` is correct.

## Final Verdict

- `Entry`: correct relative to the current engine, but **not correct for compounding equity sizing**
- `DCA add`: correct
- `Exit DCA amount / trigger`: correct
- `TP / full close logic in this run`: there was no fixed TP; closes were mostly trailing-stop and hard-stop
- `profit` on `close_long`: correct
- `profit` on `reduce_long`: correct for blended-position accounting, **not** correct if you want per-layer DCA profit
- `ROI`: correct

## Recommended Follow-Ups

1. Update script backtest context in `backend_api_python/app/services/backtest.py` so `ctx.balance` / `ctx.equity` reflect the evolving simulated account, otherwise new entries cannot compound.
2. Decide whether `reduce_long.profit` should stay as blended-position realized PnL or whether the UI/export also needs an extra field for `layerProfit`.
3. If you want clearer auditability, classify generic `close_long` rows into `trailing_stop`, `hard_stop`, `tp`, or `final_close` directly in the exported trade payload instead of inferring them from logs.
