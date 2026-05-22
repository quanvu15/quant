# Work Logs

## 2026-05-18

### Backend
- Persisted script `ctx.log()` lines into `qd_strategy_logs` during live closed-bar evaluation so Strategy Logs can show strategy-side reasoning, not just executor-level `Signal submitted`.
  - `backend_api_python/app/services/trading_executor.py`: flush new `ctx._logs` after each `on_bar` call via `append_strategy_log(..., "[script] ...")`.
- Backfilled existing DCA Grid strategy records in PostgreSQL so old saved strategies now carry the updated entry-reason logging code without recreating them.
  - Database rows updated in `qd_strategies_trading.strategy_code`: strategy IDs `4`, `6`, `7`, `8` now use the current [QuantDinger/strategy_dca_grid_script.py](/home/work/quant-dinger/QuantDinger/strategy_dca_grid_script.py) content including `entry_signal_triggered` logs.

### Frontend
- Forced indicator-analysis Pyodide loader to use bundled local assets only, removing `.env`/CDN selection for chart runtime.
  - `frontend/src/views/indicator-analysis/components/KlineChart.vue`: hardcoded Pyodide base to `/assets/pyodide/v0.25.0/full/` and removed external/CDN fallback logic so chart always loads `pyodide.js` from local `public/assets`.
- Added explicit DCA Grid entry-reason logs to template/source so entry bars can show RSI / MA-RSI values and threshold checks when a long/short signal fires.
  - `frontend/src/views/trading-assistant/components/scriptTemplateCatalog.js`: embedded DCA Grid code now logs `entry_signal_triggered` with `rsi_prev`, `rsi_now`, `ma_rsi_prev`, `ma_rsi_now`, thresholds, and each boolean condition before opening a position.
  - `QuantDinger/strategy_dca_grid_script.py`: mirrored the same logging change in the source-of-truth script.
- Fixed Strategy Code editor background bị dark (navy `#0f172a`) khi dùng Light theme trong modal Edit/Create Strategy.
  - `frontend/src/global.less`: Thêm CSS variables `--qd-code-bg`, `--qd-code-gutter-bg`, `--qd-code-border` cho cả Light theme (`#f8fafc`) và Dark theme (`#0f172a`).
  - `frontend/src/views/trading-assistant/components/StrategyEditor.vue`: Thay thế hardcoded fallback `var(--qd-code-bg, #0f172a)` bằng `var(--qd-code-bg)` trong global override; cập nhật scoped CSS dùng variables thay vì màu cứng.
- Fixed Backtest History drawer bị hẹp gây thanh cuộn ngang.
  - `frontend/src/views/indicator-analysis/components/BacktestHistoryDrawer.vue`: Tăng width từ `1060` lên `1400` (tổng width các cột ~1356px).
- Fixed cột "Price" trong bảng Trades hiển thị i18n key thô `backtest-center.result.colPrice`.
  - Thêm key `'backtest-center.result.colPrice'` vào tất cả 8 locale files: `en-US`, `vi-VN`, `zh-CN`, `ar-SA`, `de-DE`, `ja-JP`, `ko-KR`, `th-TH`, `fr-FR`.

### Notes / Pending
- Các locale khác (nếu có thêm) cũng cần bổ sung `colAction`, `colTime`, `colPrice`, `colAmount` tương tự.
- Chưa chạy lint/build cho thay đổi Pyodide loader trong môi trường hiện tại.
- Existing DCA Grid rows are now backfilled in DB; strategies already running still need a stop/start cycle to reload the updated `strategy_code` into the live executor process.
- No code changes made for strategy-log coverage review. Confirmed current behavior: detailed signal-reason logs now exist for DCA Grid; other script templates only log what their own `ctx.log(...)` statements emit, and indicator strategies do not yet have a generic per-signal reason-explanation layer.

## 2026-05-19

### Backend
- Committed and pushed the live script-log persistence change to remote `main`.
  - `backend_api_python/app/services/trading_executor.py`
  - Git commit: `566819b` (`Persist script logs to strategy logs`)

### Frontend
- Committed and pushed the local Pyodide + DCA Grid entry-log template updates to remote `main`.
  - `frontend/src/views/indicator-analysis/components/KlineChart.vue`
  - `frontend/src/views/trading-assistant/components/scriptTemplateCatalog.js`
  - Git commit: `ea06f8d` (`Use local pyodide and improve DCA entry logs`)

### Notes / Pending
- Left unrelated local modifications untouched:
  - `frontend`: `src/global.less`, locale files, `BacktestHistoryDrawer.vue`, `StrategyEditor.vue`
  - `backend_api_python`: `app/routes/backtest.py`, diagnostic scripts under `scripts/`

## 2026-05-13

### Backend
- Ran `git pull --rebase` on backend repo; push to `main` was rejected (protected branch).

### Frontend
- Ran `git pull --rebase` on frontend repo; push to `main` was rejected (protected branch).
- Allowed tunneled domain on dev server to fix Invalid Host header (frontend/vue.config.js).

### Notes / Pending
- Need permission to push to protected `main` or push to a feature branch and open an MR.

### Backend
- Updated start script to create uv virtualenv if missing, install deps via uv, and run with uv (backend_api_python/start.sh).
- Added strategy script compatibility for reduce_position (amount + ratio) in backtest and runtime contexts:
  - backend_api_python/app/services/backtest.py (ScriptBacktestContext.reduce_position)
  - backend_api_python/app/services/strategy_script_runtime.py (StrategyScriptContext.reduce_position)
- **Synced DCA Grid live trading fixes from QuantDinger dev branch to VPS backend (backend_api_python):**

  **Fix 1 â `strategy_script_runtime.py` (`StrategyScriptContext.reduce_position`):**
  - Old: only updated local `ctx.position`, did NOT emit to `ctx._orders`
  - New: emits `{'action': 'reduce', 'ratio': ratio, 'amount': amount}` to `_orders` so live trading executor can generate `reduce_long`/`reduce_short` signals
  - Also updates local position state immediately for same-bar consistency

  **Fix 2 â `trading_executor.py` (`_script_orders_to_execution_signals`):**
  - Added missing `action == 'reduce'` case
  - Converts `ratio` â `reduce_long`/`reduce_short` execution signal with `position_size=ratio`
  - Updates local `ctx.position` size for intra-bar consistency

  **Fix 3 â `trading_executor.py` (`_init_script_strategy_context`):**
  - Fixed merge order: was `{**persisted, **bot_params}` (bot_params overwrote layers on restart)
  - Now `{**bot_params, **persisted}` so DCA layer state (layers, dca_count, grid_anchor_price) survives restarts

  **Fix 4 â `backtest.py` (`_execute_script_strategy`):**
  - Added `reduce_long`, `reduce_short`, `reduce_size` Series initialization
  - Added `action == 'reduce'` handler in order processing loop
  - Added `continue` after `sell` block to prevent fall-through
  - `ScriptBacktestContext.reduce_position` now emits to `_orders` AND updates local position
  - Return dict now includes `reduce_long`, `reduce_short`, `reduce_size` signals

### Frontend
- Added strategy backtest date-range validation and improved error surfacing for /api/strategies/backtest (frontend/src/views/trading-assistant/index.vue).
- Added frontend start script with auto-install and run on port 8888 (frontend/start.sh).
- **Refactored Strategy Backtest UI from modal to IDE-style drawer:**
  - Created new component `StrategyBacktestPanel.vue` (frontend/src/views/trading-assistant/components/StrategyBacktestPanel.vue):
    - Split-panel layout: collapsible left config panel (280px) + scrollable right results panel
    - Date presets (1M/3M/6M/1Y/2Y) with auto-filter by timeframe limit
    - Params: symbol/timeframe, capital/leverage/commission/slippage, trade direction
    - Results: 6-metric grid with color-coded positive/negative, equity curve (echarts), trade table
    - Dark mode support, collapsible config rail (like Indicator IDE)
  - Replaced `a-modal` with `a-drawer` (88vw, right-side slide-in) in trading-assistant/index.vue
  - Added `onBacktestPanelRun` method to sync panel form back to parent before running
  - Registered `StrategyBacktestPanel` component in trading-assistant/index.vue
  - Added `.ta-backtest-drawer` global styles for drawer body/shadow
- **Added Bot Strategy (DCA Grid) creation flow:**
  - `scriptTemplateCatalog.js`: Added `BOT_TEMPLATE_CATALOG` with `dcaGrid` template (full embedded code + params), `getBotTemplateByKey`, `buildBotParamValues` exports
  - `StrategyTypeSelector.vue`: Added "DCA Grid Bot" card (3rd option) with orange theme, emits `@use-bot`
  - `BotParamsForm.vue`: New component â grouped param form (Entry/DCA/Exit sections) + live DCA level preview
  - `index.vue`:
    - Imported `BotParamsForm`, `BOT_TEMPLATE_CATALOG`, `getBotTemplateByKey`, `buildBotParamValues`
    - Added `botTemplateKey`, `botParamValues` to data
    - Added `handleUseBot(botKey)` method
    - Added bot mode to `strategyFormLastStepIndex` (3 steps: basic â bot params â execution)
    - Added bot step 1 (BotParamsForm) in form wizard
    - Added bot mode to `handleNext` validation
    - Added bot mode submit in `handleSubmit` â sets `strategy_mode='bot'`, `bot_type='dca'`, `bot_params={...}`
    - Added `.bot-params-step-header` styles
  - `en-US.js`, `zh-CN.js`, `vi-VN.js`: Added all bot mode + bot params i18n keys

### Notes / Pending
- Strategy backtest UI now matches Indicator IDE style (split panel, IDE drawer, date presets, metric grid).
- Chart rendering delegated to StrategyBacktestPanel via result watcher (no more parent-side echarts refs).
- **DCA Grid live trading prerequisites:**
  - Strategy must be created with `strategy_mode = 'bot'` in DB for tick-level evaluation (every price update)
  - `trading_config.bot_type` should be `'dca'` for `is_grid_bot=True` routing in buy/sell signal conversion
  - `trading_config.bot_params` should contain DCA Grid script params (rsi_period, dca_grid_pct, etc.)
  - Layers state persists via `script_runtime_state.params` in trading_config after each tick
- **Bot Strategy creation UI added** â all prerequisites above are now handled automatically by the new create flow.
- **Fixed: Script/Bot strategy not visible in Create Strategy modal:**
  - `router.config.js`: Removed `indicatorSignalOnly: true` from `/strategy-live` route â was blocking mode selector modal, forcing users into indicator-only form
  - `index.vue`: Fixed `strategiesForPage` computed â was filtering out `bot` strategies even on the main page; now shows all strategies (only `scriptStrategiesOnly` route filters to script/bot only)
- **Fixed: Build errors (ESLint):**
  - `BotParamsForm.vue`: Rewrote template with all attributes on separate lines (`vue/max-attributes-per-line`)
  - `StrategyTypeSelector.vue`: Fixed missing `</div>` closing `.mode-cards`, split multi-attr buttons to multi-line
  - `index.vue`: Removed unused `BOT_TEMPLATE_CATALOG` import, fixed `no-multi-spaces` and `object-property-newline`
- **Added: Edit support for Bot Strategy:**
  - `handleEditStrategy`: Restores `botParamValues` from `trading_config.bot_params` when editing a bot strategy
  - `loadStrategyDataToForm`: Added `strategy_mode === 'bot'` to `isScriptStrategy` check so form fields (symbol, capital, timeframe) are populated correctly on edit
  - Modal title now shows correct mode label for bot strategies

## 2026-05-13 (Context Research)

### Notes / Pending
- No code changes made. Research task: mapped DCA Grid bot strategy flow end-to-end.
- **DCA Grid strategy flow summary:**
  - Frontend: scriptTemplateCatalog.js defines BOT_TEMPLATE_CATALOG with dcaGrid key  contains embedded Python script code + 16 param definitions (entry/dca/exit groups)
  - Frontend: BotParamsForm.vue renders grouped param form (Entry Signal / DCA Grid / Exit Risk sections) + live DCA level preview; imports uildBotParamValues from scriptTemplateCatalog
  - API: POST /api/strategies/create ? StrategyService.create_strategy()  stores strategy_mode='bot', strategy_code=<embedded Python>, and 	rading_config (JSON blob containing ot_type='dca', ot_params={rsi_period, dca_grid_pct, ...}) into qd_strategies_trading.trading_config column
  - DB: All bot params live inside qd_strategies_trading.trading_config (TEXT/JSON column) as 	rading_config.bot_params. No separate bot_params table.
- Runtime: 	rading_executor._init_script_strategy_context() merges {**bot_params, **persisted} into ctx._params  bot_params provides param defaults, persisted (script_runtime_state) provides layer/DCA state that survives restarts
- Runtime state (layers, dca_count, grid_anchor_price, etc.) is written back to 	rading_config.script_runtime_state after each tick via _persist_script_runtime_state()
- strategy_mode='bot' triggers tick-level evaluation (is_bot_mode=True) in trading_executor main loop
- 	rading_config.bot_type='dca' sets is_grid_bot=True for buy/sell signal routing
- _build_bot_display() in StrategyService reads 	rading_config.bot_type + 	rading_config.bot_params to build display metadata for list view

## 2026-05-13 (Code Review)

### Backend
- No code changes made. Reviewed DCA Grid backtest/runtime paths and strategy snapshot resolution for issues related to missing DCA/add/reduce execution.

### Frontend
- No code changes made. Reviewed `trading-assistant`, bot creation/edit flows, and Indicator IDE Pyodide loading path to identify UI/layout and script-editing issues.

### Notes / Pending
- Findings identified in review:
  - Script-strategy backtest produces `reduce_long` / `reduce_short` signals, but standard backtest simulation does not consume them.
  - Bot strategy backtest snapshot does not pass `bot_params` into script runtime params, so custom DCA settings are ignored in backtest.
  - Bot editing flow only exposes parameter form, not embedded Python script editing.
  - Indicator IDE Pyodide loader defaults to local assets that are not bundled in this repo, and external fallback is disabled unless env flags are set.

## 2026-05-13 (Bot Strategy + Backtest Fixes)

### Backend
- Fixed script-strategy backtest to consume partial reduce signals (`reduce_long`, `reduce_short`, `reduce_size`) so DCA exit/reduce orders are executed in simulation (`backend_api_python/app/services/backtest.py`).
- Added script parameter seeding for strategy backtests so bot/runtime params from `trading_config.bot_params` are injected into `ctx.param(...)` defaults during script backtest (`backend_api_python/app/services/strategy_snapshot.py`, `backend_api_python/app/services/backtest.py`).
- Added backward-compatible bot type normalization for old `dcaGrid` records so runtime/display logic treats them as `dca` (`backend_api_python/app/services/trading_executor.py`, `backend_api_python/app/services/strategy.py`).

### Frontend
- Changed bot strategy flow to save runtime bot type from template metadata instead of the UI template key, fixing `bot_type` mismatch for DCA Grid (`frontend/src/views/trading-assistant/index.vue`, `frontend/src/views/trading-assistant/components/scriptTemplateCatalog.js`).
- Added bot template key/type resolution helpers so old/new bot records reopen correctly in edit flow (`frontend/src/views/trading-assistant/components/scriptTemplateCatalog.js`, `frontend/src/views/trading-assistant/index.vue`).
- Updated bot strategy step 2 to expose both parameter form and editable Python script editor, making DCA Grid editable like a script strategy (`frontend/src/views/trading-assistant/index.vue`).
- Enabled Pyodide CDN fallback by default so Indicator IDE can recover when local bundled assets are missing (`frontend/src/views/indicator-analysis/components/KlineChart.vue`).

### Notes / Pending
- Verified backend syntax with `python3 -m py_compile` on touched service files.
- Verified frontend lint on touched Vue/JS files with local `eslint`.
- `worklogs.md` encoding was normalized to UTF-8 first so future agent updates can patch it safely.

## 2026-05-13 (DCA Grid Backtest Review)

### Backend
- No code changes made. Reviewed strategy behavior from [strategy_DCA_Grid.md](/home/work/quant-dinger/strategy_DCA_Grid.md) and [strategy_dca_grid_script.py](/home/work/quant-dinger/strategy_dca_grid_script.py), then audited backtest run `qd_backtest_runs.id = 49` plus its `qd_backtest_trades` / `qd_backtest_equity_points` records in PostgreSQL.

### Frontend
- No code changes made.

### Notes / Pending
- Main review focus: verify whether run `#49` follows documented DCA Grid flow versus script-runtime flow, especially `add_long` / `reduce_long` / `close_long` sequencing.
- Key observation recorded for follow-up: run `#49` is a script-strategy backtest with `signalTiming = next_bar_open`, and its many `reduce_long` events are consistent with `use_exit_dca` partial exits rather than an unexpected close bug.

## 2026-05-15 (Backtest Run 61 Export And Audit)

## 2026-05-21

### Backend
- No code changes. Stashed local changes, pulled latest from origin/main, then reapplied stash without conflicts.

### Frontend
- No code changes. Stashed local changes, pulled latest from origin/main, then reapplied stash without conflicts.

### Notes / Pending
- Local uncommitted changes remain in both repos after stash pop.
- Quick diff review done: backend change in app/routes/backtest.py (LLMService usage) and frontend style/i18n tweaks; no conflicts detected.

### Backend
- No code changes made. Exported backtest `#61` artifacts to [exports/backtest_run_61/run_61_result_raw.json](/home/work/quant-dinger/exports/backtest_run_61/run_61_result_raw.json), [exports/backtest_run_61/run_61_result_pretty.json](/home/work/quant-dinger/exports/backtest_run_61/run_61_result_pretty.json), [exports/backtest_run_61/run_61_config_snapshot_raw.json](/home/work/quant-dinger/exports/backtest_run_61/run_61_config_snapshot_raw.json), [exports/backtest_run_61/run_61_trades.csv](/home/work/quant-dinger/exports/backtest_run_61/run_61_trades.csv), [exports/backtest_run_61/run_61_equity_curve.csv](/home/work/quant-dinger/exports/backtest_run_61/run_61_equity_curve.csv), and [exports/backtest_run_61/run_61_strategy_logs.json](/home/work/quant-dinger/exports/backtest_run_61/run_61_strategy_logs.json).
- Added audit report [exports/backtest_run_61/run_61_analysis.md](/home/work/quant-dinger/exports/backtest_run_61/run_61_analysis.md) covering entry sizing, DCA adds, Exit DCA reductions, full-close classification, `profit` semantics, and ROI verification.

### Frontend
- No code changes made.

### Notes / Pending
- Verified `Exit DCA` amount handling is correct in run `#61`: all `127` `reduce_long` rows match `payload_json.targetLayerExpectedAmount`, and all execute at or above `targetLayerExitPrice`.
- Verified long-side ROI logging is correct for partial-exit DCA accounting: recomputation across `11,705` `LONG monitor` lines matched the script formula with only log-rounding residue.
- Found one important engine-level mismatch: new `open_long` entries in the script backtest path still size off the original seeded `ctx.equity` instead of the evolving account balance, so run `#61` does not compound entries even though `_entry_order_amount(...)` is written as if it should.
- Confirmed `reduce_long.profit` is blended-position realized PnL, not per-layer DCA profit; this is why some successful DCA recoveries still show negative `profit` in the trade ledger.

## 2026-05-16 (DCA Params Clarified And Aligned)

### Backend
- Updated [QuantDinger/strategy_dca_grid_script.py](/home/work/quant-dinger/QuantDinger/strategy_dca_grid_script.py) to add explicit `use_stop_loss`, keep hard stop disabled by default, and keep `use_trailing` disabled by default so stop mechanisms are opt-in instead of silently active.
- Updated [backend_api_python/app/services/backtest.py](/home/work/quant-dinger/backend_api_python/app/services/backtest.py) so the script backtest context now refreshes `ctx.balance` / `ctx.equity` from realized and unrealized PnL during script execution, allowing later base entries to size from evolving capital instead of the original seed balance.

### Frontend
- Updated [frontend/src/views/trading-assistant/components/BotParamsForm.vue](/home/work/quant-dinger/frontend/src/views/trading-assistant/components/BotParamsForm.vue) so DCA Grid bot params now expose `use_stop_loss` as a separate switch, only show `stop_loss_pct` when enabled, and replace stale `dca_pct` editing with the real `dca_amount` parameter used by the script.
- Updated [frontend/src/views/trading-assistant/components/scriptTemplateCatalog.js](/home/work/quant-dinger/frontend/src/views/trading-assistant/components/scriptTemplateCatalog.js) so the DCA Grid bot template defaults and embedded script code align better with the real strategy: `use_trailing=false`, `use_stop_loss=false`, `dca_amount=100`, `dca_amount_multiplier=1.05`, and entry sizing uses equity ratio instead of treating `entry_pct` as raw quantity.
- Updated DCA bot param copy in [frontend/src/locales/lang/vi-VN.js](/home/work/quant-dinger/frontend/src/locales/lang/vi-VN.js), [frontend/src/locales/lang/en-US.js](/home/work/quant-dinger/frontend/src/locales/lang/en-US.js), and [frontend/src/locales/lang/zh-CN.js](/home/work/quant-dinger/frontend/src/locales/lang/zh-CN.js) to clarify the difference between `allow_short` and the strategy-level `Trade Direction`, and to describe `entry_pct` / `dca_amount` in capital-ratio terms.

### Notes / Pending
- Verified syntax with `python3 -m py_compile` for `backend_api_python/app/services/backtest.py` and `QuantDinger/strategy_dca_grid_script.py`.
- Did not run a fresh full backtest rerun in this step, so the next useful verification is to rerun a DCA backtest and confirm new entries now compound off updated equity and that trailing / hard stop stay inactive unless explicitly enabled.

## 2026-05-16 (Backtest 62 Audit And DCA Grid Script Template)

### Backend
- No backend code changes made. Exported and reviewed backtest run `#62` artifacts under [exports/backtest_run_62](/home/work/quant-dinger/exports/backtest_run_62) to verify whether entry sizing now compounds with updated capital.

### Frontend
- Added DCA Grid as a standard Python Script template in [frontend/src/views/trading-assistant/components/scriptTemplateCatalog.js](/home/work/quant-dinger/frontend/src/views/trading-assistant/components/scriptTemplateCatalog.js), reusing the embedded DCA Grid code and exposing `19` editable template parameters in the standard `Template Params` flow.
- Added localized template title/description and DCA Grid template-param labels/descriptions in [frontend/src/locales/lang/vi-VN.js](/home/work/quant-dinger/frontend/src/locales/lang/vi-VN.js), [frontend/src/locales/lang/en-US.js](/home/work/quant-dinger/frontend/src/locales/lang/en-US.js), and [frontend/src/locales/lang/zh-CN.js](/home/work/quant-dinger/frontend/src/locales/lang/zh-CN.js).

### Notes / Pending
- Confirmed run `#62` still does **not** compound new base entries by current capital: later `open_long` amounts remained around `0.0156` even when pre-entry balance had increased above `1100`, while compounded sizing should have been about `0.0172` and `0.0173` at those points.
- Verified the new script template wiring by importing `scriptTemplateCatalog.js` with Node and checking that `buildTemplateCode('dcaGrid', ...)` rewrites values such as `entry_pct` and `use_trailing` into the generated code.
- The new DCA Grid template now appears in the standard Python Script template catalog, but the separate dedicated `DCA Grid Bot` create-mode card still exists; remove or merge that card later only if you want to consolidate the UX.

## 2026-05-16 (Strategy Create Modal Pair Fallback)

### Backend
- No backend code changes made. Confirmed the Python backend already exposes `/api/market/watchlist/get`, `/api/indicator/getIndicators`, `/api/credentials/list`, and `/api/strategies/notifications/unread-count`, so the reported 404s are likely environment/proxy issues rather than missing Python routes.

### Frontend
- Updated [frontend/src/views/trading-assistant/index.vue](/home/work/quant-dinger/frontend/src/views/trading-assistant/index.vue) so strategy creation now uses `currentUserId` instead of hardcoded user id `1` for watchlist, add-watchlist, and exchange-credentials requests.
- Added a fallback in [frontend/src/views/trading-assistant/index.vue](/home/work/quant-dinger/frontend/src/views/trading-assistant/index.vue) so when watchlist loading fails or returns empty, the trading pair dropdown is populated from `getHotSymbols(...)` instead of staying empty with `No Data`.

### Notes / Pending
- Verified the patch is present with a local Node source check.
- This fixes the immediate strategy-create UX problem where the DCA Grid template opens with an empty trading-pair list, but it does not eliminate unrelated console 404s if the local frontend is still pointed at a backend/proxy that does not serve those `/api/*` routes correctly.

## 2026-05-16 (Frontend Proxy Fixed To Local Backend Port)

### Backend
- No backend code changes made. Diagnosed the local API issue by confirming `localhost:5000` was occupied by an unrelated `webhook_bot.py` service, while the QuantDinger backend from this repo was actually listening on `localhost:5005` and serving `/api/*` correctly there.

### Frontend
- Updated [frontend/vue.config.js](/home/work/quant-dinger/frontend/vue.config.js) so the dev proxy now targets `VUE_APP_PYTHON_API_BASE_URL` and defaults to `http://localhost:5005` instead of the stale `http://localhost:5000`.
- Updated [frontend/src/config/defaultSettings.js](/home/work/quant-dinger/frontend/src/config/defaultSettings.js) so the frontend's Python API fallback base URL also defaults to `http://localhost:5005`.
- Updated [frontend/.env.development](/home/work/quant-dinger/frontend/.env.development) to define `VUE_APP_PYTHON_API_BASE_URL=http://localhost:5005`, making the intended local backend target explicit.

### Notes / Pending

## 2026-05-16 (Concept Explanation: Bot vs Strategy vs Live)

### Backend
- No code changes made. Answered a conceptual question about the difference between trading bot, strategy, and live trading for this repo context.

### Frontend
- No code changes made. No UI updates were required for this task.

### Notes / Pending
- No follow-up required unless you want this explanation turned into internal documentation or product copy.

## 2026-05-16 (Trading Bot Flow Explanation In Repo Context)

### Backend
- No code changes made. Reviewed bot creation and runtime flow across [backend_api_python/app/routes/strategy.py](/home/work/quant-dinger/backend_api_python/app/routes/strategy.py), [backend_api_python/app/services/strategy.py](/home/work/quant-dinger/backend_api_python/app/services/strategy.py), [backend_api_python/app/services/trading_executor.py](/home/work/quant-dinger/backend_api_python/app/services/trading_executor.py), and [backend_api_python/app/services/strategy_snapshot.py](/home/work/quant-dinger/backend_api_python/app/services/strategy_snapshot.py) to explain how bot mode is created, started, evaluated every tick, and persisted.

### Frontend
- No code changes made. Reviewed bot creation flow in [frontend/src/views/trading-assistant/index.vue](/home/work/quant-dinger/frontend/src/views/trading-assistant/index.vue), [frontend/src/views/trading-assistant/components/StrategyTypeSelector.vue](/home/work/quant-dinger/frontend/src/views/trading-assistant/components/StrategyTypeSelector.vue), [frontend/src/views/trading-assistant/components/BotParamsForm.vue](/home/work/quant-dinger/frontend/src/views/trading-assistant/components/BotParamsForm.vue), and [frontend/src/views/trading-assistant/components/scriptTemplateCatalog.js](/home/work/quant-dinger/frontend/src/views/trading-assistant/components/scriptTemplateCatalog.js).

### Notes / Pending
- Current UX appears to favor creating DCA logic from script templates in the mode selector, while backend/runtime still fully supports `strategy_mode='bot'` and `trading_config.bot_params`.

## 2026-05-16 (Polymarket BTC Strategy Review)

### Backend
- No backend code changes made. Reviewed [QuantDinger/polymarket_btc_strategy.py](/home/work/quant-dinger/QuantDinger/polymarket_btc_strategy.py) end-to-end and produced a detailed assessment report at [exports/polymarket_btc_strategy_review_2026-05-16.md](/home/work/quant-dinger/exports/polymarket_btc_strategy_review_2026-05-16.md).
- Verified syntax with `python3 -m py_compile QuantDinger/polymarket_btc_strategy.py`.
- Attempted a direct runtime check with `python3 QuantDinger/polymarket_btc_strategy.py --test-mode`, which failed because `python-dotenv` is not installed in the current environment.

### Frontend
- No code changes made. No frontend files were involved in this research task.

### Notes / Pending
- Main conclusion: the file is a useful prototype, but not production-ready and not yet compatible with the repo's standard `on_init/on_bar` script runtime.

## 2026-05-16 (Polymarket BTC Upstream Repo Re-Review)

### Backend
- No backend code changes made. Cloned and reviewed the upstream repository `aulekator/Polymarket-BTC-15-Minute-Trading-Bot` to reassess the strategy beyond the local extracted file.
- Produced an updated upstream-based review at [exports/polymarket_btc_origin_repo_review_2026-05-16.md](/home/work/quant-dinger/exports/polymarket_btc_origin_repo_review_2026-05-16.md).
- Verified static syntax for all Python files in the cloned upstream repo with a bulk `py_compile` pass.

### Frontend
- No code changes made. No frontend files were involved in this upstream research task.

### Notes / Pending
- Updated conclusion: the upstream repo is meaningfully stronger than the local extracted script, especially around divergence logic and the late-window trading thesis, but the README still overstates maturity versus implementation/testing reality.

## 2026-05-17 (Polymarket Strategy Go No-Go Answer)

### Backend
- No code changes made. Answered whether the Polymarket BTC strategy is worth converting into a QuantDinger strategy script for backtesting, and clarified whether it appears to be actively used in the current repo/runtime context.

### Frontend
- No code changes made. No frontend files were involved in this advisory task.

### Notes / Pending
- Current recommendation: backtest a reduced script version of the late-window core idea, not a blind full-port of the entire upstream bot architecture.

## 2026-05-17 (Polymarket Late-Window Script V1)

### Backend
- Added the first QuantDinger-native backtestable script version of the upstream late-window idea at [QuantDinger/polymarket_btc_late_window_script.py](/home/work/quant-dinger/QuantDinger/polymarket_btc_late_window_script.py).
- The new script keeps the simplest testable thesis: trade only near minute `13` of each 15-minute cycle, use `0.60 / 0.40` as the main trend gate, optionally require short-lookback momentum confirmation, and close positions on the next cycle rollover.
- Verified syntax with `python3 -m py_compile QuantDinger/polymarket_btc_late_window_script.py`.

### Frontend
- No code changes made. No frontend files were required for creating this strategy script.

### Notes / Pending
- Best tested on `1m` data or finer; using `15m` candles would destroy the late-window timing assumption.
- Next useful step is to run a first backtest, inspect trade count and distribution, then tune `trend_up_threshold`, `trend_down_threshold`, and `min_cycle_move_pct`.

## 2026-05-17 (Polymarket Backtest Readiness Clarified)

### Backend
- No code changes made. Verified that the new script is runtime-compatible with QuantDinger strategy scripts and that strategy backtests do load `trading_config.script_params` / `bot_params`.
- Also confirmed a current blocker for meaningful Polymarket backtests: [backend_api_python/app/data_sources/factory.py](/home/work/quant-dinger/backend_api_python/app/data_sources/factory.py) does not route a `Polymarket` market type into `DataSourceFactory`, so the standard backtest path cannot currently fetch Polymarket-style historical K-lines directly.

### Frontend
- No code changes made. No frontend files were required for this readiness check.

### Notes / Pending
- Recommendation stays the same: the script itself is ready, but a real backtest of this strategy needs Polymarket historical data support or an equivalent import/adaptation layer first.
- Verified `http://localhost:5005/health` returns `200` and `http://localhost:5005/api/strategies` returns `401 Token missing`, which confirms the correct backend is alive and the `/api/*` routes exist there.
- Frontend dev server must be restarted after changing `vue.config.js` / `.env.development`, otherwise the old proxy target `5000` will remain in memory.

## 2026-05-16 (Backtest 63 Audit)

### Backend
- No code changes made. Reviewed PostgreSQL backtest run `qd_backtest_runs.id = 63`, its `qd_backtest_trades` ledger, and the strategy code path in [QuantDinger/strategy_dca_grid_script.py](/home/work/quant-dinger/QuantDinger/strategy_dca_grid_script.py) plus [backend_api_python/app/services/backtest.py](/home/work/quant-dinger/backend_api_python/app/services/backtest.py).
- Confirmed run `#63` used `code_hash = ea270a...`, which differs from both the current DB strategy code and the local file, so the audit distinguishes “self-consistent with the historical run logic” from “matches the current script exactly”.

### Frontend
- No code changes made.

### Notes / Pending
- Main audit conclusion: run `#63` is internally coherent as a DCA-recovery backtest, but it should not be treated as a clean validation of the current local script because the script logic has changed materially since that run.
- Important follow-up if you want a strict apples-to-apples check: rerun the same market window with the current script and compare the new `code_hash`, trade sequence, and final PnL against run `#63`.

## 2026-05-16 (Backtest 63 Rechecked Against strategy_dca_grid_script.py)

### Backend
- No code changes made. Rechecked backtest run `#63` directly against the current [QuantDinger/strategy_dca_grid_script.py](/home/work/quant-dinger/QuantDinger/strategy_dca_grid_script.py), ignoring template/id differences as requested.

### Frontend
- No code changes made.

### Notes / Pending
- Confirmed a concrete logic mismatch with the current script: in [strategy_dca_grid_script.py](/home/work/quant-dinger/QuantDinger/strategy_dca_grid_script.py:308) a new long DCA layer stores `exit_price` as the weighted average of the whole stack, but run `#63` exits many DCA layers near their own layer price instead of that weighted stack price.
- Example from run `#63`: base long `69088.5` plus first DCA `67539.52` should give weighted-stack exit around `68314.01`, so the `reduce_long` at `67539.53` is not consistent with the current script's `price >= exit_price` rule in [strategy_dca_grid_script.py](/home/work/quant-dinger/QuantDinger/strategy_dca_grid_script.py:283).

## 2026-05-16 (DCA Grid Template Resynced)

### Backend
- No backend code changes made. Audited the DCA Grid bot/template flow and confirmed the mismatch was in the frontend embedded template code rather than in [QuantDinger/strategy_dca_grid_script.py](/home/work/quant-dinger/QuantDinger/strategy_dca_grid_script.py).

### Frontend
- Updated the embedded `DCA_GRID_CODE` in [frontend/src/views/trading-assistant/components/scriptTemplateCatalog.js](/home/work/quant-dinger/frontend/src/views/trading-assistant/components/scriptTemplateCatalog.js) so new DCA Grid bot/script templates now match the current `strategy_dca_grid_script.py` logic, including weighted-stack `exit_price`, aggregate ROI tracking, restored base-layer sizing, global take-profit priority, and the revised DCA amount calculation flow.

### Notes / Pending
- Verified with Node that `buildTemplateCode('dcaGrid', ...)` now emits code containing `avg_exit_price = _stack_average_price(new_stack)`, `total_entry_value`, and the current global TP / exit-DCA flow.
- Existing strategies already saved in the database keep their old `strategy_code`; only newly created templates (or strategies you reopen and resave with refreshed code) pick up the corrected embedded version automatically.

## 2026-05-16 (Mode Selector Cleanup And Backtest 65 Audit)

### Backend
- No backend code changes made. Reviewed PostgreSQL backtest run `#65` against the current DCA Grid logic, including weighted `exit_dca`, cumulative ROI accounting, realized trade profit sums, and the final liquidation path.

### Frontend
- Removed the standalone `DCA Grid Bot` card from [frontend/src/views/trading-assistant/components/StrategyTypeSelector.vue](/home/work/quant-dinger/frontend/src/views/trading-assistant/components/StrategyTypeSelector.vue) and cleaned related dead styling so strategy creation now relies on the existing script-template quick-start instead of showing a duplicate bot-mode card.

### Notes / Pending
- Run `#65` trade flow is logically consistent with the newer DCA Grid behavior: DCA layer exit prices are weighted-stack exits, DCA amounts scale upward with the configured multiplier, and the final wipeout is a leverage liquidation after max DCA depth rather than a profit/ROI math bug.
- Metric caveat recorded: `totalTrades` / `winRate` in backtest results are computed from non-zero-profit exit events only, so a run can show a very high win rate right before a final liquidation; the formulas are internally consistent but can be misleading at a glance.

## 2026-05-16 (Frontend And Backend Git Sync)

### Backend
- Committed local backend changes in [backend_api_python/app/services/backtest.py](/home/work/quant-dinger/backend_api_python/app/services/backtest.py), rebased `backend_api_python/main` onto `origin/main`, and pushed the updated branch successfully.

### Frontend
- Committed local frontend changes in [frontend/src/views/trading-assistant/components/scriptTemplateCatalog.js](/home/work/quant-dinger/frontend/src/views/trading-assistant/components/scriptTemplateCatalog.js), [frontend/src/views/trading-assistant/components/StrategyTypeSelector.vue](/home/work/quant-dinger/frontend/src/views/trading-assistant/components/StrategyTypeSelector.vue), related locale/config files, rebased `frontend/main` onto `origin/main`, and pushed the updated branch successfully.

### Notes / Pending
- Git sync completed without conflicts: frontend advanced from `origin/main` old tip `c5d5936` to pushed tip `ebcc3da`, backend advanced from `f8bb06a` to `6d11577`.
- Both repos ended clean after push (`git status` showed no remaining modified files).

## 2026-05-18 (DCA Grid Strategy Params In Detail Header)

### Backend
- No backend code changes made. Confirmed the DCA Grid template/runtime already stores active values in `trading_config.bot_params`, so this task only needed frontend rendering changes.

### Frontend
- Updated [frontend/src/views/trading-assistant/index.vue](/home/work/quant-dinger/frontend/src/views/trading-assistant/index.vue) to render strategy header badges from data instead of a small fixed set only:
  - Added computed header tags for symbol, leverage, direction, template, and timeframe.
  - Added a general strategy-parameter renderer for bot, script, and indicator strategies instead of only DCA Grid:
    - Bot strategies read `trading_config.bot_params`
    - Script strategies read `trading_config.script_params`, with fallback parsing from `ctx.param(...)` defaults in saved code for older records
    - Indicator strategies read `trading_config.indicator_params` plus core risk settings from `trading_config`
  - Extended template-key resolution so bot strategies with `bot_type` / `bot_params` still show the correct `DCA Grid Bot` template label even if stored mode data is inconsistent.
  - Added styling for parameter badges to visually separate config values from the basic strategy metadata badges.
- Updated [frontend/src/views/trading-assistant/components/StrategyEditor.vue](/home/work/quant-dinger/frontend/src/views/trading-assistant/components/StrategyEditor.vue) to accept initial template params when reopening/editing a script template strategy, and guarded against parent-child param sync loops.
- Updated script strategy save/edit flow in [frontend/src/views/trading-assistant/index.vue](/home/work/quant-dinger/frontend/src/views/trading-assistant/index.vue) to persist `trading_config.script_params` from the template editor so newly created script strategies also have stable param data for the detail layout.
- Updated the Trading Bots module so it can reuse strategies created in Trading Assistant instead of only hard-coded bot presets:
  - Added a new `Use Existing Strategy` card in [frontend/src/views/trading-bot/components/BotTypeCards.vue](/home/work/quant-dinger/frontend/src/views/trading-bot/components/BotTypeCards.vue).
  - Extended [frontend/src/views/trading-bot/index.vue](/home/work/quant-dinger/frontend/src/views/trading-bot/index.vue) to load reusable script/bot strategies from `/api/strategies`, pass them into the bot wizard, and include bot-page-created strategy clones in the bot list.
  - Extended [frontend/src/views/trading-bot/components/BotCreateWizard.vue](/home/work/quant-dinger/frontend/src/views/trading-bot/components/BotCreateWizard.vue) with source-strategy selection, source-prefill behavior, and payload cloning logic that reuses the selected strategy's code and saved params.
  - Updated [frontend/src/views/trading-bot/components/BotList.vue](/home/work/quant-dinger/frontend/src/views/trading-bot/components/BotList.vue) and [frontend/src/views/trading-bot/components/BotDetail.vue](/home/work/quant-dinger/frontend/src/views/trading-bot/components/BotDetail.vue) to recognize the new strategy-based bot type and display script-param-backed details.
  - Added locale strings in [frontend/src/locales/lang/en-US.js](/home/work/quant-dinger/frontend/src/locales/lang/en-US.js) and [frontend/src/locales/lang/vi-VN.js](/home/work/quant-dinger/frontend/src/locales/lang/vi-VN.js) for the new strategy-reuse bot flow.

### Notes / Pending
- Tried running `npm run lint:nofix -- --files src/views/trading-assistant/index.vue` in `frontend`, but the command did not return output in this environment before timing out/polling stalled, so there is no clean lint confirmation from the tool run yet.
- If you want, the next small UX pass could group the parameter badges by section (`Entry`, `DCA`, `Exit`) or collapse less-important params behind a “show more” toggle when the list gets long.
- Current strategy-reuse flow is focused on reusing existing `script` / `bot` strategies that already have saved executable code. It does not yet clone indicator-only strategies into the Trading Bots wizard.

## 2026-05-18 (Reverted Trading Bot Strategy-Reuse Experiment)

### Backend
- No backend code changes made.

### Frontend
- Reverted the `Use Existing Strategy` experiment from the Trading Bots module and restored the original 4-card preset flow in:
  - [frontend/src/views/trading-bot/components/BotTypeCards.vue](/home/work/quant-dinger/frontend/src/views/trading-bot/components/BotTypeCards.vue)
  - [frontend/src/views/trading-bot/index.vue](/home/work/quant-dinger/frontend/src/views/trading-bot/index.vue)
  - [frontend/src/views/trading-bot/components/BotCreateWizard.vue](/home/work/quant-dinger/frontend/src/views/trading-bot/components/BotCreateWizard.vue)
  - [frontend/src/views/trading-bot/components/BotList.vue](/home/work/quant-dinger/frontend/src/views/trading-bot/components/BotList.vue)
  - [frontend/src/views/trading-bot/components/BotDetail.vue](/home/work/quant-dinger/frontend/src/views/trading-bot/components/BotDetail.vue)
  - [frontend/src/locales/lang/en-US.js](/home/work/quant-dinger/frontend/src/locales/lang/en-US.js)
  - [frontend/src/locales/lang/vi-VN.js](/home/work/quant-dinger/frontend/src/locales/lang/vi-VN.js)

### Notes / Pending
- The Trading Bots module is back to its original design: 4 built-in preset bot cards plus AI-assisted creation, separate from Trading Assistant strategy templates.
- No lint/build verification was completed in this environment after the revert.

## 2026-05-18 (Inspected DCA Grid Param Source Without Code Changes)

### Backend
- No backend code changes made. Reviewed how strategy snapshots/runtime read `bot_params` vs `script_params`.

### Frontend
- No code changes made. Traced the DCA Grid parameter flow in:
  - [frontend/src/views/trading-assistant/components/BotParamsForm.vue](/home/work/quant-dinger/frontend/src/views/trading-assistant/components/BotParamsForm.vue)
  - [frontend/src/views/trading-assistant/components/scriptTemplateCatalog.js](/home/work/quant-dinger/frontend/src/views/trading-assistant/components/scriptTemplateCatalog.js)
  - [frontend/src/views/trading-assistant/components/StrategyEditor.vue](/home/work/quant-dinger/frontend/src/views/trading-assistant/components/StrategyEditor.vue)
  - [frontend/src/views/trading-assistant/index.vue](/home/work/quant-dinger/frontend/src/views/trading-assistant/index.vue)

### Notes / Pending
- Confirmed there are two different DCA Grid parameter definitions in the frontend:
  - `BOT_TEMPLATE_CATALOG` for bot-mode forms
  - `SCRIPT_TEMPLATE_CATALOG` for script-template editing
- Confirmed the displayed header tags are derived from saved `trading_config.bot_params` or `trading_config.script_params`, and missing keys are filled from template defaults.
- Found a likely UX trap for script-template mode: changing template params in the editor does not persist to parent/save payload until the user applies the template params back into code.

## 2026-05-18 (Binance Exchange Client Creation Failed)

### Backend
- Diagnosed `Exchange client creation failed (): Unsupported exchange_id:` error when connecting Binance strategy to live trading.
- Root cause: `resolve_exchange_config()` in `exchange_execution.py` silently swallowed credential load failures (wrong `SECRET_KEY`, `user_id` mismatch, or missing credential), returning `{}` with no `exchange_id`, causing `create_client()` to fail with empty exchange_id.
- Improved error logging in `backend_api_python/app/services/exchange_execution.py`:
  - `_load_credential_config`: Changed `logger.warning` to `logger.error` with explicit messages for "no credential found", "decrypt failed", and "empty JSON after decrypt".
  - `resolve_exchange_config`: Added `logger.error` when credential returns empty config, and `logger.warning` when `exchange_id` is still empty after full merge — so the root cause is now visible in logs before the worker fails.

### Notes / Pending
- To confirm root cause: restart backend and retry the strategy signal — the new error logs will show exactly which of the 3 failure modes is occurring (credential not found, decrypt error, or user_id mismatch).
- Most likely fix after seeing logs: re-save the Binance credential from the UI (Settings → Exchange Credentials → Edit → Save) to re-encrypt with the current `SECRET_KEY`, then re-link it to the strategy.
- If `user_id` mismatch: check that the strategy's `user_id` matches the credential's `user_id` in `qd_exchange_credentials`.

## 2026-05-18 (Inspected Backtest Run 70 Against Strategy 8)

### Backend
- No backend code changes made. Inspected local PostgreSQL records for `qd_backtest_runs.id = 70` and `qd_strategies_trading.id = 8`.
- Verified `runId=70` is a successful `strategy_script` backtest for `strategyId=8` (`DCA Grid Bot Strategy`) on `ETH/USDT`, timeframe `15m`, date range `2026-02-17` to `2026-05-18`, leverage `100`, initial capital `10`.
- Verified the strategy snapshot/backtest path in:
  - [backend_api_python/app/routes/strategy.py](/home/work/quant-dinger/backend_api_python/app/routes/strategy.py)
  - [backend_api_python/app/services/strategy_snapshot.py](/home/work/quant-dinger/backend_api_python/app/services/strategy_snapshot.py)
  - [backend_api_python/app/services/backtest.py](/home/work/quant-dinger/backend_api_python/app/services/backtest.py)
- Confirmed script backtests seed `ctx._params` from `snapshot.script_params`, so `runId=70` uses `strategyId=8`'s saved `trading_config.script_params` (`rsi_threshold_long=45`, `rsi_threshold_short=65`, `ma_rsi_threshold_long=45`, `ma_rsi_threshold_short=65`) instead of template defaults.
- Confirmed the entry sizing in `runId=70` is consistent with the strategy settings: `entry_pct=0.25`, `initial_capital=10`, `leverage=100`, and entry near `1978.75` produced amount `0.126342...`, matching the backtest trade/result log.
- Identified a backtest behavior caveat in [backend_api_python/app/services/backtest.py](/home/work/quant-dinger/backend_api_python/app/services/backtest.py): liquidation is triggered at `entry_price * (1 - 1/leverage)` for long positions and, when hit, `_liquidation_loss(capital)` sets the result to lose the entire remaining account capital (`capital = 0`), even when the strategy only opened a partial-margin position via `entry_pct < 1`.

### Frontend
- No frontend code changes made. Cross-checked the current UI-stored `strategyId=8` parameters against the strategy row and confirmed the saved script params align with the intended `45/65` thresholds.

### Notes / Pending
- `runId=70` is logically aligned with `strategyId=8` for signal source, next-bar-open execution timing, and entry amount sizing.
- The `-100%` final result is not a full DCA-cycle result; it is dominated by the current backtest liquidation model, which wipes the whole account once the liquidation price is touched.
- If needed next, compare `runId=69` and `runId=70` side by side, or patch the liquidation model so partial-margin entries do not zero the entire account on liquidation.

## 2026-05-18 (Calculated Run 70 Liquidation Vs First DCA)

### Backend
- No backend code changes made. Queried `qd_backtest_runs.id = 70` result payload to extract the actual filled entry, liquidation event, and first `LONG dca_check` level for `strategyId=8`.
- Confirmed from `runId=70`:
  - executed long entry trade price = `1978.76`
  - liquidation trade price = `1958.9724`
  - first DCA check price from strategy logs = `1939.175000`
- Recomputed the same levels from the current strategy settings:
  - long liquidation with leverage `100`: `1978.76 * (1 - 1/100) = 1958.9724`
  - first DCA level from a `2%` grid anchored to the script's recorded base `1978.75`: `1978.75 * 0.98 = 1939.175`

### Frontend
- No frontend code changes made.

### Notes / Pending
- In `runId=70`, liquidation is about `19.7974` points above the first DCA level, so the position gets liquidated before the script ever reaches DCA 1.
- The tiny `0.0098` difference between `1939.1750` and `1978.76 * 0.98 = 1939.1848` comes from the script logging its base anchor at `1978.75`, while the executed trade record is rounded to `1978.76` on the next bar fill.

## 2026-05-18 (Fixed Trading Assistant Execution Badge Ambiguity)

### Backend
- No backend code changes made. Verified the local DB contains a live strategy (`strategy_id=8`) with `execution_mode = live` but an empty `exchange_config`, which is why the UI previously fell back to a vague `Live Trading` badge.
- Verified the local credential vault currently has one saved credential for the user: `exchange_id = binance`.

### Frontend
- Updated [frontend/src/views/trading-assistant/index.vue](/home/work/quant-dinger/frontend/src/views/trading-assistant/index.vue) so execution badges in strategy list and detail header no longer show ambiguous `Live Trading` text.
- Added execution-source inference rules:
  - first use `exchange_config.exchange_id`
  - then fallback to the exchange resolved from stored `credential_id`
  - then, for live strategies with no explicit exchange link, fallback to the single compatible saved credential when exactly one exists
  - otherwise show a warning-state badge `Live · Exchange Missing`
- With the current local data, the live DCA Grid strategy now resolves to `Live Binance` instead of generic `Live Trading`.

### Notes / Pending
- This avoids misleading labels while still surfacing data integrity issues for older/live records missing exchange linkage.
- If you want a stricter fix later, the next step would be a small data migration/backfill so old live strategies always persist `credential_id` or `exchange_id` explicitly.

## 2026-05-18 (Fixed Strategy List Badge Overflow Layout)

### Backend
- No backend code changes made.

### Frontend
- Updated [frontend/src/views/trading-assistant/index.vue](/home/work/quant-dinger/frontend/src/views/trading-assistant/index.vue) to fix strategy list layout overflow after adding execution badges.
- Adjusted the left strategy list item layout so long badge combinations no longer spill into the detail panel:
  - strategy name/badge row now wraps safely
  - grouped strategy items no longer force single-line badge layouts
  - strategy title can break to a new line when needed
  - action menu aligns to the top so the content column can grow vertically

### Notes / Pending
- This is a CSS/layout-only fix; no strategy logic or saved data changed.
- If another badge is added later, the row should now wrap inside the card instead of overflowing right.

## 2026-05-18 (Fixed Initial Execution Badge Resolution On Page Load)

### Backend
- No backend code changes made.

### Frontend
- Updated [frontend/src/views/trading-assistant/index.vue](/home/work/quant-dinger/frontend/src/views/trading-assistant/index.vue) to load exchange credentials during `mounted()` instead of only in create/edit flows.
- This fixes the first-render/F5 case where live strategies temporarily showed `Live · Exchange Missing` because `exchangeCredentials` had not been fetched yet.

### Notes / Pending
- With this change, the live strategy badge can resolve to `Live Binance` immediately on initial page load when the exchange is inferred from the saved credential set.

## 2026-05-18 (Reviewed Git State And Pushed Frontend/Backend)

### Backend
- Reviewed git state in [backend_api_python](/home/work/quant-dinger/backend_api_python) and confirmed branch `main` was not behind `origin/main` before pushing.
- Committed backend tracked changes in [backend_api_python/app/services/exchange_execution.py](/home/work/quant-dinger/backend_api_python/app/services/exchange_execution.py) with commit `a721ac8` and pushed `main -> origin/main`.

### Frontend
- Reviewed git state in [frontend](/home/work/quant-dinger/frontend) and confirmed branch `main` was not behind `origin/main` before pushing.
- Committed frontend tracked changes in:
  - [frontend/src/views/trading-assistant/index.vue](/home/work/quant-dinger/frontend/src/views/trading-assistant/index.vue)
  - [frontend/src/views/trading-assistant/components/StrategyEditor.vue](/home/work/quant-dinger/frontend/src/views/trading-assistant/components/StrategyEditor.vue)
- Pushed frontend commit `15685a2` from `main` to `origin/main`.

### Notes / Pending
- `frontend` is clean after push.
- `backend_api_python` still has untracked local diagnostic scripts under `scripts/`; they were intentionally not committed or pushed to avoid polluting the remote with debug helpers.

## 2026-05-18 (Diagnosed Binance Order Failure For Live Script Strategy)

### Backend
- Investigated `Exchange client creation failed (): Unsupported exchange_id:` for live strategy execution.
- Confirmed from `qd_strategy_logs` that `strategy_id=8` produced a valid `open_long` signal and then failed at exchange-client creation, so the problem was in live execution config rather than signal generation.
- Confirmed the root cause in local DB: [qd_strategies_trading] record `strategy_id=8` had `execution_mode = live` but an empty `exchange_config`, while the same user already had a valid Binance credential (`credential_id=1`, `exchange_id=binance`).
- Repaired the live strategy record in the local DB by setting `exchange_config` for `strategy_id=8` to `{\"credential_id\": 1}` so future live orders can resolve Binance correctly.
- Added backend validation in [backend_api_python/app/services/strategy.py](/home/work/quant-dinger/backend_api_python/app/services/strategy.py) so create/update now rejects `execution_mode = live` when the resolved exchange config is empty, preventing silent saves of broken live strategies.

### Frontend
- Fixed [frontend/src/views/trading-assistant/index.vue](/home/work/quant-dinger/frontend/src/views/trading-assistant/index.vue) so `script` and `bot` strategy save flows now include `exchange_config` for live execution, matching the signal-strategy flow.
- Added shared live-exchange payload building for IBKR, MT5, and crypto credential-based live strategies, plus live credential validation for script/bot mode before submit.

### Notes / Pending
- The immediate Binance failure was caused by missing `exchange_config` on the saved live strategy, not by the DCA Grid script logic itself.
- The DB repair for `strategy_id=8` takes effect immediately for future signal-to-order execution because the pending-order worker resolves exchange config from the stored strategy row at execution time.
- The new frontend/backend code protections require the running app processes to pick up the code changes (restart/redeploy if hot reload is not active).

## 2026-05-18 (Pulled Checked State And Pushed Live Trading Fixes)

### Backend
- Verified [backend_api_python](/home/work/quant-dinger/backend_api_python) `main` was not behind `origin/main` before publishing the latest fix.
- Committed and pushed [backend_api_python/app/services/strategy.py](/home/work/quant-dinger/backend_api_python/app/services/strategy.py) with commit `f86c908` to enforce valid exchange config for live strategies.

### Frontend
- Verified [frontend](/home/work/quant-dinger/frontend) `main` was not behind `origin/main` before publishing the latest fix.
- Committed and pushed [frontend/src/views/trading-assistant/index.vue](/home/work/quant-dinger/frontend/src/views/trading-assistant/index.vue) with commit `460e6b0` to persist live `exchange_config` for script/bot strategy saves.

### Notes / Pending
- Only the files related to the live Binance order bug were committed in this push.
- Other local modifications already present in `frontend` and `backend_api_python` were intentionally left untouched to avoid bundling unrelated changes or causing conflicts.

## 2026-05-18 (Pyodide Self-Host Fix)

### Frontend
- Diagnosed root cause of "Python Engine Load Failed / Your current region or network environment cannot use this feature" error in `/indicator-ide` Chart tab:
  - `KlineChart.vue` defaults to loading pyodide from `/assets/pyodide/v0.25.0/full/pyodide.js` (local), but `public/assets/pyodide/` did not exist → 404.
  - CDN fallback (`cdn.jsdelivr.net`) is accessible from server/WSL but blocked in browser by region/network → both paths fail → `pyodideLoadFailed = true`.
- Downloaded all required pyodide v0.25.0 files to `frontend/public/assets/pyodide/v0.25.0/full/` via jsDelivr from WSL (server-side accessible):
  - Core: `pyodide.js`, `pyodide.asm.js`, `pyodide.asm.wasm`, `pyodide-lock.json`, `python_stdlib.zip`
  - Packages: `numpy-1.26.1`, `pandas-1.5.3`, `python_dateutil-2.8.2`, `pytz-2023.3`, `six-1.16.0`
- Updated `frontend/.env.development` to set `VUE_APP_PYODIDE_LOCAL_BASE`, `VUE_APP_PYODIDE_PREFER_CDN=false`, `VUE_APP_ALLOW_EXTERNAL_PYODIDE=false` so pyodide loads from self-hosted local path instead of CDN.
- Added `frontend/scripts/download-pyodide.sh` as a reusable script to re-download pyodide assets if needed.

### Notes / Pending
- Restart the frontend dev server after `.env.development` changes for the new env vars to take effect.
- `public/assets/pyodide/` (~46MB) should be added to `.gitignore` if not already, to avoid committing large binary files.
- For production builds, either include the pyodide folder in the build output or set `VUE_APP_PYODIDE_CDN_BASE` to a self-hosted CDN/S3 bucket.

## 2026-05-18 (AI Suggest Flow Analysis)

### Backend
- Analyzed `backend_api_python/app/routes/backtest.py` — `POST /backtest/aiAnalyze` endpoint (line 658)
- Analyzed `_heuristic_ai_advice()` rule-based fallback (line 444)
- Analyzed `backend_api_python/app/config/api_keys.py` — `APIKeys.OPENROUTER_API_KEY` priority: env var → DB addon config

### Frontend
- Analyzed `frontend/src/views/indicator-analysis/components/BacktestHistoryDrawer.vue` — full AI Suggest flow
- Confirmed component is used in: `frontend/src/views/indicator-ide/index.vue` and `frontend/src/views/trading-assistant/index.vue`
- Analyzed `frontend/src/utils/request.js` — `ANALYSIS_TIMEOUT = 180000ms` (3 min) for `/backtest/aiAnalyze`

### Notes / Pending
- No code changes made — analysis only.
- Noted timeout mismatch: frontend allows 180s but backend OpenRouter call has 30s hard timeout → silent fallback to heuristic on slow LLM.
- LLM response is non-streaming (blocking); consider SSE/streaming for better UX.
- Max 10 runs per AI Suggest call (backend enforced).

## 2026-05-18 (Fix AI Suggest — Use LLMService instead of hardcoded OpenRouter)

### Backend
- `backend_api_python/app/routes/backtest.py`:
  - Removed hardcoded OpenRouter-only logic from `ai_analyze_backtest_runs()` endpoint
  - Removed `_openrouter_base_and_key()` helper function (no longer needed)
  - Removed `import requests` (no longer used in this file)
  - Replaced with `LLMService.call_llm_api()` — now respects system-wide provider config: `CUSTOM_API_URL`, `CUSTOM_MODEL`, `LLM_PROVIDER`, etc.
  - Provider readiness check: falls back to heuristic if no provider is configured (key or custom URL)
  - `use_json_mode=False` so LLM returns plain markdown text (not JSON)

### Notes / Pending
- Root cause: endpoint was written before `LLMService` existed and never updated.
- With `CUSTOM_API_URL=https://api.chainhub.tech/v1` and `CUSTOM_MODEL=gpt-5.4-mini` in `.env`, AI Suggest will now correctly use the custom provider.
- `OPENROUTER_TEMPERATURE` env var is still reused for temperature config (no breaking change).
